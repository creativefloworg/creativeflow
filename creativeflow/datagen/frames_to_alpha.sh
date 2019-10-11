#!/bin/bash -e
set -o nounset

# Get the directory where current script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

USAGE="$0 imgdir/*.png odir"

FRAMEGLOB=$1
ODIR=$2

FRAMEDIR=$(dirname "$FRAMEGLOB")

mkdir -p "$ODIR"

# First we extract the alpha component of all the images
# echo "Extracting alpha to $TDIR"
for FRR in $FRAMEGLOB; do
    OFRR=$ODIR/$(basename $FRR)
    convert "$FRR" -set colorspace RGB -alpha extract "$OFRR"
done
