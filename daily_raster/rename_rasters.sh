#!/bin/bash

TABLES=$(bq ls --max_results 10000 pipeline_classify_logistic_661b_bined  | grep TABLE | pyin 'line.strip().split()[0]')

for T in ${TABLES}; do
    echo gsutil mv gs://new-benthos-pipeline/scratch/inital-daily-density/allvessels_${T:0:4}-${T:4:2}-${T:6:2}.tif gs://new-benthos-pipeline/scratch/inital-daily-density/${T:0:4}-${T:4:2}-${T:6:2}.tif
done | parallel -j 16 
