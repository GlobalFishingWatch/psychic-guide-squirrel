"""
The following script creates a geotiff of vessel density for a given calendar date

usage:

! python daily_raster_fishing_effort.py yyyymmdd

The code for downloading a table from BigQuery was written by Tim Hochberg:
https://github.com/GlobalFishingWatch/nn-vessel-classification/blob/master/tah-proto/get-data/gctools.py
"""

import uuid
import time
import subprocess
from googleapiclient import discovery
from oauth2client.client import GoogleCredentials
import csv
import sys
import numpy as np
import gzip
import rasterio as rio
import affine

# date should be YYYYMMDD
# I don't have any error handling, so get it right
thedate = sys.argv[1] # 

# Change these depending on where you want things locally
path_to_csv_zip = "../data/dailytables/fishing_vessel_effort/zips/"
path_to_tiff = "../data/dailytables/fishing_vessel_effort/tiffs/"

yyyy = thedate[:4]
mm = thedate[4:6]
dd = thedate[6:8]

# make all 
query = '''
SELECT
  INTEGER(FLOOR(lat*10)) lat_bin,
  INTEGER(FLOOR(lon*10)) lon_bin,
  SUM(IF(last_timestamp IS NOT NULL, (timestamp-last_timestamp)/3600000000, 
    (timestamp - TIMESTAMP("'''+yyyy+'-'+mm+"-"+dd+''' 00:00:00"))/3600000000)/2 + 
IF(next_timestamp IS NOT NULL, (next_timestamp - timestamp)/3600000000, 
  (TIMESTAMP("'''+yyyy+'-'+mm+"-"+dd+''' 23:59:59") - timestamp)/3600000000 )/2) hours
FROM
  [pipeline_classify_logistic_661b_fishing.'''+thedate+''']
WHERE
  measure_new_score > .5
  and seg_id NOT IN (
  SELECT
    seg_id
  FROM
    [scratch_david_seg_analysis_661b.'''+thedate[:4]+'''_segments]
  WHERE
    (point_count<20
      AND terrestrial_positions = point_count)
    OR ((min_lon >= 0 // these are almost definitely noise
        AND max_lon <= 0.109225)
      OR (min_lat >= 0
        AND max_lat <= 0.109225) ))
  AND lat < 90
  AND lat > -90
  AND lon > -180
  AND lon < 180
GROUP BY
  lat_bin,
  lon_bin
'''


proj_id = "world-fishing-827"
dataset = "scratch_global_fishing_raster"
table = "fishing_effort_"+thedate

class BigQuery:

    def __init__(self):
        credentials = GoogleCredentials.get_application_default()
        self._bq = discovery.build('bigquery', 'v2', credentials=credentials)


    # XXX allow dataset/table to be optional (should probably pass in as atomic `destination`)
    # XXXX allow allowLargeResults to be optional
    # XXX check that dataset/table set if not
    # XXX ADD note that if dest table specified it is not automatically deleted
    def async_query(self, project_id, query, dataset, table,
                        batch=False, num_retries=5):
        """Create an asynchronous BigQuery query
        MOAR DOCS
        """
        # Generate a unique job_id so retries
        # don't accidentally duplicate query
        job_data = {
            'jobReference': {
                'projectId': project_id,
                'job_id': str(uuid.uuid4())
            },
            'configuration': {
                'query': {
                    'allowLargeResults': 'true',
                    'writeDisposition':'WRITE_TRUNCATE', #overwrites table
                    'destinationTable' : {
                      "projectId": project_id,
                      "datasetId": dataset,
                      "tableId": table,
                      },
                    'query': query,
                    'priority': 'BATCH' if batch else 'INTERACTIVE'
                }
            }
        }
        return self._bq.jobs().insert(
            projectId=project_id,
            body=job_data).execute(num_retries=num_retries)


    def poll_job(self, job, max_tries=4000):
        """Waits for a job to complete."""

        request = self._bq.jobs().get(
            projectId=job['jobReference']['projectId'],
            jobId=job['jobReference']['jobId'])

        trial = 0
        while trial < max_tries:
            result = request.execute(num_retries=2)

            if result['status']['state'] == 'DONE':
                if 'errorResult' in result['status']:
                    raise RuntimeError(result['status']['errorResult'])
                return

            time.sleep(1)
            trial += 1

        raise RuntimeError("timeout")


    def async_extract_query(self, job, path, format="CSV", compression="GZIP",
                                                        num_retries=5):
        """Extracts query specified by job into Google Cloud storage at path
        MOAR docs
        """

        job_data = {
          'jobReference': {
              'projectId': job['jobReference']['projectId'],
              'jobId': str(uuid.uuid4())
          },
          'configuration': {
              'extract': {
                  'sourceTable': {
                      'projectId': job['configuration']['query']['destinationTable']['projectId'],
                      'datasetId': job['configuration']['query']['destinationTable']['datasetId'],
                      'tableId': job['configuration']['query']['destinationTable']['tableId'],
                  },
                  'destinationUris': [path],
                  'destinationFormat': format,
                  'compression': compression
              }
          }
        }
        return self._bq.jobs().insert(
            projectId=job['jobReference']['projectId'],
            body=job_data).execute(num_retries=num_retries)


