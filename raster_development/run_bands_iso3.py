"""
The following script runs the daily_raster_fishing_effort_bands.py code across all countries
"""

import os
from datetime import datetime,timedelta
import subprocess


commands = []
d = datetime(2015,1,1)
# d = d + timedelta(days=1)
for i in range(365):
    # print d + timedelta(days=i)
    yyyymmdd = datetime.strftime(d + timedelta(days=i),"%Y%m%d")
    command = '''echo python daily_raster_fishing_effort_iso3_geartype_2.py {yyyymmdd}'''.format(yyyymmdd=yyyymmdd)
    commands.append(command)


all_commands = "("+";".join(commands) +") | parallel -j 16"
# print all_commands
os.system(all_commands)