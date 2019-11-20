#!/bin/bash -e
set -o nounset

# Get the directory where current script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

USAGE="$0 <FLAGS> <dataset_dir>

Decompresses select data types of Creative Flow+ Data.
Here, dataset_dir contains:
scene_name0/cam0/meta
scene_name0/cam0/renders
scene_name1/cam0/meta
scene_name1/cam0/renders
...
as produced by pipeline.sh

***
Note:
Core dataset metadata may not include all the files that can be decompressed
here. If downloading a supplement, you can simply rsync the supplement directory
into the core directory to ensure that scene_name0/cam0/meta contains both core
and supplementary metadata files for each scene,cam pair.

***
Flags:
-h help

-o output directory (required), where will create output of the format
   scene_name0/cam0/decomp/meta/alpha
   scene_name0/cam0/decomp/meta/flow
   scene_name0/cam0/decomp/meta/<meta requested with -m>
   scene_name0/cam0/decomp/renders/composite
   scene_name0/cam0/decomp/renders/line/line_style_name
   scene_name0/cam0/decomp/renders/line/line_style_name.alpha
   scene_name0/cam0/decomp/renders/<renders requested with -r>

-m which metadata to decompress, encoded as a string of chars, e.g. 'afo' :
   a - alpha             (core dataset)
   b - back_flows        (supplementary)
   c - correspondences   (core; lossless in supplementary)
   d - depth (arrays)    (supplementary)
   D - depth (images)    (core)
   f - flows             (core)
   i - object ids        (core)
   n - normals           (core; lossless in supplementary)
   o - occlusion maps    (core)
   r - original renders  (core)

-r which renders to decompress, encoded as a string of chars, e.g. 'CLl' :
   C - composite renders
   L - line renders
   l - line alpha renders (i.e. encode line transparency for custom compositing)
   S - shading renders (alpha here is the same as metadata alpha)

-S <sanity fraction> check metadata sanity (requires uncompressing at least -m acfio)

-H hard skip scenes that already have an entry in the output directory (this is
   useful if e.g. decompression fails and needs to be restarted)

-N run without confirmation
"

UMETA=''  # 'acDfinor'
URENDER=''  # 'C'
CHECK_SANITY=0
MIN_SANITY=0
SKIP_EXISTING=0
CONFIRM=1

while getopts ':ho:m:r:S:HN' option; do
    case "$option" in
        h) echo "$USAGE"
           exit
           ;;
        o) ODIR=$OPTARG
           echo "Setting output directory to $ODIR"
           ;;
        m) UMETA=$OPTARG
           echo "Setting meta decompression to $OPTARG"
           ;;
        r) URENDER=$OPTARG
           echo "Setting rendering decompression to $OPTARG"
           ;;
        S) MIN_SANITY=$OPTARG
           CHECK_SANITY=1
           echo "Requesting a sanity check with min sanity $MIN_SANITY"
           ;;
        H) SKIP_EXISTING=1
           echo "Skipping sequences with entries in the output directory"
           ;;
        N) CONFIRM=0
           echo "Skipping confirmation"
           ;;
        \?) printf "ERROR! illegal option: -%s\n" "$OPTARG" >&2
            echo "$USAGE" >&2
            exit 1
            ;;
    esac
done
shift $((OPTIND - 1))

if [ -z ${ODIR+x} ]; then
    echo "ERROR: Must set -o flag for output directory"
    exit 1
fi

DATADIR=$1

if [[ "$ODIR" = *[[:space:]]* ]]; then
  echo "ERROR: sorry, this script is not robust to filenames with spaces ('$ODIR')."
  echo "Please try another output location, or create a symlink (untested)."
  exit 1
fi

if [[ "$DATADIR" = *[[:space:]]* ]]; then
  echo "ERROR: sorry, this script is not robust to filenames with spaces ('$DATADIR')."
  echo "Please move to another location, or create a symlink (untested)."
  exit 1
fi

if [[ "$SCRIPT_DIR" = *[[:space:]]* ]]; then
  echo "ERROR: sorry, this script is not robust to filenames with spaces ('$SCRIPT_DIR')."
  echo "Please move to another location."
  exit 1
fi

DIRS=$(ls "$DATADIR")
NDIRS=$(ls -1 "$DATADIR" | wc -l | awk '{printf "%s", $1}')
echo "----------------------------------------------------------------"
echo " Decompressing $DATADIR"
echo
echo " Found $NDIRS clip directories, including... "

I=0
for D in $DIRS; do
    echo "   $D/"
    I=$((I + 1))
    if [ $I -gt 4 ]; then
        echo "   ..."
        break
    fi
done

echo " Will write output to $ODIR, creating directories such as..."
I=0
for D in $DIRS; do
    echo "   $ODIR/$D/"
    I=$((I + 1))
    if [ $I -gt 4 ]; then
        echo "   ..."
        break
    fi
