#!/bin/bash -e

FLAGS=""
FRATE=12
CRF=20

USAGE="to_animation.sh <flags> frame_path/frame_pattern%06d.png output_file.mp4

Flags:
-y auto-overwrite
-f framerate
-c crf passed to ffmpeg (see https://trac.ffmpeg.org/wiki/Encode/H.264)
-d auto-detect start frame"

AUTO_START=0
while getopts ':yf:c:hd' option; do
       case "$option" in
              y) FLAGS="-y"
                 # echo "Auto overwrite"
                 ;;
              f) FRATE=$OPTARG
                 # echo "Set framerate to $FRATE"
                 ;;
              c) CRF=$OPTARG
                 # echo "Set crf to $CRF"
                 ;;
              h) echo "$USAGE"
                 exit 0
                 ;;
              d) echo "Detecting start frame automatically"
                 AUTO_START=1
                 ;;
              \?) printf "ERROR! illegal option: -%s\n" "$OPTARG" >&2
                  echo "$USAGE"
                  exit 1
                  ;;
       esac
done
shift $((OPTIND - 1))

if [ "$#" -lt 2 ]; then
    echo "$USAGE"
    exit 1
fi

FPATTERN=$1 # e.g. /tmp/out/frame%06d.png
OFILE=$2

if [ $AUTO_START -eq "1" ]; then
    BPAT=$(echo $(basename "$FPATTERN") | awk '{gsub(/%.*/, ""); print}')

    FIRST=$(ls -1 $(dirname "$FPATTERN") | grep "$BPAT" | sort -u | head -n1)
    START=$(echo $FIRST | awk '{gsub(/[^0-9]/, ""); gsub(/^[0]+/, ""); print}')
    echo "Detected first frame as $START in $FIRST"
    FLAGS="$FLAGS -start_number $START"
fi

set -x
ffmpeg $FLAGS -framerate $FRATE \
       -i "$FPATTERN" \
       -c:v libx264 -profile:v high -crf $CRF -pix_fmt yuv420p \
       "$OFILE"
set +x
# Lossless (not supported by this script):
# https://stackoverflow.com/questions/4839303/convert-image-sequence-to-lossless-movie
# https://trac.ffmpeg.org/wiki/Encode/H.264
