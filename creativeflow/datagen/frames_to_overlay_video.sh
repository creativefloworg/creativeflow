#!/bin/bash -e
set -o nounset

# Get the directory where current script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

USAGE="$0 background_img imgdir/*.png frame%06d.png <framerate> <crf> out.mp4

Composites background_img into all the input frames and encodes as mp4.

Note: background_img must already be resized."

BG_IMG=$1
FRAMEGLOB=$2
FRAMEPATTERN=$3
FRATE=$4
CRF=$5
OFILE=$6

FRAMEDIR=$(dirname "$FRAMEGLOB")
TDIR=$FRAMEDIR/bgframes$RANDOM

mkdir -p $TDIR

# Composite images with the background
for FRR in $($(which ls) $FRAMEGLOB); do
    OFRR=$TDIR/$(basename $FRR)
    composite -dissolve 100 -gravity center -alpha Set \
              $FRR $BG_IMG $OFRR
done

# Create animation
$SCRIPT_DIR/to_animation.sh -y -f $FRATE -c 20 $TDIR/$FRAMEPATTERN $OFILE

rm -rf $TDIR


# ------------------------------------------------------------------------------
# Note: ffmpeg actually has built-in compositing, and the following command does
# all in ffmpeg 3.4. However, the encoded video is malformed with ffmpeg 2.8, the
# standard version bundled with Ubuntu 16.04. We could not figure out an ffmpeg
# command modification that would work with this earlier version, and instead
# use the above workaround.
#
# Alternative for ffmpeg >= 3.4:
#
# ffmpeg -framerate $FRATE -i $BG_IMG \
#        -framerate $FRATE -i $FRAMEDIR/$FRAMEPATTERN \
#        -filter_complex "overlay=0:0" \
#        -c:v libx264 -profile:v high -crf $CRF \
#        -pix_fmt yuv420p $OFILE