done

if [ $CONFIRM -eq "1" ]; then
    read -p "Continue [y/n]? " RESP
    echo
    if [[ ! $RESP =~ ^[Yy]$ ]]; then
        echo "... Exiting ..."
        exit 1
    fi
fi

function decompress_mp4 {
    echo "   > Decompressing $1 to $2"
    if [ ! -f "$1" ]; then
        echo "     --> FAIL: file not found $1"
        exit 1
    fi
    "$SCRIPT_DIR"/mp4_to_frames.sh "$1" "$2"
    echo "     --> OK"
}

function decompress_mp4s_dir {
    VIDEOS=$(find "$1" -name "*${3}.mp4" \( ! -name "*${4}*" \))
    for V in $VIDEOS; do
        BNAME=$(basename "$V" | awk '{gsub(/\.mp4/, ""); printf "%s", $1}')
        decompress_mp4 "$V" "$2/$BNAME/frame%06d.png"

        X=$(find "$1" -name "*${BNAME}*LICENSE.txt")
        if [ -n "$X" ]; then
            cp "$X" "$2/$BNAME/LICENSE.txt"
            echo "     --> OK: got license"
        fi
    done
}

function decompress_special_zip {
    echo "   > Decompressing $2 to $3"
    if [ ! -f "$2" ]; then
        echo "     --> FAIL: file not found $2"
        exit 1
    fi
    mkdir -p $(dirname "$3")
    "$SCRIPT_DIR"/../blender/decompress_packed_zip_main.py \
                 --input_type="$1" \
                 --input_zip="$2" \
                 --output_pattern="$3"
    echo "     --> OK"
}

function decompress_zip {
    echo "   > Decompressing $1 to $2"
    if [ ! -f "$1" ]; then
        echo "     --> FAIL: file not found $1"
        exit 1
    fi
    mkdir -p "$2"
    unzip -o "$1" -d "$2" > /dev/null
    echo "     --> OK"
}

echo "----------------------------------------------------------------"

N_MISSING_FILES=0
for D in $DIRS; do
    if [ "$SKIP_EXISTING" -eq 1 ] && [ -d "$ODIR/$D" ]; then
        echo "Hard-skipping sequence: $D"
        continue
    fi

    HAS_MISSING_FILES=0
    CAMS=$(find "$DATADIR/$D" -mindepth 1 -maxdepth 1 -type d -name "cam*" -exec realpath --relative-to "$DATADIR/$D" {} \;)
    for C in $CAMS; do
        INBASE=$DATADIR/$D/$C
        OBASE=$ODIR/$D/$C
        echo "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
        echo "Processing $INBASE ...."

        # Process metadata -----------------------------------------------------
        INMETA=$INBASE/meta
        OUTMETA=$OBASE/metadata

        if [[ "$UMETA" == *a* ]]; then
            decompress_mp4 "$INMETA/alpha.mp4" "$OUTMETA/alpha/alpha%06d.png"
        fi

        if [[ "$UMETA" == *b* ]]; then
            if [ -f "$INMETA/backflow.zip" ]; then
                decompress_special_zip "FLOW" "$INMETA/backflow.zip" "$OUTMETA/backflow/backflow%06d.flo"
            else
                echo "     ---> WARN: missing $INMETA/backflow.zip"
                HAS_MISSING_FILES=1
            fi
        fi

        if [[ "$UMETA" == *c* ]]; then
            if [ -f "$INMETA/corresp_lossless.zip" ]; then
                decompress_special_zip "PNG" "$INMETA/corresp_lossless.zip" "$OUTMETA/corresp/corr%06d.png"
            else
                decompress_mp4 "$INMETA/corresp.mp4" "$OUTMETA/corresp/corr%06d.png"
            fi
        fi

        if [[ "$UMETA" == *d* ]]; then
            decompress_special_zip "ARRAY" "$INMETA/depth.zip" "$OUTMETA/depth/depth%06d.array"
        fi

        if [[ "$UMETA" == *D* ]]; then
            decompress_mp4 "$INMETA/depthimg.mp4" "$OUTMETA/depthimg/depth%06d.png"
            cp "$INMETA/depth.range.txt" "$OUTMETA"/depthimg/.
        fi

        if [[ "$UMETA" == *f* ]]; then
            if [ -f "$INMETA/flow.zip" ]; then
                decompress_special_zip "FLOW" "$INMETA/flow.zip" "$OUTMETA/flow/flow%06d.flo"
            else
                echo "     ---> WARN: missing $INMETA/flow.zip"
                HAS_MISSING_FILES=1
            fi
        fi

        if [[ "$UMETA" == *i* ]]; then
            decompress_zip "$INMETA/objectids.zip" "$OUTMETA/objectid"
        fi

        if [[ "$UMETA" == *n* ]]; then
            if [ -f "$INMETA/normals_lossless.zip" ]; then
                decompress_special_zip "PNG" "$INMETA/normals_lossless.zip" "$OUTMETA/normals/normal%06d.png"
            else
                decompress_mp4 "$INMETA/normals.mp4" "$OUTMETA/normals/normal%06d.png"
            fi

        fi

        if [[ "$UMETA" == *o* ]]; then
            if [ -f "$INMETA/occlusions.mp4" ]; then
                decompress_mp4 "$INMETA/occlusions.mp4" "$OUTMETA/occlusions/occlusions%06d.png"
            else
                echo "     ---> WARN: missing $INMETA/occlusions.mp4"
                HAS_MISSING_FILES=1
            fi
        fi

        if [[ "$UMETA" == *r* ]]; then
            decompress_mp4 "$INMETA/original.mp4" "$OUTMETA/original_render/frame%06d.png"
        fi

        # Process renders -----------------------------------------------------
        INRENDER=$INBASE/renders
        OUTRENDER=$OBASE/renders

        if [[ "$URENDER" == *C* ]]; then
            decompress_mp4s_dir "$INRENDER/composite" "$OUTRENDER/composite" "" "mockexclude"
        fi

        if [[ "$URENDER" == *L* ]]; then
            decompress_mp4s_dir "$INRENDER/lines" "$OUTRENDER/lines" "" "alpha"
        fi

        if [[ "$URENDER" == *l* ]]; then
            decompress_mp4s_dir "$INRENDER/lines" "$OUTRENDER/lines" "alpha" "mockexclude"
        fi

        if [[ "$URENDER" == *S* ]]; then
            decompress_mp4s_dir "$INRENDER/shading" "$OUTRENDER/shading" "" "mockexclude"
        fi
    done
    if [ $HAS_MISSING_FILES -eq "1" ]; then
        N_MISSING_FILES=$((N_MISSING_FILES + 1))
    fi
