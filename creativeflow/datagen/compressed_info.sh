#!/bin/bash -e

set -o nounset

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

USAGE="$0 <directory> <output_directory>

Gets compressed flow info for a number of blends.

E.g.:
$0 \
DATADIR/dataset_compressed/test/mixamo
DATADIR/dataset_info/test/mixamo/
"

if [ $# -ne "2" ]; then
    echo "$USAGE"
    exit
fi

INDIR=$1
ODIR=$2
OBJDIR=""
if [ $# -gt "2" ]; then
    OBJDIR=$3
fi

LOG=/tmp/info_log.txt

NPROC=0
for F in $($(which ls) "$INDIR/*/cam*/meta/flow.zip"); do
    NPROC=$((NPROC + 1))
    echo "Getting info for ($NPROC): $F"
    echo "Log: $LOG"
    CAM=$(basename $(dirname $(dirname $F)))
    NAME=$(basename $(dirname $(dirname $(dirname $F))))
    OFILE=$ODIR/${NAME}_${CAM}_flowinfo.txt
    echo "Ofile: $OFILE"

    if [ -f $OFILE ]; then
        echo "...skipping -> ofile exists..."
    else
        echo "...processing..."
        IDS=""
        if [ ! -z $OBJDIR ]; then
            # Note: only works for the data in the pipeline directory
            IDS=" --objiddir=$OBJDIR/$NAME/$CAM/metadata/objectid"
        fi

        ${SCRIPT_DIR}/../blender/compressed_info_main.py \
                     --flowzip=$F $IDS --out_file=$OFILE > $LOG 2>&1
    fi
done

