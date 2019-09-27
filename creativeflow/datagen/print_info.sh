#!/bin/bash -e
set -o nounset

BPTH=$1
EXTENSION="blend"

if [ "$#" -eq 2 ]; then
    EXTENSION=$2
fi

# Ensure we can deal with files with spaces
OIFS="$IFS"
IFS=$'
'
BLENDS=$(find $BPTH -type f -name "*.${EXTENSION}")

k=0
for B in $BLENDS; do
    FILES[$k]=$B
    k=$((k+1))
done
IFS=$OIFS

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"


for i in $(seq 0 $(($k - 1))); do
    B=${FILES[i]}
    echo "INFO_BLEND: $B"
    if [ "$EXTENSION" != "blend" ]; then
        blender --background --factory-startup \
                --python ${SCRIPT_DIR}/../blender/print_info.py \
                -- --import_file="$B"
    else
        blender --background --factory-startup -b "$B" \
                --python ${SCRIPT_DIR}/../blender/print_info.py
    fi
done