done

# Handle licenses
echo "----------------------------------------------------------------"
echo "Processing LICENSE.txt files"
for LIC in $(find "$DATADIR" -name "LICENSE.txt" -exec realpath --relative-to "$DATADIR" {} \;); do
  OUT_LICENSE=$ODIR/$LIC
  echo "   > Copying License: $DATADIR/$LIC to $OUT_LICENSE"

  LIC_DIR=$(dirname "$OUT_LICENSE")
  mkdir -p "$LIC_DIR"
  cp "$DATADIR/$LIC" "$OUT_LICENSE"
done

if [ $N_MISSING_FILES -gt "0" ]; then
    echo "NOTE: $N_MISSING_FILES out of $NDIRS scenes are missing files related to flow (see our errata on why this may be)"
    if [ $N_MISSING_FILES -gt $((NDIRS / 10)) ]; then
        echo "FAIL: too many scenes are missing required files; did you unzip those packages?"
        exit 1
    fi
fi


if [ "$CHECK_SANITY" -eq "1" ]; then
    echo "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
    echo " Checking metadata sanity "
    echo "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
    echo

    SANEDIR=$ODIR/.sanity_checks
    mkdir -p "$SANEDIR"
    echo "Logs: $SANEDIR"
    echo
    for D in $DIRS; do
        CAMS=$(ls -1 "$DATADIR/$D")

        for C in $CAMS; do
            OBASE=$ODIR/$D/$C
            OUTMETA=$OBASE/metadata

            echo "Checking $D/$C ...."

            LOGFILE=$SANEDIR/${D}_${C}_sanity_log.txt
            DEBUG_SANITY_IMG=$SANEDIR/${D}_${C}_sanity_debug_img.png
            echo "         $LOGFILE"
            echo "         $DEBUG_SANITY_IMG"
            "$SCRIPT_DIR"/../blender/check_sanity_main.py \
                         --flow_pattern="$OUTMETA/flow/*.flo" \
                         --objectid_pattern="$OUTMETA/objectid/*.png" \
                         --corresp_pattern="$OUTMETA/corresp/*.png" \
                         --occlusion_pattern="$OUTMETA/occlusions/*.png" \
                         --alpha_pattern="$OUTMETA/alpha/*.png" \
                         --debug_output_file="$DEBUG_SANITY_IMG" \
                         --debug_only_on_failure \
                         --min_sanity="$MIN_SANITY" \
                         --nframes=10 --npixels=2000 > "$LOGFILE" 2>&1
            echo "       --> OK: $(tail -n1 "$LOGFILE")"
        done
    done

    echo "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
    echo "All Sanity Checks Passed"
    echo "Sanity Logs Written To: $SANEDIR"
fi

echo
echo "DECOMPRESSION SUCCESSFUL"
