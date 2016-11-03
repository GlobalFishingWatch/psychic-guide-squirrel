"""
The following script runs the daily_raster_fishing_effort_bands.py code across all countries
"""

import os
import csv
from datetime import datetime,timedelta
import subprocess

iso3s = []

with open('topcountries.csv','rU') as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        iso3s.append(row['iso3'])


commands = []
d = datetime(2015,4,1)
# d = d + timedelta(days=1)
for i in range(30):
    # print d + timedelta(days=i)
    yyyymmdd = datetime.strftime(d + timedelta(days=i),"%Y%m%d")
    for iso3 in iso3s:
        command = '''echo python daily_raster_fishing_effort_bands.py {yyyymmdd} {iso3}'''.format(yyyymmdd=yyyymmdd,iso3=iso3)
        commands.append(command)


all_commands = "("+";".join(commands) +") | parallel -j 16"

os.system(all_commands)