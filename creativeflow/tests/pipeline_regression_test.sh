#!/bin/bash

set -o nounset

# Get the directory where current script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

USAGE="$0 [optional flags] <optional_output_dir> <optional_start_phase>

Runs regression test for the entire data generation pipeline, pipeline.sh.

Flags:
-h print help
-y skip confirmations
"

ALWAYS_CONTINUE=0
while getopts ':hy' option; do
    case "$option" in
        h) echo "$USAGE"
           exit
           ;;
        y) ALWAYS_CONTINUE=1
           echo "Skipping interactive confirmations"
           ;;
        \?) printf "ERROR! illegal option: -%s\n" "$OPTARG" >&2
            echo "$USAGE" >&2
            exit 1
            ;;
    esac
done
shift $((OPTIND - 1))

# Utils ------------------------------------------------------------------------

export CLI_COLOR=1
RED='\033[1;31m'
GREEN='\033[1;32m'
NOCOLOR='\033[0m'

# echo -e "\033[0;32mCOLOR_GREEN\t\033[1;32mCOLOR_LIGHT_GREEN"
# echo -e "\033[0mCOLOR_NC (No color)"
# echo -e "$GREEN LIGHT GREEN $NOCOLOR"
# exit

function continue_anyway {
    if [ $ALWAYS_CONTINUE -eq "1" ]; then
        echo "... Continuing without confirmation ..."
    else
        read -p "Continue [y/n]? " RESP
        echo
        if [[ ! $RESP =~ ^[Yy]$ ]]; then
            echo "... Exiting ..."
            exit 1
        fi
    fi
}

LAST_TIME=$(date '+%N')
DATEUTIL=date
if ! [[ $LAST_TIME =~ ^[0-9]+$ ]]; then
    echo "Date seems to not work ok (Mac OS?): date '+%N' is not a number; trying gdate."
    command -v gdate > /dev/null
    if [ $? -ne "0" ]; then
        echo "ERROR: Command 'gdate' is not available. If on a Mac, can install gdate instead."
        exit 1
    fi
    DATEUTIL=gdate
fi

function start_timing {
    LAST_TIME=$($DATEUTIL +%s)
}
start_timing