def gs_mv(src_path, dest_path):
    """Move data using gsutil
    This was written to move data from cloud
    storage down to your computer and hasn't been
    tested for other things.
    Example:
    gs_mv("gs://world-fishing-827/scratch/SOME_DIR/SOME_FILE",
                "some/local/path/.")
    """
    subprocess.call(["gsutil", "-m", "mv", src_path, dest_path])


# this function is to get the approximate area of a grid cell, 
# which can be used to normalize density. It currently isn't used
def get_area(lat):
    lat_degree = 69 # miles
    # Convert latitude and longitude to 
    # spherical coordinates in radians.
    degrees_to_radians = math.pi/180.0        
    # phi = 90 - latitude
    phi = (lat+cellsize/2.)*degrees_to_radians #plus half a cell size to get the middle
    lon_degree = math.cos(phi)*lat_degree 
    # return 69*69*2.6
    return  lat_degree*lon_degree* 2.58999 # miles to square km




# Execute the query, move the table to gcs, then download it
# as a zipped csv file

gcs_path = "gs://david-scratch/"+table+".zip"
local_path = path_to_csv_zip+table+".zip"


import os.path
if not os.path.isfile('../data/dailytables/fishing_vessel_effort/zips/fishing_effort_'+thedate+".zip"): 
    print thedate
    bigq = BigQuery()
    query_job = bigq.async_query(proj_id, query, dataset, table)
    bigq.poll_job(query_job)
    extract_job = bigq.async_extract_query(query_job, gcs_path)
    bigq.poll_job(extract_job)
    gs_mv(gcs_path, local_path)


# Now read the csv file into a grid and create a tiff

# .1 degree grid

if not os.path.isfile("../data/dailytables/fishing_vessel_effort/tiffs/"+yyyy+"-"+mm+"-"+dd+".tif"): 
    print yyyy+"-"+mm+"-"+dd
    one_over_cellsize = 10
    cellsize = .1
    num_lats = 180 * one_over_cellsize
    num_lons = 360 * one_over_cellsize

    vessel_hours = np.zeros(shape=(num_lats,num_lons))
    #vessel_hours = np.zeros(shape=(num_lats,num_lons))

    with gzip.open(path_to_csv_zip+table+".zip", 'rb') as f:
        reader = csv.DictReader(f)
        for row in reader:
            lat = int(row['lat_bin'])
            lon = int(row['lon_bin'])   
            if lat<90*one_over_cellsize and lat>-90*one_over_cellsize and lon>-180*one_over_cellsize and lon<180*one_over_cellsize:
                lat_index = lat+90*one_over_cellsize
                lon_index = lon+180*one_over_cellsize
                hours = float(row['hours'])
                vessel_hours[lat_index][lon_index] = hours
                # area = get_area(lat*float(cellsize)) # approximate area of 1 by 1 degree at a given lat
                # vessel_density[lat_index][lon_index] = hours / (24.* area*cellsize*cellsize) #vessels per square km

    profile = {
        'crs': 'EPSG:4326',
        'nodata': -9999,
        'dtype': rio.float32,
        'height': num_lats,
        'width': num_lons,
        'count': 1,
        'driver': "GTiff",
        'transform': affine.Affine(float(cellsize), 0, -180, 
                                   0, -float(cellsize), 90),
        'TILED': 'YES',
        'BIGTIFF': 'NO',
        'INTERLEAVE': 'BAND',
        'COMPRESS': 'DEFLATE',
        'PREDICTOR': '3'
    }


    out_tif = yyyy+"-"+mm+"-"+dd+".tif"

    with rio.open(path_to_tiff + out_tif, 'w', **profile) as dst:
        dst.write(np.flipud(vessel_hours).astype(profile['dtype']), indexes=1)
