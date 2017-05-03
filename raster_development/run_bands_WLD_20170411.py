"""
The following script runs the daily_raster_fishing_effort_bands.py code across all countries
"""

import os
from datetime import datetime,timedelta
import subprocess


commands = []
d = datetime(2012,1,1)
# d = d + timedelta(days=1)
for i in range(365*3+100):
    # print d + timedelta(days=i)
    yyyymmdd = datetime.strftime(d + timedelta(days=i),"%Y%m%d")
    command = '''python Make_Rasters_WLD_201704011.py {yyyymmdd}'''.format(yyyymmdd=yyyymmdd)
    commands.append(command)


# all_commands = "("+";".join(commands) +") | parallel -j 8"
# # print all_commands
# os.system(all_commands)

    
with open('commands.txt', 'w') as f:
    f.write("\n".join(commands))
    
os.system("parallel -j 16 < commands.txt")

os.system("rm -f commands.txt")