NFAILURES=0
function report_status {
    local PREFIX=""
    if [ $# -gt "2" ]; then
        PREFIX=$3
    fi

    local NOW=$($DATEUTIL +%s)
    local ELAPSED=$((NOW - LAST_TIME))
    local ELAPSED=$($DATEUTIL -d@$ELAPSED -u +%H:%M:%S)
    start_timing

    if [ $1 -eq "0" ]; then
        echo -e "$PREFIX $GREEN RAN OK $NOCOLOR $ELAPSED"
    else
        echo -e "$PREFIX $RED FAILED --> see Log $NOCOLOR"
        NFAILURES=$((NFAILURES + 1))

        if [ $2 -eq "1" ]; then
            echo "... Terminating test"
            exit 1
        fi
    fi
}


# Set necessary variables ------------------------------------------------------

NCAM=1  # TODO: add 2nd camera to blends to ensure sanity always passes
BSTYLES=2
SSTYLES=2
WIDTH=750
MAXFRAMES=10
MIN_SANITY=0.8

# Style assets are all for train set (test set assets are not public)
export ABCV_LINESTYLES=$SCRIPT_DIR/../assets/train/styles.blend
export ABCV_MATS=${SCRIPT_DIR}/../assets/train/styles.blend
export ABCV_BACKGROUNDS=${SCRIPT_DIR}/data/backgrounds/file_list.txt
export ABCV_BACKGROUND_DIR=${SCRIPT_DIR}/data/backgrounds/img
export ABCV_STYLIT_STYLES=${SCRIPT_DIR}/../assets/train/stylit_styles

# Use prepared test blends
BLENDS=$SCRIPT_DIR/data/blends #debug_blends/square_focallength.blend
BLENDLIST="$($(which ls) -1 $BLENDS)"

# Output directory
if [ $# -gt 0 ]; then
    ODIR=$1
elif [ -z ${TMPDIR+x} ]; then
    ODIR=$SCRIPT_DIR/.tmp_test_output
    echo "ERROR: \$TMPDIR variable not set; outputting to: $ODIR"
    continue_anyway
else
    ODIR=$TMPDIR/cartoon_flow_test_output${RANDOM}
fi

RESDIR=$ODIR/results
LOGDIR=$ODIR/logs

# Check blender version --------------------------------------------------------
command -v blender > /dev/null
if [ $? -ne "0" ]; then
    echo "ERROR: Command 'blender' is not available. Requires Blender 2.79."
    exit 1
fi

BVERSION=$(blender --version | head -n1)
echo $BVERSION | grep "2.79"
if [ $? -ne "0" ]; then
    echo "ERROR: Blender version 2.79 required; instead detected $BVERSION"
    continue_anyway
fi

# Check other required commands ------------------------------------------------
command -v ffmpeg  > /dev/null
if [ $? -ne "0" ]; then
    echo "ERROR: Command 'ffmpeg' is not available. Requires Ffmpeg 2.8 (best >3)."
    exit 1
fi

command -v convert  > /dev/null
if [ $? -ne "0" ]; then
    echo "ERROR: Command 'convert' is not available. Ensure imagemagick is installed."
    exit 1
fi

command -v composite  > /dev/null
if [ $? -ne "0" ]; then
    echo "ERROR: Command 'composite' is not available. Ensure imagemagick is installed."
    exit 1
fi

command -v shuf  > /dev/null
if [ $? -ne "0" ]; then
    command -v gshuf > /dev/null
    if [ $? -ne "0" ]; then
        echo "ERROR: Command 'shuf' or 'gshuf' is not available. If on a Mac, can install gshuf instead."
        exit 1
    fi
fi

command -v awk  > /dev/null
if [ $? -ne "0" ]; then
    echo "ERROR: Command 'awk' is not available. Please install."
    exit 1
fi


# Check that virtualenv is enabled ---------------------------------------------
python -c $'import sys;\nif not hasattr(sys, "real_prefix") and (not hasattr(sys, "base_prefix") or sys.base_prefix == sys.prefix):\n  raise RuntimeError()\n' 2>/dev/null && INVENV=1 || INVENV=0
if [ "$INVENV" -ne "1" ]; then
    echo "WARNING: Not in virtualenv. Running the script requires requirements.pip to be installed."
    continue_anyway
fi

# Check if stylit binary is present --------------------------------------------

if [ -z ${STYLIT_BINARY+x} ]; then
    echo "WARNING: STYLIT_BINARY variable is not set; unable to test stylit stylization"
    echo
    echo "Note: StylIt binary is not publicly available, contact authors of: "
    echo
    echo "'StyLit: illumination-guided example-based stylization of 3D renderings.'"
    echo "Jakub Fišer, Ondřej Jamriška, Michal Lukáč, Eli Shechtman"
    echo "Paul Asente, Jingwan Lu, Daniel Sýkora"
    echo "ACM Transactions on Graphics (TOG) 35, no. 4 (2016): 92."
    echo
    echo "for a binary that runs as: "
    echo "STYLIT_BINARY target_dir source_dir full.png normals.png ids.png style_examplar.png result.png"
    echo
    SSTYLES=0
    continue_anyway
fi

# Check for spaces in filenames -----------------------------------------------
if [[ "$ODIR" = *[[:space:]]* ]]; then
  echo "ERROR: sorry, this script is not robust to filenames with spaces ('$ODIR')."
  echo "Please try another output location, or create a symlink (untested)."
  exit 1
fi

if [[ "$SCRIPT_DIR" = *[[:space:]]* ]]; then
  echo "ERROR: sorry, this script is not robust to filenames with spaces ('$SCRIPT_DIR')."
  echo "Please move to another location."
  exit 1
fi

# Run the full pipeline 1 stage at a time, to report failures ------------------

echo "--------------------------------------------------------------------------"
echo " Regression test for benchmark data generation. "
echo "--------------------------------------------------------------------------"
echo " Test blends: $BLENDS "
echo " Styles: $ABCV_LINESTYLES"
echo " Stylit styles: $ABCV_STYLIT_STYLES"
echo " Test backgrounds: $ABCV_BACKGROUND_DIR"
echo " Num camera angles / blend: $NCAM"
echo " Num blender styles / camera angle: $BSTYLES"
echo " Num stylit styles / camera angle: $SSTYLES"
echo " Rendered frames / clip: $MAXFRAMES"
echo " Render size: $WIDTH x $WIDTH"
echo
echo " Output directory: $ODIR "
echo

START_PHASE=0
if [ $# -gt "1" ]; then
    START_PHASE=$2
    echo "Setting start phase to : $2"
fi

mkdir -p $ODIR
if [ $START_PHASE -eq "0" ]; then
    rm -rf $ODIR/*
fi

mkdir -p $RESDIR
mkdir -p $LOGDIR
for I in $(seq $START_PHASE 16); do
    LOG=$LOGDIR/log_phase${I}.txt
    echo "----------------------------------------------------------------------"
    echo " RUNNING PHASE $I: datagen/pipeline.sh -s :${I}: "
    echo " Log: $LOG "

    ${SCRIPT_DIR}/../datagen/pipeline.sh -s :${I}: \
                 -n $BSTYLES -N $SSTYLES -c $NCAM \
                 $BLENDS $RESDIR \
                 "--width=$WIDTH --height=$WIDTH --rendered_frames=$MAXFRAMES --bg_name=STYMO_BG --deterministic_objectid_colors" \
                 > $LOG 2>&1
    report_status $? 1

    if [ $I -eq "16" ]; then
        cat $LOG | grep "Sanity"
    fi
done

echo "----------------------------------------------------------------------"
echo " All phases completed. Performing additional tests. "
echo "----------------------------------------------------------------------"
echo

LOG=$LOGDIR/log_uncompress_core.txt
echo "----------------------------------------------------------------------"
echo " 1. Can we decompress all (core) output successfully ?"
echo "    Log: $LOG"

UNCOMPDIR=$RESDIR/uncompressed
mkdir -p $UNCOMPDIR
${SCRIPT_DIR}/../datagen/pipeline_decompress.sh \
             -m acDfinor -r CLlS -N -S $MIN_SANITY \
             -o $UNCOMPDIR $RESDIR/compressed > $LOG 2>&1
report_status $? 1
cat $LOG | grep Sanity
echo

echo "----------------------------------------------------------------------"
echo " 2. Do original and uncompressed (core) outputs agree ?"

for B in $BLENDLIST; do
    BNAME=$(echo $(basename $B) | awk '{gsub(/\.blend/, ""); printf "%s", $1}')
    for C in $(seq 0 $((NCAM - 1))); do
        LOG=$LOGDIR/check_core_${BNAME}_$C.txt
        echo " > Checking $BNAME, cam $C"
        echo "   Log: $LOG"

        echo "    > Checking $BNAME/cam$C/metadata/flow"
        ${SCRIPT_DIR}/check_dir_content_similar.sh -t "0.00001" \
                     $RESDIR/pipeline/$BNAME/cam$C/metadata/flow \
                     $UNCOMPDIR/$BNAME/cam$C/metadata/flow "flo" >> $LOG 2>&1
        report_status $? 0 "      "

        echo "    > Checking $BNAME/cam$C/metadata/objectid"
        ${SCRIPT_DIR}/check_dir_content_similar.sh -t "0.00001" \
                     $RESDIR/pipeline/$BNAME/cam$C/metadata/objectid \
                     $UNCOMPDIR/$BNAME/cam$C/metadata/objectid "png" >> $LOG 2>&1
        report_status $? 0 "      "

        for D in "alpha" "corresp" "depthimg" "normals" "occlusions"; do
            echo "    > Checking $BNAME/cam$C/metadata/$D"
            ${SCRIPT_DIR}/check_dir_content_similar.sh -t "0.03" \
                         $RESDIR/pipeline/$BNAME/cam$C/metadata/$D \
                         $UNCOMPDIR/$BNAME/cam$C/metadata/$D "png" >> $LOG 2>&1
            report_status $? 0 "      "
        done

        NSTYLES=$((BSTYLES+SSTYLES))
        for R in "composite" "lines" "shading"; do
            echo "    > Checking $R renderings"
            RDIR=$UNCOMPDIR/$BNAME/cam$C/renders/$R
            if [ ! -d $RDIR ]; then
                echo -e "      $RED FAILED: $NOCOLOR cannot find directory $RDIR"
                exit 1
            fi

            NDIRS=$($(which ls) -1 $RDIR | grep -v "alpha" | wc -l | awk '{printf "%s", $1}')
            if [ $NDIRS -ne "$NSTYLES" ]; then
                echo -e "     $RED FAILED: $NOCOLOR expected $NSTYLES subdirectories; found $NDIRS in $RDIR"
                exit 1
            fi
            echo -e "      $GREEN OK: $NOCOLOR found $NDIRS subdirs in $RDIR"
        done
    done
done

LOG=$LOGDIR/log_uncompress_supp.txt
echo "----------------------------------------------------------------------"
echo " 3. Can we decompress all (supplementary) output successfully ?"
echo "    Log: $LOG"

rsync -azhrv $RESDIR/compressed_supp/ $RESDIR/compressed > /dev/null
UNCOMPDIR=$RESDIR/uncompressed
mkdir -p $UNCOMPDIR
${SCRIPT_DIR}/../datagen/pipeline_decompress.sh \
             -m bcdn -r "" -N -S $MIN_SANITY \
             -o $UNCOMPDIR $RESDIR/compressed > $LOG 2>&1
report_status $? 1
cat $LOG | grep Sanity
echo

echo "----------------------------------------------------------------------"
echo " 4. Do original and uncompressed (supplementary) outputs agree ?"

for B in $BLENDLIST; do
    BNAME=$(echo $(basename $B) | awk '{gsub(/\.blend/, ""); printf "%s", $1}')

    for C in $(seq 0 $((NCAM - 1))); do
        LOG=$LOGDIR/check_supp_${BNAME}_$C.txt
        echo " > Checking $BNAME, cam $C"
        echo "   Log: $LOG"

        echo "    > Checking $BNAME/cam$C/metadata/backflow"
        ${SCRIPT_DIR}/check_dir_content_similar.sh -t "0.00001" \
                     $RESDIR/pipeline/$BNAME/cam$C/metadata/backflow \
                     $UNCOMPDIR/$BNAME/cam$C/metadata/backflow "flo" >> $LOG 2>&1
        report_status $? 0 "      "

        for D in "corresp" "depth" "normals"; do
            echo "    > Checking $BNAME/cam$C/metadata/$D"
            ${SCRIPT_DIR}/check_dir_content_similar.sh -t "0.01" \
                         $RESDIR/pipeline/$BNAME/cam$C/metadata/$D \
                         $UNCOMPDIR/$BNAME/cam$C/metadata/$D "png" >> $LOG 2>&1
            report_status $? 0 "      "
        done
    done
done

echo "----------------------------------------------------------------------"
echo " 5. Checking against hand-checked ground truth. "

TRUTHDIR=${SCRIPT_DIR}/data/ground_truth
NCHECKS=0
for B in $BLENDLIST; do
    BNAME=$(echo $(basename $B) | awk '{gsub(/\.blend/, ""); printf "%s", $1}')

    if [ -d $TRUTHDIR/$BNAME ]; then
        LOG=$LOGDIR/check_truth_${BNAME}.txt
        echo " > Checking $BNAME against $TRUTHDIR/$BNAME"
        echo "   Log: $LOG"
        for D in $($(which ls) -1 $TRUTHDIR/$BNAME | grep -v "flowviz"); do
            TDIR=$TRUTHDIR/$BNAME/$D
            ADIR=$UNCOMPDIR/$BNAME/cam0/metadata/$D
            echo "    > Checking $ADIR against $TDIR"
            ${SCRIPT_DIR}/check_dir_content_similar.sh -r -o -t "0.02" \
                         $TDIR $ADIR "png" >> $LOG 2>&1
            report_status $? 0 "      "
            NCHECKS=$((NCHECKS+1))
        done
    else
        echo " > Skipping $BNAME; no ground truth in $TRUTHDIR"
    fi
done

if [ $NCHECKS -eq "0" ]; then
    echo -e " FAILED: no ground truth found $NOCOLOR in $TRUTHDIR for blends in $BLENDS"
    exit 1
fi

if [ $NFAILURES -eq 0 ]; then
    LOG=$LOGDIR/log_phase17.txt
    echo "----------------------------------------------------------------------"
    echo " RUNNING CLEANUP PHASE 17: datagen/pipeline.sh -s :17: "
    echo " Log: $LOG "

    ${SCRIPT_DIR}/../datagen/pipeline.sh -s :17: \
                 -n $BSTYLES -N $SSTYLES -c $NCAM \
                 $BLENDS $RESDIR \
                 "--width=$WIDTH --height=$WIDTH --rendered_frames=$MAXFRAMES --bg_name=STYMO_BG" \
                 > $LOG 2>&1
    report_status $? 1
fi

echo
echo "----------------------------------------------------------------------"
echo
if [ $NFAILURES -eq "0" ]; then
    echo -e "$GREEN REGRESSION TEST SUCCESSFUL $NOCOLOR"
    echo " Please visually inspect results in $RESDIR/compressed"
    exit 0
else
    echo -e "$RED REGRESSION TEST FAILED $NOCOLOR"
    echo " See $NFAILURES failures reported above"
    exit 1
fi
