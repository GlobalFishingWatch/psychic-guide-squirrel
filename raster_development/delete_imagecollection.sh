#!/bin/bash

TABLES=$(earthengine ls projects/globalfishingwatch/WLD)

for T in ${TABLES}; do
    earthengine rm $T;
    sleep .34
done 
