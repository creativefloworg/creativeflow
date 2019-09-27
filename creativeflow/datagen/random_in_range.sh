#!/bin/bash -e

set -o nounset

read RANGE

START=$(echo $RANGE | awk '{print $(NF-1)}')
END=$(echo $RANGE | awk '{print $(NF)}')

#echo "Start: $START End: $END"

DIFF=$((END-START))
if [ "$DIFF" -le "0" ]; then
    echo $START
else
    echo $((START + (RANDOM % DIFF)))
fi
