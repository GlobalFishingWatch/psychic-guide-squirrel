#!/usr/bin/env python

from __future__ import division

import copy
import datetime
import itertools as it
import json
import math
import multiprocessing as mp
import multiprocessing.dummy
import posixpath as pp
import random
import threading
import time
try:
    from urlparse import urlsplit
except ImportError:
    from urllib.parse import urlsplit

import click
import ee
from googleapiclient import discovery
import oauth2client.client


_GCS_API = None
_CREDENTIALS = None


def rate_limit(iterator, number, seconds):

    """Given an iterator, ensure that only N items are yielded within a given
    time window.  Used to prevent swamping the API.

    Parameters
    ----------
    iterator : iter
        Produce items from this iterator.
    number : int
        Don't emit more than ``number`` of items per ``seconds``.
    seconds : int
        Don't emit more than ``number`` of items per ``seconds``.

    Yields
    ------
    object
        From ``iterator``.
    """

    lock = threading.Lock()
    start = time.time()
    end = start + seconds
    n_yielded = 0
    for item in iterator:
        yield item
        n_yielded += 1
        if n_yielded >= number or time.time() >= end:
            wait = end - time.time() + random.uniform(0.01, 0.001)
            time.sleep(wait)
            start = time.time()
            end = start + seconds
            n_yielded = 0


def _gcs_api():
    """Lazily ensure the GCS API has been discovered."""
    global _GCS_API
    if _GCS_API is None:
        _GCS_API = discovery.build('storage', 'v1', credentials=_credentials())
    return _GCS_API


def _credentials():
    """Lazily ensure we are authenticated."""
    global _CREDENTIALS
    if _CREDENTIALS is None:
        _CREDENTIALS = oauth2client.client.GoogleCredentials.get_application_default()
    return _CREDENTIALS


def gcs_listdir(path):
    """Recursively list a GCS directory."""
    url = urlsplit(path)
    assert url.scheme == 'gs', "Need a GCS URL, not: {}".format(path)
    bucket = url.netloc
    prefix = url.path[1:]

    request = _gcs_api().objects().list(bucket=bucket, prefix=prefix)
    response = request.execute()

    while response is not None:
        for item in response.get('items', []):
            yield 'gs://' + pp.join(item['bucket'], item['name'])

        request = _gcs_api().objects().list_next(request, response)
        if request is None:
            break

        response = request.execute()


def _upload_params(paths, nodata, dst):
    """Given a bunch of file paths, construct Earth Engine ingestion requests.

    The EE docs are lacking and the source is stupid hard to read.  Here's
    an example request that this thing builds:

        {
            'missingData': {
                'value': -9999
            },
            'pyramidingPolicy': 'MODE',
            'tilesets': [
                {
                    'sources': [
                        {
                            'primaryPath': 'gs://new-benthos-pipeline/scratch/inital-daily-density/allvessels_2013-05-01.tif'
                        }
                    ]
                }
            ],
            'id': 'users/kwurster/2013-05-01-trash',
            'properties': {
                'system:time_end': 1367366400000,
                'system:time_start': 1367366400000,
                'gfw': 'density'
            }
        }

    Parameters
    ----------
    paths : iter
        Iterable producing GCS URLs.
    nodata : str or int or float or None
        Set nodata value or policy for all input images.
    dst : str
        Target image collection.
    """

    for p in paths:

        name = pp.basename(p)
        start_time = datetime.date(
            year=int(name[4:8]),
            month=int(name[9:11]),
            day=int(name[12:14]))
        end_time = start_time + datetime.timedelta(days=1)

        props = {
            'system:time_end': 1000*time.mktime(start_time.timetuple()),
            'system:time_start': 1000*time.mktime(end_time.timetuple()),
            'country':name[:3],
            # 'geartype':'trawler'
        }

        request = {
            'pyramidingPolicy': 'MODE',
            'tilesets': [
                {
                    'sources': [
                        {
                            'primaryPath': p
                        }
                    ]
                }
            ],
            'id': pp.splitext(pp.join(dst, name))[0],
            'properties': props
        }

        if nodata is not None:
            request['missingData'] = {
                'value': nodata
            }

        yield request


def _ls_collection(path):
    """List images in an Earth Engine ImageCollection."""
    path = path.rstrip('/')
    results = ee.data.getList({'id': path})
    for item in results:
        if item['type'] == 'Image':
            yield item['id']
        elif item['type'] == 'ImageCollection':
            for i in _ls_collection(item['id']):
                yield i
        else:
            raise ValueError(
                "Unrecognized asset type: '{}'".format(item['type']))


def _upload(kwargs):
    """Send an ingestion request to Earth Engine.  For use with
    `multiprocessing.dummy.Pool.imap_unordered()`."""
    request = kwargs['request']
    retries = kwargs['retries']
    retry_wait = kwargs['retry_wait']
    task_id = kwargs['task_id']

    out = {
        'completed': False,
        'request': request,
        'response': None,
        'exceptions': []
    }

    attempt = 1
    while attempt <= retries:
        try:
            out['response'] = ee.data.startIngestion(task_id, request)
            out['completed'] = True
            break

        except ee.EEException as e:
            attempt += 1
            out['exceptions'].append(str(e))
            time.sleep(retry_wait + random.uniform(0.1, 0.01))
    else:
        out['completed'] = False

    return out


@click.command()
@click.argument('indir')
@click.argument('collection')
@click.option(
    '--nodata', type=click.FLOAT, default=None, show_default=True,
    help="Set nodata value for all images.")
