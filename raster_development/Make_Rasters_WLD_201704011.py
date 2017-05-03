
# coding: utf-8

# In[5]:


import uuid
import time
import subprocess
from googleapiclient import discovery
from oauth2client.client import GoogleCredentials
import csv
import sys
import gzip
import rasterio as rio
import affine
import os.path
from datetime import datetime, timedelta
import numpy as np


# In[ ]:



thedate = sys.argv[1] 

# In[ ]:


yyyy = thedate[:4]
mm = thedate[4:6]
dd = thedate[6:8]

# In[6]:


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

proj_id = "world-fishing-827"
dataset = "scratch_global_fishing_raster"


# In[9]:


    # print d + timedelta(days=i)
#     command = '''python Make_Rasters_201704011.py {yyyymmdd}'''.format(yyyymmdd=yyyymmdd)
#     commands.append(command)

#     thedate = "20150103" 

path_to_csv_zip = "data/dailytables/fishing_vessel_effort_iso3_gears/WLD/zips/"
path_to_tif = "data/dailytables/fishing_vessel_effort_iso3_gears/tifs/"

# codes = {}
# all_codes = []
# with open('iso3.csv','rU') as csvfile:
#     reader = csv.DictReader(csvfile)
#     for row in reader:
#         iso3 = row['iso3']
#         code = row['code']
#         if iso3 not in codes:
#             codes[iso3] = []
#         codes[iso3].append(code)
#         all_codes.append(code)






query = '''
SELECT
  FLOOR(lat*10) lat_bin,
  FLOOR(lon*10) lon_bin,
  SUM(hours) hours,
  if(inferred_label is null, "unknown",inferred_label) AS label,
FROM (
  SELECT
    mmsi,
    lat,
    lon,
    hours,
    flag_iso3 AS iso3
  FROM
    [world-fishing-827:gfw_research.FAO${thedate}]
  WHERE
    measure_new_score > .5 
    and seg_id NOT IN (
    SELECT
      seg_id
    FROM
      [world-fishing-827:gfw_published.segments],
    WHERE
      valid_positions < 10
      AND satellite_positions = 0)) a
LEFT JOIN (
  SELECT
    mmsi,
    inferred_label
  FROM
    [gfw_research.vessel_info_20170405]
  WHERE
    year={yyyy}) b
ON
  a.mmsi = b.mmsi
GROUP BY
  label,
  lat_bin,
  lon_bin
ORDER BY
  label,
'''.format(thedate=thedate,yyyy=yyyy)


table = "fishing_effort_"+thedate
gcs_path = "gs://david-scratch/"+table+".zip"
local_path = path_to_csv_zip+table+".zip"

if not os.path.isfile(local_path): 
    print thedate
    bigq = BigQuery()
    query_job = bigq.async_query(proj_id, query, dataset, table)
    bigq.poll_job(query_job)
    extract_job = bigq.async_extract_query(query_job, gcs_path)
    bigq.poll_job(extract_job)
    gs_mv(gcs_path, local_path)

# one_over_cellsize = 10
# cellsize = .1
# num_lats = 180 * one_over_cellsize
# num_lons = 360 * one_over_cellsize


# profile = {
#             'crs': 'EPSG:4326',
#             'nodata': -9999,
#             'dtype': rio.float32,
#             'height': num_lats,
#             'width': num_lons,
#             'count': 6,
#             'driver': "GTiff",
#             'transform': affine.Affine(float(cellsize), 0, -180, 
#                                        0, -float(cellsize), 90),
#             'TILED': 'YES',
#             'BIGTIFF': 'NO',
#             'INTERLEAVE': 'BAND',
#             'COMPRESS': 'DEFLATE',
#             'PREDICTOR': '3'
#         }

# with gzip.open(local_path, 'rb') as f:
#     reader = csv.DictReader(f)

#     hours = {}
#     hours['trawlers'] = np.zeros(shape=(num_lats,num_lons))
#     hours['drifting_longlines'] = np.zeros(shape=(num_lats,num_lons))
#     hours['purse_seines'] = np.zeros(shape=(num_lats,num_lons))
#     hours['fixed_gear'] = np.zeros(shape=(num_lats,num_lons))
#     hours['squid_jigger'] = np.zeros(shape=(num_lats,num_lons))
#     hours['other_unknown'] = np.zeros(shape=(num_lats,num_lons))
#     for row in reader:

#         # # Read bands individually and write individually
#         # with rio.open('RGB.byte.tif') as src, \
#         #         rio.open('individual.tif', 'w', **src.profile) as dst:
#         #     for bidx in range(1, src.count + 1):
#         #         data = src.read(bidx)
#         #         dst.write(data, indexes=bidx)

#         # Kevin says You also want the GeoTIFF creation option `PHOTOMETRIC=MINISBLACK`.  
#         # If an image has 3+ bands of type Byte GDAL will assume `PHOTOMETRIC=RGB`


#         lat = int(row['lat_bin'])
#         lon = int(row['lon_bin'])   
#         if lat<90*one_over_cellsize and             lat>-90*one_over_cellsize and lon>-180*one_over_cellsize and lon<180*one_over_cellsize:
#             label = row['label']
#             if label not in ["drifting_longlines","fixed_gear","squid_jigger", "purse_seines"]:
#                 label = "other_unknown"
#             lat_index = lat+90*one_over_cellsize
#             lon_index = lon+180*one_over_cellsize
#             hours[label][lat_index][lon_index] = float(row['hours'])
            
# iso3 = "WLD"                           
# os.system("mkdir "+path_to_tif + iso3 )
# out_tif = path_to_tif + iso3 +"/"+yyyy+"-"+mm+"-"+dd+".tif"

# with rio.open(out_tif, 'w', **profile) as dst:
#     dst.write(np.flipud(hours['trawlers']).astype(profile['dtype']), indexes=1)
#     dst.write(np.flipud(hours['drifting_longlines']).astype(profile['dtype']), indexes=2)
#     dst.write(np.flipud(hours['purse_seines']).astype(profile['dtype']), indexes=3)
#     dst.write(np.flipud(hours['fixed_gear'] ).astype(profile['dtype']), indexes=4)
#     dst.write(np.flipud(hours['squid_jigger']).astype(profile['dtype']), indexes=5)
#     dst.write(np.flipud(hours['other_unknown']).astype(profile['dtype']), indexes=6)
#     # dst.write((np.flipud(vessel_hours)/2.).astype(profile['dtype']), indexes=2)


# In[5]:




# In[ ]:




# In[ ]:



