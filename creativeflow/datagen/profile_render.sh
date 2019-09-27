#!/bin/bash

set -o nounset
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd $SCRIPT_DIR/..

USAGE="$0 <blends> <odir>

Runs first stage of the pipeline on the input blends; prints time and status.
"

if [ $# -ne "2" ]; then
    echo "$USAGE"
    exit
fi

BLEND_PATH=$1
ODIR=$2
RESDIR=$ODIR/results
LDIR=$ODIR/logs
mkdir -p $RESDIR
mkdir -p $LDIR

LAST_TIME=$(date '+%N')
DATEUTIL=date
if ! [[ $LAST_TIME =~ ^[0-9]+$ ]]; then
    echo "Date seems to not work ok (Mac OS?): date '+%N' is not a number; trying gdate."
    command -v gdate > /dev/null
    if [ $? -ne "0" ]; then
        echo "ERROR: Command 'gdate' is not available. If on a Mac, can install gdate instead."
        exit 1
    fi
    DATEUTIL=gdate
fi

function start_timing {
    LAST_TIME=$($DATEUTIL +%s)
}
start_timing

function report_status {
    local NOW=$($DATEUTIL +%s)
    local ELAPSED=$((NOW - LAST_TIME))
    local ELAPSED=$($DATEUTIL -d@$ELAPSED -u +%H:%M:%S)
    start_timing

    if [ $1 -eq "0" ]; then
        echo "Status: OK $ELAPSED"
    else
        echo "Status: FAILED $ELAPSED"
    fi
}

# Ensure we can deal with files with spaces
OIFS="$IFS"
IFS=$'
'
BLENDS=$(find $BLEND_PATH -type f -name "*.blend")

k=0
for B in $BLENDS; do
    FILES[$k]=$B
    k=$((k+1))
done
IFS=$OIFS

for i in $(seq 0 $(($k - 1))); do
    BLENDFILE=${FILES[i]}
    NAME=$(basename "$BLENDFILE")
    FNAME="${NAME%.*}"
    FNAME=${FNAME// /_}

    LOG=$LDIR/${FNAME}_log.txt
    echo "Blend: $BLENDFILE"
    echo "Log: $LOG"

    start_timing
    datagen/pipeline.sh -s :0:1: \
                        -n 1 -N 0 -c 1 \
                        "$BLENDFILE" $RESDIR \
                        "--bg_name=STYMO_BG" \
                        > $LOG 2>&1
    report_status $?
done

echo "Finished"
