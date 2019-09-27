#!/bin/bash -e

set -o nounset

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

MAX_IDS=7
RANDPROB="0"
RUN_ID=""

USAGE="stylize.sh <flags> style_dir frame_dir norm_dir ids_dir out_dir aux_dir

Uses \$STYLIT_BINARY to stylize a directory of images, using additional metadata
provided.

Flags:
-m maximum allowed ids
-i run identifier (optional)
-r <0-100> probability of randomizing input colors (default = 0)"


while getopts ':m:r:i:' option; do
    case "$option" in
        m) MAX_IDS=$OPTARG
           echo "Set max ids to $MAX_IDS"
           ;;
        r) RANDPROB=$OPTARG
           echo "Allowing color randomization with probability $RANDPROB"
           ;;
        i) RUN_ID=$OPTARG
           ;;
        \?) printf "ERROR! illegal option: -%s\n" "$OPTARG" >&2
            echo "$USAGE" >&2
            exit 1
            ;;
    esac
done
shift $((OPTIND - 1))


STYLE_DIR=$1
FRAME_DIR=$2
NORM_DIR=$3
IDS_DIR=$4
ODIR=$5
AUXDIR=$6

mkdir -p "$ODIR"
mkdir -p "$AUXDIR"

# Are wre randomizing color?
SOURCE_ID=""
RAND_FLAG=""
if [ "$((RANDOM % 100))" -lt "$RANDPROB" ]; then
    echo "Randomizing color"
    RAND_FLAG="-r"
    SOURCE_ID="-r${RUN_ID}"
else
    echo "Keeping original color"
    MAX_IDS=2  # only have max of 2 original colors per style
fi

# Is our style color or bw?
set +e
BG=$($(which ls) $STYLE_DIR | grep "bg")
set -e
if [ -z "$BG" ]; then
    echo "Style is B/W; stylizing with one color"
    MAX_IDS=1
fi

# First, process all the IDs into a smaller set of ids
# (slow and sometimes unnecessary?)
if [ -f "$IDS_DIR/N.txt" ]; then
    echo "Assuming IDs have been processed, file exists: $IDS_DIR/N.txt"
    PROC_IDS_DIR=$IDS_DIR
else
    PROC_IDS_DIR=$AUXDIR/proc_ids$MAX_IDS
    mkdir -p "$PROC_IDS_DIR"

    if [ -f "$PROC_IDS_DIR/N.txt" ]; then
        echo "Assuming IDs have been processed, file in auxiliary ids dir exists: $PROC_IDS_DIR/N.txt"
    else
        echo "IDs have not been processed. Running processing: "
        echo "  $IDS_DIR --> $PROC_IDS_DIR"
        ${SCRIPT_DIR}/../blender/process_ids_main.py --nids=$MAX_IDS \
                     --save_colors_file="$IDS_DIR/ucolors.txt" \
                     --ids_images="$IDS_DIR/*.png" \
                     --out_dir="$PROC_IDS_DIR"
    fi
fi

echo "Processed IDs in: $PROC_IDS_DIR"
N=$(cat "$PROC_IDS_DIR/N.txt")

# Next, we create an appropriate source
SOURCE=$AUXDIR/source_$(basename "$STYLE_DIR")_$N$SOURCE_ID
if [ -d "$SOURCE" ]; then
    echo "Source directory exists; reusing: $SOURCE"
else
    mkdir "$SOURCE"

    if [ "$N" -eq "1" ]; then
        echo "Creating (B/W) source from $STYLE_DIR in $SOURCE"
        ${SCRIPT_DIR}/make_bw_source.sh $RAND_FLAG $STYLE_DIR $SOURCE
    else
        echo "Creating (color) source from $STYLE_DIR in $SOURCE"
        ${SCRIPT_DIR}/make_color_source.sh $RAND_FLAG $N $STYLE_DIR $SOURCE
    fi
fi

echo "Source for $N colors: $SOURCE"


FRAMES=$(ls "$FRAME_DIR" | awk '{gsub(/[^0-9]/, ""); print;}' | sort)
echo "Number of frames: $(ls -l "$FRAME_DIR" | wc -l)"

FRAMESBG=$AUXDIR/frames_bg
TARGET=$AUXDIR/tmptarget
mkdir -p "$TARGET"
mkdir -p "$FRAMESBG"
for F in $FRAMES; do
    RES=$ODIR/frame$F.png

    if [ -f "$RES" ]; then
        echo "FRAME $F: skipping, exists $RES"
    else
        echo "FRAME $F: processing to $RES"
        rm -rf $TARGET/*

        FRAME_PROC=$FRAMESBG/full$F.png
        if [ ! -f "$FRAME_PROC" ]; then
            echo "Creating white bg: $FRAME_PROC"
            convert $FRAME_DIR/full$F.png -background white -flatten PNG24:$FRAME_PROC
        fi
        ln -s $PROC_IDS_DIR/objectid$F.png $TARGET/ids.png
        convert $NORM_DIR/normal$F.png -depth 8 PNG24:$TARGET/normals.png
        ln -s $FRAME_PROC $TARGET/full.png
        echo "Target in: $TARGET"

        FNUM=$(echo $F | awk '{gsub(/^0*/, ""); printf "%d", $1}')
        I=$((RANDOM % 2)) #$((FNUM % 2))
        echo "./stylit $TARGET $SOURCE full.png normals.png ids.png \
                       $SOURCE/style$I.png $RES"
        if [ -z ${STYLIT_BINARY+x} ]; then
            echo "No stylit binary found; set STYLIT_BINARY="
            exit 0
        else
            ${STYLIT_BINARY} $TARGET $SOURCE full.png normals.png ids.png \
                             $SOURCE/style$I.png $RES
        fi
    fi
done
