#!/bin/bash

TABLES=$(bq ls --max_results 10000 pipeline_classify_logistic_661b_bined  | grep TABLE | pyin 'line.strip().split()[0]')

for T in ${TABLES}; do
    echo python daily_raster_fishing_effort.py ${T}
done | parallel -j 16 
