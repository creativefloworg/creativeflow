#!/bin/bash -e
set -o nounset

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

USAGE="preprocess_mocap.sh path_to/*.blend blend_out_dir"

BLEND_PATH=$1
ODIR=$2
TDIR=$ODIR/debug

if [ $# -gt 3 ]; then
    echo "Wrong number of input arguments"
    echo $USAGE
    exit 1
fi

# Read blends
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

echo "Found $((k - 1)) matching blends"

if [ -z ${STYMO_ENVMAPS+x} ]; then
    STYMO_ENVMAPS=${SCRIPT_DIR}/../assets/common/envmaps
    echo "> set STYMO_ENVMAPS= to override using environment maps in $STYMO_ENVMAPS"
else
    echo "> using environment maps in STYMO_ENVMAPS=$STYMO_ENVMAPS"
fi

# Process blends
mkdir -p $TDIR/out0
mkdir -p $TDIR/out1

for i in $(seq 0 $(($k - 1))); do
    B=${FILES[i]}
    echo "Processing file $B"
    FNAME=$(basename "$B")
    IMNAME="${FNAME%.*}"
    IMNAME=${IMNAME// /_}


    echo "Processing $B --> $ODIR/$FNAME.blend"
    blender --background --factory-startup "$B" \
            --python blender/render_main.py -- \
            --set_camera=0 \
            --keep_extra_cameras \
            --output_blend="$TDIR/$FNAME" \
            --width=100 --height=100 \
            --image_output_prefix=$TDIR/out0/$IMNAME \
            --rendered_frames=1 \
            --set_env_lighting_image=$STYMO_ENVMAPS \
            --use_blender_render

    blender --background --factory-startup "$TDIR/$FNAME" \
            --python blender/render_main.py -- \
            --set_camera=1 \
            --add_random_camera_motion \
            --keep_extra_cameras \
            --output_blend="$ODIR/$FNAME" \
            --width=100 --height=100 \
            --image_output_prefix=$TDIR/out1/$IMNAME \
            --rendered_frames=5 \
            --use_blender_render

done

echo "Blends written to: $ODIR"
echo "Test frames written to: $TDIR"
