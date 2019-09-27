#!/bin/bash
set -o nounset

BPTH=$1
ODIR=$2

# Ensure we can deal with files with spaces
OIFS="$IFS"
IFS=$'
'
BLENDS=$(find "$BPTH" -type f -name "*.blend")

k=0
for B in $BLENDS; do
    FILES[$k]=$B
    k=$((k+1))
done
IFS=$OIFS

mkdir -p "$ODIR/models"
mkdir -p "$ODIR/models_needcam"
FINFO=$ODIR/fileinfo.txt
NEEDCAM=$ODIR/needcam.txt

for i in $(seq 0 $(($k - 1))); do
    B=${FILES[i]}
    echo "Processing file $B"

    blender "$B"

    echo "Keep [y/N]?"
    read ANS
    if [ "$ANS" == "y" ] || [ "$ANS" == "Y" ]; then
        SRC=$(basename $(dirname $(dirname "$B")))
        ONAME=$(basename "$B")
        ONAME="${SRC}_$ONAME"
        echo "src: $SRC"

        echo "Needs cam [y/n]?"
        read ANS

        if [ "$ANS" == "y" ] || [ "$ANS" == "Y" ]; then
            echo "Copying model: $ODIR/models_needcam/${ONAME}"
            cp "$B" "$ODIR/models_needcam/${ONAME}"
        else
            echo "Copying model: $ODIR/models/${ONAME}"
            cp "$B" "$ODIR/models/${ONAME}"
        fi

        echo "$B,$ODIR/models/${ONAME}" >> $FINFO

    else
        echo "Skipping model"
    fi

done
