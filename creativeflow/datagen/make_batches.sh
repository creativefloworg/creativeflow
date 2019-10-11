#!/bin/bash
set -o nounset

USAGE="$0 <nbatches> <input_file> <output_file_prefix>

Splits input file lines into a number of smaller files.
"

if [ $# -ne "3" ]; then
    echo "$USAGE"
    exit
fi

NBATCHES=$1
INFILE=$2
OPREF=$3

LINES=$(wc -l "$INFILE" | awk '{printf "%s", $1}')
BSIZE=$((LINES / NBATCHES))
TOTAL=0

for (( B=0; B<$NBATCHES; B++)); do
    TOTAL=$((TOTAL + BSIZE))
    head -n$TOTAL $INFILE | tail -n$BSIZE > ${OPREF}_${B}.txt
done

if [ $TOTAL -lt $LINES ]; then
    REM=$((LINES - TOTAL))
    tail -n$REM $INFILE >> ${OPREF}_$((NBATCHES-1)).txt
fi
