#!/bin/bash
set -o nounset

BLEND_PATH=$1

OIFS="$IFS"
IFS=$'
'
BLENDS=$(find "$BLEND_PATH" -type f -name "*.blend")

k=0
for B in $BLENDS; do
    FILES[$k]=$B
    k=$((k+1))
    echo "Found blend: $B"
done
IFS=$OIFS

export CLI_COLOR=1
RED='\033[1;31m'
GREEN='\033[1;32m'
NOCOLOR='\033[0m'

for i in $(seq 0 $(($k - 1))); do
    B=${FILES[i]}

    echo "Blend: $B"

    blender --background --python-exit-code 1 --factory-startup "$B" \
            --python-expr "import bpy; bpy.ops.file.pack_all(); bpy.ops.wm.save_mainfile();"

    if [ $? -eq "0" ]; then
        echo -e "  --> $GREEN OK $NOCOLOR"
    else
        echo -e "  --> $RED FAILED: $NOCOLOR $B"
    fi
    echo
done
