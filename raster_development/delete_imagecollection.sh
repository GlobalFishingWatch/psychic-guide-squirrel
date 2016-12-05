#!/bin/bash

TABLES=$(earthengine ls users/davidk/initial-daily-density-fishing2)

for T in ${TABLES}; do
    earthengine rm $T;
    sleep .34
done 
