#!/bin/bash -e
set -o nounset

# Get the directory where current script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

USAGE="$0 imgdir/*.png frame%06d.png <framerate> out.mp4"

FRAMEGLOB=$1
FRAMEPATTERN=$2
FRATE=$3
OFILE=$4

FRAMEDIR=$(dirname "$FRAMEGLOB")
TDIR=$FRAMEDIR/alpha$RANDOM

mkdir -p "$TDIR"

# First we extract the alpha component of all the images
# echo "Extracting alpha to $TDIR"
${SCRIPT_DIR}/frames_to_alpha.sh "$FRAMEGLOB" "$TDIR"
# echo "Extracted alpha to $TDIR"

# Then encode as an mp4
$SCRIPT_DIR/to_animation.sh -y -f $FRATE -c 20 "$TDIR/$FRAMEPATTERN" "$OFILE"

rm -rf $TDIR
