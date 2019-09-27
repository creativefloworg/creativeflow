#!/bin/bash -e
set -o nounset

USAGE="$0 inputfile.mp4 /path/to/output/frameprefix%06d.png"

if [ $# -lt 2 ]; then
    echo "$USAGE"
    exit
fi

INFILE="$1"
OFRAMEPATTERN="$2"

ODIR=$(dirname "$OFRAMEPATTERN")
mkdir -p "$ODIR"

# First we extract to temporary directory
TDIR=$ODIR/tmp$RANDOM
mkdir "$TDIR"

TMPPATTERN=$TDIR/$(basename "$OFRAMEPATTERN")

ffmpeg -hide_banner -loglevel panic \
       -start_at_zero -i "$INFILE" "$TMPPATTERN"

# Then do a simple convert; this ensures more consistent PNG formats
EXT=$(echo "$OFRAMEPATTERN" | awk -F'.' '{printf "%s", $NF}')
for F in $(find $TDIR -name "*.${EXT}"); do
    convert "$F" $ODIR/$(basename $F)
done

rm -rf "$TDIR"