@click.option(
    '--qps', default=3, type=click.FLOAT, show_default=True,
    help="Queries per second.")
@click.option(
    '--retries', default=5, show_default=True,
    help="Number of retries for any given API call.")
@click.option(
    '--retry-wait', metavar='SECONDS', type=click.FLOAT, default=1.1,
    show_default=True,
    help="Amount of time to wait between retry attempts.")
@click.option(
    '--threads', default=3, show_default=True,
    help="Execute queries across N threads.  Can't be more than --qps.")
@click.option(
    '--wait / --no-wait', default=False, show_default=True,
    help="Wait for all ingestion jobs to complete before exiting.")
@click.option(
    '--wait-sleep', default=3, show_default=True,
    help="When waiting for ingestion jobs to complete, sleep for N seconds "
         "between each check.")
@click.pass_context
def cli(
        ctx, indir, collection, nodata, qps, retries, threads, retry_wait, wait,
        wait_sleep):

    """Upload density rasters to a single Earth Engine image collection.

    Default behavior is to schedule the ingest requests and exit.  Use the
    --wait flag to poll until all tasks are complete.

    If an input image already exists in the target collection it is ignored.
    """

    collection = collection.rstrip('/')
    print collection

    if threads > qps:
        raise click.BadParameter(
            "'--threads' cannot be larger than '--qps': {} >= {}.".format(
                threads, qps))

    ee.Initialize()

    ee.data.create_assets([collection], ee.data.ASSET_TYPE_IMAGE_COLL, False)

    completed = set(map(pp.basename, _ls_collection(collection)))

    # When checking to see if any of the requested uploads are running we can
    # also grab their task ID's in case we need to --wait for everything to
    # finish
    discovered_running = set()

    # Filter out images that have already been ingested or are currently running
    for t in ee.data.getTaskList():
        if t['task_type'] == 'INGEST':
            o_path = t['description'].lower().split('asset ingestion: ')[1]
            # Image was already successfully ingested
            if t['state'] == 'COMPLETED':
                url = urlsplit(t['output_url'][0])
                o_path = url.query.split('asset=')[1]
                if pp.dirname(o_path).rstrip('/') == collection:
                    completed.add(pp.basename(o_path))
            # Image is currently being ingested
            elif t['state'] == 'RUNNING':
                if pp.dirname(o_path).rstrip('/') == collection:
                    completed.add(pp.basename(o_path))
                    discovered_running.add(t['id'])

    inpaths = [
        p for p in gcs_listdir(indir) if pp.basename(p)[:10] not in completed and pp.basename(p) != '']
    task_ids = []

    # All input paths have been ingested
    if not inpaths and not discovered_running:
        click.echo("All input images have already been ingested.")
        ctx.exit()

    elif inpaths:

        id_batch_size = 1000
        if len(inpaths) <= id_batch_size:
            id_batches = [len(inpaths)]
        else:
            _n_full = int(math.floor(len(inpaths) / id_batch_size))
            id_batches = ([id_batch_size] * _n_full) + [len(inpaths) % 1000]

        task_ids = list(
            it.chain.from_iterable(map(ee.data.newTaskId, id_batches)))

        tasks = _upload_params(
            paths=inpaths,
            nodata=nodata,
            dst=collection)
        tasks = ({
            'request': r,
            'retries': retries,
            'retry_wait': retry_wait,
            'task_id': tid
        } for tid, r in it.izip_longest(task_ids, tasks))
        tasks = rate_limit(tasks, qps, 1)

        label = 'Loading {} images'.format(len(inpaths))
        progressbar = click.progressbar(tasks, length=len(inpaths), label=label)
        with progressbar as tasks:

            pool = mp.dummy.Pool(threads)

            if threads == 1:
                results = (_upload(t) for t in tasks)
            else:
                results = pool.imap_unordered(_upload, tasks)

            for res in results:
                if not res['completed']:
                    raise click.ClickException(
                        "Request failed: {}".format(json.dumps(res)))

    if wait:
        click.echo("Waiting for ingestion to finish ...")
        check_ids = copy.deepcopy(set(task_ids)) | discovered_running
        failed_tasks = []
        n_failed = 0
        n_completed = 0
        while check_ids:

            time.sleep(wait_sleep)

            # Keep track of failed tasks so we can update the user each cycle
            _n_failed = 0
            _n_completed = 0

            for task in ee.data.getTaskList():
                if task['id'] in check_ids:
                    state = task['state']

                    if state == 'FAILED':

                        # Task is marked as failed, but only because the target
                        # asset already exists
                        if 'cannot overwrite asset' in \
                                task['error_message'].lower():
                            _n_completed += 1

                        # Actual failure
                        else:
                            _n_failed += 1
                            failed_tasks.append(task)
                        check_ids.discard(task['id'])

                    elif state == 'COMPLETED':
                        _n_completed += 1
                        check_ids.discard(task['id'])

            # Update the user
            n_failed += _n_failed
            n_completed += _n_completed
            if _n_failed > 0 or _n_completed > 0:
                click.echo(
                    "Found {} failed and {} completed tasks".format(
                        _n_failed, _n_completed))

        # Final status report
        click.echo("Failed:    {}".format(n_failed))
        click.echo("Completed: {}".format(n_completed))
        if failed_tasks:
            click.echo("Failed tasks:")
            for task in failed_tasks:
                click.echo(json.dumps(task, sort_keys=True))


if __name__ == '__main__':
    cli()
