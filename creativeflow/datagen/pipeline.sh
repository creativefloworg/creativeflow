#!/bin/bash -e
set -o nounset

# Get the directory where current script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Get current working directory
CDIR=`pwd`

SKIP_EXISTING=0
USE_STYLIT=0
NCAM=1
ONESTYLE=0 # if select at random stylit or blender style
NSTYLESB=3 # flat; toon; textured; random
NSTYLESS=0 # stylit
STAGES=:0:1:2:3:4:5:6:7:8:9:10:11:12:13:14:15:16:
MODE="train"
USERARG=""
CLEANUP=0
RANDBG=1
BGNUM=0
FRAME_BOUNDS=""

USAGE="$0 <FLAGS> <blend_path> <output_dir> <extra_flags to render_main.py (optional)>

Run the complete Creative Flow+ Dataset data generation pipeline for a number
of blend files, producing stylized renderings and ground truth flow, depth,
normals, correspondeces, objectids.

Note: requires Blender 2.79 to be available.

Note: before running this, run tests/pipeline_regression_test.sh to ensure
your set up generates data correctly.

***
Flags:
-h help

-s stages to run of the form :0:1:2:5: denotes the stages below to run (default:all)
   - 0: generate / set up n camera angles [save test frames]
   - 1: configure metadata (images and exr; 2 steps) [save test frames]
   - 2: configure shading styles [save test frames]
   - 3: configure outlines [save test frames]
   - 4: render original
   - 5: render image metadata
   - 6: render exr metadata
   - 7: render stylit base material
   - 8: render outlines
   - 9: render shading styles
   - 10_0: purge stylit cache if regenerating new style
   - 10: use stylit to stylize
   - 11: composite lines and shading (no backgrounds)
   - 12: unpack exr metadata
   - 13_0: purge backgrounds and resample
   - 13: composite backgrounds (add backgrounds)
   - 14: make ffmpeg clips and compress
   - 15: check that all the files have been written successfully
   - 16: perform sanity checks on flow/correspondence agreement
   - 17: partial pipeline data clean up (only run after 14,15)

-c number of camera angles per blend (default=$NCAM)

-n number of blender styles per camera angle (default=$NSTYLESB)

-N number of stylit styles per camera angle (default=$NSTYLESS)

-O disregard -n and -N, and use this number of random styles from either category

-r reuse existing resources

-t use test styles by default

-R force skip blends with existing result dir

-X immediately clean up raw data after compression

-d use deterministic background image order for phase :13:

-b frame bounds file, containing [normalized blendname|start_frame_offset|end_frame_offset]

***
External environment variables:
ABCV_LINESTYLES - blend file containing available freestyle linestyles;
                  e.g. assets/train/styles.blend
ABCV_MATS - blend file containing available freestyle shading styles;
            e.g. assets/train/styles.blend
ABCV_COLORS - text file containing available color themes to impact part of
              style color randomization; e.g. assets/train/colors.txt
ABCV_BACKGROUNDS - text file containing available images for background
                   compositing; e.g. tests/data/backgrounds/file_list.txt
ABCV_BACKGROUND_DIR - location of the images referenced in ABCV_BACKGROUNDS
STYLIT_BINARY - location of stylit binary (run tests/pipeline_regression_test.sh
                for explanation.

***
Sample command:

export MODE=test
export EXTRA_FLAGS=\"-t\"  # ensures that test styles are used
export BLENDS=\$DATA/test_blends
export ABCV_COLORS=\$REPO/assets/\$MODE/colors.txt
export ABCV_BACKGROUNDS=\$DATA/test_images_list.txt
export ABCV_BACKGROUND_DIR=\$DATA/images

./datagen/pipeline.sh -n 1 \$BLENDS \$ODIR \$EXTRA_FLAGS \
        \"--rendered_frames=\$MAX_FRAMES --width=50 --height=50\"
"

while getopts ':hs:c:n:N:O:rRtXdb:' option; do
    case "$option" in
        h) echo "$USAGE"
           exit
           ;;
        s) STAGES=$OPTARG
           echo "Setting stages to $OPTARG"
           ;;
        c) NCAM=$OPTARG
           echo "Using $NCAM camera angles per blend"
           ;;
        n) NSTYLESB=$OPTARG
           echo "Generating $NSTYLESB blender styles per camera angle"
           ;;
        N) NSTYLESS=$OPTARG
           if [ $NSTYLESS -gt "0" ]; then
               USE_STYLIT=1
               if [ -z ${STYLIT_BINARY+x} ]; then
                   echo "ERROR: STYLIT_BINARY not set, -N flag cannot be used (use -n only)"
                   exit 1
               fi
           fi
           echo "Generating $NSTYLESS stylit styles per camera angle"
           ;;
        O) ONESTYLE=$OPTARG
           if [ -z ${STYLIT_BINARY+x} ]; then
               echo "ERROR: STYLIT_BINARY not set, -O flag cannot be used (use -n instead)"
               exit 1
           fi
           USE_STYLIT=1
           echo "Disregarding -n and -N style counts; using $ONESTYLE random style(s) from either category"
           ;;
        r) SKIP_EXISTING=1
           echo "> skipping existing files"
           USERARG="--skip_existing_frames "
           ;;
        R) SKIP_EXISTING=2
           echo "> hard skip existing -- if any step was done; skips all steps for blend"
           ;;
        t) MODE="test"
           echo "> using test assets by default (still overridden by env variables)"
           ;;
        X) CLEANUP=1
           echo "> immediately cleaning up uncompressed results"
           ;;
        d) RANDBG=0
           echo "> use deterministic background selection"
           ;;
        b) FRAME_BOUNDS=$OPTARG
           echo "> setting frame bounds to $FRAME_BOUNDS"
           ;;
        \?) printf "ERROR! illegal option: -%s\n" "$OPTARG" >&2
            echo "$USAGE" >&2
            exit 1
            ;;
    esac
done
shift $((OPTIND - 1))

if [ "$#" -ne "2" ] && [ "$#" -ne "3" ]; then
    echo "ERROR: 2 or 3 arguments expected; $# found"
    echo "$USAGE"
    exit 1
fi

BLEND_PATH=$1
ODIR=$2
if [ $# -eq 3 ]; then
    USERARG="$USERARG $3"
    echo "User arguments: $USERARG"
fi
NSTYLES=$((NSTYLESB + NSTYLESS))
if [ $ONESTYLE -ne "0" ]; then
    NSTYLES=$ONESTYLE
fi
echo "Generating $NSTYLES total styles"

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

SHUF=shuf
set +e
command -v shuf
if [ "$?" -ne "0" ]; then
    echo "Shuf does not exist; assuming gshuf is installed instead"
    SHUF=gshuf
fi
set -e

if [[ "$STAGES" == *:2:* ]] || [[ "$STAGES" == *:3:* ]]; then
    if [ -z ${ABCV_LINESTYLES+x} ]; then
        ABCV_LINESTYLES=${SCRIPT_DIR}/../assets/$MODE/styles.blend
        echo "> set ABCV_LINESTYLES= to override using linestyles in $ABCV_LINESTYLES"
    else
        echo "> using linestyles in ABCV_LINESTYLES=$ABCV_LINESTYLES"
    fi

    if [ -z ${ABCV_MATS+x} ]; then
        ABCV_MATS=${SCRIPT_DIR}/../assets/$MODE/styles.blend
        echo "> set ABCV_MATS= to override using materials in $ABCV_MATS"
    else
        echo "> using materials in ABCV_MATS=$ABCV_MATS"
    fi

    if [ -z ${ABCV_COLORS+x} ]; then
        echo "> using random colors, set ABCV_COLORS= to set themes"
    else
        echo "> using predefined colors from ABCV_COLORS=$ABCV_COLORS for some styles"
    fi
fi

if [[ "$STAGES" == *:13:* ]]; then
    if [ -z ${ABCV_BACKGROUNDS+x} ]; then
        echo "Must set ABCV_BACKGROUNDS to a file with available images for -s 13"
        exit 1
    fi
    if [ -z ${ABCV_BACKGROUND_DIR+x} ]; then
        echo "Must set ABCV_BACKGROUND_DIR to location of background images for -s 13"
        exit 1
    fi
fi

if [[ "$USE_STYLIT" -eq "1" || "$ONESTYLE" -ne "0" ]]; then
    if [ -z ${ABCV_STYLIT_STYLES+x} ]; then
        ABCV_STYLIT_STYLES=${SCRIPT_DIR}/../assets/$MODE/stylit_styles
        echo "> set ABCV_STYLIT_STYLES= to override using stylit styles in $ABCV_STYLIT_STYLES"
    else
        echo "> using stylit styles in ABCV_STYLIT_STYLES=$ABCV_STYLIT_STYLES"
    fi
fi

function get_line_spec {
    if [ -f $1 ]; then
        cat $1 | \
            awk 'BEGIN{srand(); R=int(rand() * 100);S=0;}{S=S+$1; if (R<=S) { print }}END{print R}' | \
            head -n1
    else
        echo "--randomize_line_color"
        echo "No line requirements found: $1"
        exit 1  # TODO: remove once tested
    fi
}

function read_onestylestyle_info {
    NSTYLESB=$(cat $1 | grep "NSTYLESB" | awk '{printf "%s", $2}')
    NSTYLESS=$(cat $1 | grep "NSTYLESS" | awk '{printf "%s", $2}')
    if [ "$NSTYLESS" -gt "0" ]; then
        USE_STYLIT=1
    fi
    NSTYLES=$((NSTYLESB + NSTYLESS))
    echo "Read onestyle config with: $NSTYLESB blender styles and $NSTYLESS stylit styles"
}


# Ensure we can deal with files with spaces
OIFS="$IFS"
IFS=$'
'
BLENDS=$(find $BLEND_PATH -type f -name "*.blend")

k=0
for B in $BLENDS; do
    FILES[$k]=$B
    k=$((k+1))
    echo "Found blend: $B"
done
IFS=$OIFS


TESTFRAMES=$ODIR/pipeline/aux/testframes
WHITEBG=$ODIR/pipeline/aux/white_bg.png
mkdir -p $ODIR/pipeline/aux
mkdir -p $ODIR/pipeline/info

function make_white_bg {
    SAMPLEIMG=$1
    DIMS=$(convert $SAMPLEIMG -format "%wx%h" info:)
    convert ./assets/common/misc/white_bg.png -resize "${DIMS}^" -gravity center \
            -crop "${DIMS}+0+0" +repage $WHITEBG
}

for i in $(seq 0 $(($k - 1))); do
    BLENDFILE=${FILES[i]}
    echo "-------------------------------------------------------------"
    echo "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
    echo "Processing file $BLENDFILE"
    NAME=$(basename "$BLENDFILE")
    FNAME="${NAME%.*}"
    FNAME=${FNAME// /_}

    for (( CAM=0; CAM<$NCAM; CAM++)); do
        # Actual outputs
        BASEDIR=$ODIR/pipeline/$FNAME/cam$CAM

        if [ "$SKIP_EXISTING" -eq 2 ] && [ -d "$BASEDIR" ]; then
            echo "Hard-skipping camera $CAM for blend: $BLENDFILE"
            continue
        fi

        echo "-------------------------------------------------------------"
        echo "Processing camera $CAM for $BLENDFILE"

        FINALDIR=$ODIR/compressed/$FNAME/cam$CAM
        FINALDIR_SUPP=$ODIR/compressed_supp/$FNAME/cam$CAM

        AUXDIR=$BASEDIR/aux
        LOGDIR=$AUXDIR/logs
        METADIR=$BASEDIR/metadata
        RENDERDIR=$BASEDIR/raw_frames
        COMPOSITEDIR_NOBG=$BASEDIR/composite_frames_alpha
        COMPOSITEDIR=$BASEDIR/composite_frames

        # Final compressed outputs
        FIN_RENDERDIR=$FINALDIR/renders
        FIN_LINEDIR=$FIN_RENDERDIR/lines
        FIN_SHADEDIR=$FIN_RENDERDIR/shading
        FIN_COMPDIR=$FIN_RENDERDIR/composite
        FIN_METADIR=$FINALDIR/meta

        FIN_METADIR_SUPP=$FINALDIR_SUPP/meta

        # FINALOUT=$BASEDIR/final/meta
        # FINALOUT=$BASEDIR/final/meta/redmat.mp4   # OK
        # FINALOUT=$BASEDIR/final/meta/orig.mp4     # OK
        # FINALOUT=$BASEDIR/final/meta/alpha.mp4    # OK
        # FINALOUT=$BASEDIR/final/meta/normals.mp4  # OK
        # FINALOUT=$BASEDIR/final/meta/corresp.mp4  # OK
        # FINALOUT=$BASEDIR/final/meta/objids.zip   # OK
        # FINALOUT=$BASEDIR/final/meta/flow.zip     # OK
        # FINALOUT=$BASEDIR/final/meta/depth.zip    # OK
        # FINALOUT=$BASEDIR/final/meta/occlusions.mp4  # OK

        # Metadata
        FLOWDIR=$METADIR/flow
        BACKFLOWDIR=$METADIR/backflow
        IDXDIR=$METADIR/objectid
        NORMDIR=$METADIR/normals
        DEPTHDIR=$METADIR/depth
        DEPTHIMGDIR=$METADIR/depthimg
        CORRDIR=$METADIR/corresp
        OCCDIR=$METADIR/occlusions
        ALPHADIR=$METADIR/alpha

        # Auxiliary
        ONESTYLECONFIG=$AUXDIR/onestyle_info.txt
        BLENDDIR=$AUXDIR/blends
        REDMATDIR=$AUXDIR/frames/redmat
        EXRDIR=$AUXDIR/frames/exr
        STYLEDIR=$AUXDIR/stylit/styles

        # Raw renders
        SHADING_DIR=$RENDERDIR/shading
        LINE_DIR=$RENDERDIR/outlines

        # Composites
        ORIGDIR=$COMPOSITEDIR/style.original

        # Configured blends
        CAM_BLEND=$BLENDDIR/cam.blend
        IMGMETA_BLEND=$BLENDDIR/meta_normals_corresp.blend
        IDS_BLEND=$BLENDDIR/meta_objectids.blend
        EXRMETA_BLEND=$BLENDDIR/meta_exr.blend
        STYLIT_BLEND=$BLENDDIR/stylit.blend
        SHADING_BLEND_PREFIX=$BLENDDIR/shading
        LINE_BLEND_PREFIX=$BLENDDIR/outlines

        mkdir -p $LOGDIR
        mkdir -p $BLENDDIR

        if [[ "$STAGES" == *:0:* ]]; then
            if [ "$SKIP_EXISTING" -eq 1 ] && [ -f "$CAM_BLEND" ]; then
                echo "(STEP 0): Skipping existing $CAM_BLEND"
            else
                LOGFILE=$LOGDIR/log_stage0.txt
                echo "STEP 0: Setting up camera angle $CAM for $FNAME"
                echo "        $LOGFILE"

                echo "" > $LOGFILE
                START_FRAME_OFFSET=0
                END_FRAME_OFFSET=0
                if [ ! -z "$FRAME_BOUNDS" ]; then
                    echo " Getting frame bounds for $FNAME from $FRAME_BOUNDS" > $LOGFILE
                    NBOUNDS=$(cat $FRAME_BOUNDS | grep "$FNAME" | wc -l | awk '{printf "%s", $1}')
                    if [ $NBOUNDS -gt "1" ]; then
                        echo " Multiple bounds found for $FNAME in ${FRAME_BOUNDS}; specifying camera" >> $LOGFILE
                        BOUNDS=$(cat $FRAME_BOUNDS | grep "${FNAME}_cam${CAM}")
                    else
                        BOUNDS=$(cat $FRAME_BOUNDS | grep "${FNAME}")
                    fi
                    START_FRAME_OFFSET=$(echo "$BOUNDS" | awk -F'|' '{printf "%d", $2}')
                    END_FRAME_OFFSET=$(echo "$BOUNDS" | awk -F'|' '{printf "%d", $3}')
                    echo " Got bounds: $START_FRAME_OFFSET and $END_FRAME_OFFSET" >> $LOGFILE
                fi

                mkdir -p $BLENDDIR
                mkdir -p $TESTFRAMES
                blender --background --python-exit-code 1 --factory-startup "$BLENDFILE" \
                        --python blender/render_main.py -- \
                        --set_camera=$CAM \
                        --offset_scene_start_frame_by=$START_FRAME_OFFSET \
                        --offset_scene_end_frame_by=$END_FRAME_OFFSET \
                        --frame_output_prefix=$TESTFRAMES/orig_${FNAME}_cam${CAM}_ \
                        --output_blend=$CAM_BLEND $USERARG \
                        --rendered_frames=1 \
                        >> $LOGFILE 2>&1
                echo "      --> Ok: $CAM_BLEND"
                echo "            : $TESTFRAMES/orig_$FNAME"
            fi
        fi

        if [[ "$STAGES" == *:1:* ]]; then
            if [ "$SKIP_EXISTING" -eq 1 ] && [ -f "$IMGMETA_BLEND" ] && [ -f "$EXRMETA_BLEND" ]; then
                echo "(STEP 1): Skipping existing $IMGMETA_BLEND $EXRMETA_BLEND"
            else
                LOGFILE=$LOGDIR/log_stage1.txt
                echo "STEP 1: Configuring metadata rendering for camera $CAM for $FNAME"
                echo "        $LOGFILE"

                # Normals and correspondences blend
                mkdir -p $NORMDIR
                mkdir -p $CORRDIR
                mkdir -p $BLENDDIR
                blender --background --debug-python --python-exit-code 1 --verbose 7 \
                        --factory-startup "$CAM_BLEND" \
                        --python blender/render_main.py -- \
                        --camera_normals_output_dir=$NORMDIR \
                        --frame_output_prefix=$TESTFRAMES/corr_${FNAME}_cam${CAM}_ \
                        --set_corresp_style \
                        --output_blend=$IMGMETA_BLEND \
                        --use_blender_render \
                        --quality_samples=1 $USERARG \
                        --rendered_frames=1 \
                        > $LOGFILE 2>&1
                echo "      --> Ok: $IMGMETA_BLEND"
                echo "            : $NORMDIR"
                echo "            : $CORRDIR"
                echo "            : $TESTFRAMES/corr_${FNAME}_cam${CAM}"

                # Objectids blend
                mkdir -p $IDXDIR
                blender --background --debug-python --python-exit-code 1 --verbose 7 \
                        --factory-startup "$CAM_BLEND" \
                        --python blender/render_main.py -- \
                        --frame_output_prefix=$TESTFRAMES/objectids_${FNAME}_cam${CAM}_ \
                        --objectids_key_file=$IDXDIR/KEYS.txt \
                        --set_objectids_style \
                        --output_blend=$IDS_BLEND \
                        --use_blender_render \
                        --quality_samples=1 $USERARG \
                        --rendered_frames=1 \
                        > $LOGFILE 2>&1
                echo "      --> Ok: $IDS_BLEND"
                echo "            : $IDXDIR"
                echo "            : $TESTFRAMES/ids_${FNAME}_cam${CAM}"

                # EXR metadata blend
                mkdir -p $EXRDIR
                blender --background --python-exit-code 1 --factory-startup "$CAM_BLEND" \
                        --python blender/render_main.py -- \
                        --frame_output_prefix=$EXRDIR/meta \
                        --render_metadata_exr \
                        --output_blend=$EXRMETA_BLEND \
                        --use_cycles \
                        --quality_samples=1 $USERARG \
                        --rendered_frames=1 \
                        >> $LOGFILE 2>&1
                echo "      --> Ok: $EXRMETA_BLEND"
                echo "            : $EXRDIR"
            fi
        fi

        LINE_SPECS=$AUXDIR/outline_specs.txt
        if [[ "$STAGES" == *:2:* ]]; then
            echo "STEP 2: Configuring shading styles"

            if [ "$ONESTYLE" -ne "0" ]; then
                echo " ... Configuring Mixed type random styles"
                NSTYLESB=0
                NSTYLESS=0
                for i in $(seq $ONESTYLE); do
                    if [ "$((RANDOM % 2))" -eq 0 ]; then
                        echo "Selecting a random style $i --> using Blender"
                        NSTYLESB=$((NSTYLESB + 1))
                    else
                        echo "Selecting a random style $i --> using Stylit"
                        NSTYLESS=$((NSTYLESS + 1))
                        USE_STYLIT=1
                    fi
                done
                NSTYLES=$((NSTYLESB + NSTYLESS))
                cat > $ONESTYLECONFIG <<EOF
NSTYLESB $NSTYLESB
NSTYLESS $NSTYLESS
EOF
            fi


            LOGFILE=$LOGDIR/log_stage2.txt
            echo "" > $LOGFILE

            # Configure other shading styles -----------------------------------
            rm -rf $LINE_SPECS
            # TODO: remove outline blends and renders too

            for (( STY=0; STY<$NSTYLESB; STY++)); do
                if [ "$STY" -eq "0" ] && [ $NSTYLESB -gt 1 ]; then
                    MAT="flat"
                elif [ "$STY" -eq "1" ] && [ $NSTYLESB -gt 2 ]; then
                    MAT="toon"
                elif [ "$STY" -eq "2" ] && [ $NSTYLESB -gt 3 ]; then
                    MAT="textured"
                else
                    MAT=".*"
                fi

                echo "      configuring shading $STY ..."
                STYLE_BLEND=$SHADING_BLEND_PREFIX$STY.blend
                if [ "$SKIP_EXISTING" -eq 1 ] && [ -f "$STYLE_BLEND" ]; then
                    echo "      (skipping): $STYLE_BLEND"
                    echo "                : $TESTFRAMES/shading${STY}_${FNAME}_cam${CAM}_ "
                else
                    echo "      $LOGFILE"
                    rm -rf ${SHADING_BLEND_PREFIX}${STY}*

                    # TODO: also remove renderings

                    COLORS=""
                    if [ ! -z ${ABCV_COLORS+x} ] && [ "$((RANDOM % 3))" -eq 0 ]; then
                        NCOLORS=$(wc -l $ABCV_COLORS | awk '{printf "%s", $1}')
                        LN=$((1 + (RANDOM % NCOLORS)))
                        COLORS=$(head -n$LN $ABCV_COLORS | tail -n1 | awk -F'|' '{print $2}')
                    fi


                    STYLE_INFO=$AUXDIR/shading${STY}_info.txt
                    blender --background --python-exit-code 1 --factory-startup "$CAM_BLEND" \
                            --python blender/render_main.py -- \
                            --frame_output_prefix=$TESTFRAMES/shading${STY}_${FNAME}_cam${CAM}_ \
                            --materials_blend=$ABCV_MATS \
                            --set_materials_matching="$MAT" \
                            --randomize_material_color \
                            --material_color_choices="$COLORS" \
                            --output_blend="${SHADING_BLEND_PREFIX}${STY}_<M>.blend" \
                            --use_blender_render \
                            --info_file=$STYLE_INFO \
                            $USERARG \
                            --rendered_frames=1 >> $LOGFILE 2>&1

                    STYLENAME=$(cat $STYLE_INFO | grep "MATSTYLE" | awk '{print $2}')
                    echo "Style name: $STYLENAME"
                    echo "Looking for line req: $(dirname $ABCV_MATS)/line_reqs/$STYLENAME.txt"
                    LINE_REQ=$(dirname $ABCV_MATS)/line_reqs/$STYLENAME.txt
                    LINE_SPEC=$(get_line_spec $LINE_REQ)
                    echo "$LINE_SPEC" >> $LINE_SPECS

                    echo "      --> Ok: ${SHADING_BLEND_PREFIX}${STY}_"
                    echo "            : $TESTFRAMES/shading${STY}_${FNAME}_cam${CAM}_"
                    ln -s $($(which ls) ${SHADING_BLEND_PREFIX}${STY}_*) $STYLE_BLEND
                    echo "            : $STYLE_BLEND"
                    echo "   linespec : $LINE_SPEC"
                fi
            done

            # If stylit, configre red material blend ---------------------------
            if [ "$USE_STYLIT" -eq "1" ]; then
                echo "      configuring stylit ..."
                if [ "$SKIP_EXISTING" -eq 1 ] && [ -f "$STYLIT_BLEND" ]; then
                    echo "      (skipping): $STYLIT_BLEND; $REDMATDIR"
                else
                    echo "      $LOGFILE"

                    mkdir -p $REDMATDIR
                    blender --background --python-exit-code 1 --factory-startup "$CAM_BLEND" \
                            --python blender/render_main.py -- \
                            --frame_output_prefix=$TESTFRAMES/redmat_${FNAME}_cam${CAM}_ \
                            --set_stylit_style \
                            --set_stylit_lighting \
                            --output_blend=$STYLIT_BLEND \
                            --use_cycles \
                            --enable_gamma_correction \
                            --quality_samples=36 \
                            $USERARG \
                            --rendered_frames=1 >> $LOGFILE 2>&1
                    echo "      --> Ok: $STYLIT_BLEND"
                    echo "            : $TESTFRAMES/redmat_${FNAME}_cam${CAM}_"

                    STYLES=($($(which ls) -1 $ABCV_STYLIT_STYLES | $SHUF | head -n$NSTYLESS))
                    echo "ABCV: $ABCV_STYLIT_STYLES"
                    for (( STY=0; STY<$NSTYLESS; STY++)); do
                        STYLE=${STYLES[STY]}
                        echo "Looking for style: $ABCV_STYLIT_STYLES/$STYLE"
                        ls -d $ABCV_STYLIT_STYLES/$STYLE

                        LINE_REQ=$ABCV_STYLIT_STYLES/$STYLE/line_req.txt
                        LINE_SPEC=$(get_line_spec $LINE_REQ)
                        echo "$LINE_SPEC" >> $LINE_SPECS

                        echo "$STYLE" > $AUXDIR/stylit_info${STY}.txt
                        echo "    Stylit style $STY:"
                        echo "      --> Ok: $AUXDIR/stylit_info${STY}.txt"
                        echo "       style: $STYLE"
                        echo "   linespec : $LINE_SPEC"
                    done
                fi
            fi
        fi

        if [[ "$STAGES" == *:3:* ]]; then
            echo "STEP 3: Configuring outline styles"
            LOGFILE=$LOGDIR/log_stage3.txt

            if [ "$ONESTYLE" -ne "0" ]; then
                read_onestylestyle_info $ONESTYLECONFIG
            fi

            # Configure outlines -----------------------------------------------
            for (( STY=0; STY<$NSTYLES; STY++)); do
                if [ "$STY" -eq "0" ] && [ $NSTYLES -gt 1 ]; then
                    LINES="pen[^c]"  # not pencil, but pen
                else
                    LINES=".*"
                fi

                LINE_SPEC=$(head -n$((STY+1)) $LINE_SPECS | tail -n1)
                EXTRA_LINE_FLAGS=$(echo $LINE_SPEC | awk '{for (i=3;i<=NF; ++i) { printf "%s ", $i}}')

                echo "      configuring outline $STY ..."
                echo "      (extra flags: $EXTRA_LINE_FLAGS)"
                STYLE_BLEND=$LINE_BLEND_PREFIX$STY.blend
                if [ "$SKIP_EXISTING" -eq 1 ] && [ -f "$STYLE_BLEND" ]; then
                    echo "      (skipping): $STYLE_BLEND"
                    echo "                : $TESTFRAMES/outline${STY}_${FNAME}_cam${CAM}_ "
                else
                    echo "      $LOGFILE"

                    rm -rf ${LINE_BLEND_PREFIX}${STY}*
                    #TODO: remove renders as well

                    blender --background --python-exit-code 1 --factory-startup "$CAM_BLEND" \
                            --python blender/render_main.py -- \
                            --frame_output_prefix=$TESTFRAMES/outline${STY}_${FNAME}_cam${CAM}_ \
                            --materials_blend=$ABCV_MATS \
                            --linestyles_blend=$ABCV_LINESTYLES \
                            --set_linestyle_matching="$LINES" \
                            --set_materials_matching="none" \
                            --output_blend="${LINE_BLEND_PREFIX}${STY}_<L>.blend" \
                            --use_blender_render \
                            --info_file=$AUXDIR/outline${STY}_info.txt \
                            $EXTRA_LINE_FLAGS \
                            $USERARG \
                            --rendered_frames=1 > $LOGFILE 2>&1

                    echo "      --> Ok: ${LINE_BLEND_PREFIX}${STY}_"
                    echo "            : $TESTFRAMES/outline${STY}_${FNAME}_cam${CAM}_"
                    ln -s $($(which ls) ${LINE_BLEND_PREFIX}${STY}_*) $STYLE_BLEND
                    echo "            : $STYLE_BLEND"
                fi
            done
        fi

        if [[ "$STAGES" == *:4:* ]]; then
            LOGFILE=$LOGDIR/log_stage4.txt
            echo "STEP 4: Rendering original"
            echo "        $LOGFILE"

            mkdir -p $ORIGDIR
            blender --background --python-exit-code 1 --factory-startup "$CAM_BLEND" \
                    --python blender/render_main.py -- \
                    --frame_output_prefix=$ORIGDIR/frame \
                    --rendered_frames=-1 \
                    $USERARG > $LOGFILE 2>&1
            echo "      --> Ok: $ORIGDIR"
        fi

        if [[ "$STAGES" == *:5:* ]]; then
            LOGFILE=$LOGDIR/log_stage5.txt
            echo "STEP 5.1: Rendering image metadata (normals, correspondences)"
            echo "          $LOGFILE"

            mkdir -p $NORMDIR
            mkdir -p $CORRDIR
            blender --background --python-exit-code 1 --factory-startup "$IMGMETA_BLEND" \
                    --python blender/render_main.py -- \
                    --frame_output_prefix=$CORRDIR/corr \
                    --rendered_frames=-1 \
                    $USERARG > $LOGFILE 2>&1
            echo "      --> Ok: $CORRDIR"

            # We rename normals to only contain relative frame number, not absolute
            for X in $(find $NORMDIR -name "normal*.png"); do
                XX=$(echo $X | awk '{gsub(/_[0-9]+\.png$/, ".png"); printf "%s", $1}')
                mv $X $XX
            done
            echo "      --> Ok: $NORMDIR"

            echo "STEP 5.2: Rendering image metadata (objectids)"
            echo "          $LOGFILE"

            mkdir -p $IDXDIR
            blender --background --python-exit-code 1 --factory-startup "$IDS_BLEND" \
                    --python blender/render_main.py -- \
                    --frame_output_prefix=$IDXDIR/objectid \
                    --rendered_frames=-1 \
                    $USERARG > $LOGFILE 2>&1
            echo "      --> Ok: $IDXDIR"

            # We also extract alphas, then rename them
            mkdir -p $ALPHADIR
            ./datagen/frames_to_alpha.sh "$IDXDIR/*.png" $ALPHADIR
            for X in $(find $ALPHADIR -name "*.png"); do
                XX=$(echo $X | awk '{gsub(/objectid/, "alpha"); printf "%s", $1}')
                mv $X $XX
            done
            echo "      --> Ok: $ALPHADIR"
        fi

        if [[ "$STAGES" == *:6:* ]]; then
            LOGFILE=$LOGDIR/log_stage6.txt
            echo "STEP 6: Rendering exr metadata"
            echo "        $LOGFILE"

            mkdir -p $EXRDIR
            blender --background --python-exit-code 1 --factory-startup "$EXRMETA_BLEND" \
                    --python blender/render_main.py -- \
                    --frame_output_prefix=$EXRDIR/meta \
                    --render_metadata_exr \
                    --use_cycles \
                    --quality_samples=1 \
                    --rendered_frames=-1 \
                    $USERARG > $LOGFILE 2>&1
            echo "      --> Ok: $EXRDIR"
        fi

        if [[ "$STAGES" == *:7:* ]]; then
            LOGFILE=$LOGDIR/log_stage7.txt
            echo "STEP 7: Rendering stylit base material"

            if [ "$USE_STYLIT" -eq "1" ]; then
                echo "        $LOGFILE"
                mkdir -p $REDMATDIR
                blender --background --python-exit-code 1 --factory-startup "$STYLIT_BLEND" \
                        --python blender/render_main.py -- \
                        --frame_output_prefix=$REDMATDIR/full \
                        --rendered_frames=-1 \
                        $USERARG > $LOGFILE 2>&1
                echo "      --> Ok: $REDMATDIR"
            else
                echo "      --> Skipping; no stylit styles requested"
            fi
        fi

        if [[ "$STAGES" == *:8:* ]]; then
            echo "STEP 8: Rendering outlines"

            if [ "$ONESTYLE" -ne "0" ]; then
                read_onestylestyle_info $ONESTYLECONFIG
            fi

            for (( STY=0; STY<$NSTYLES; STY++)); do
                LOGFILE=$LOGDIR/log_stage8_outline${STY}.txt
                echo "      rendering outline $STY ..."
                STYLE_BLEND=$($(which ls) -1 ${LINE_BLEND_PREFIX}${STY}_* | head -n1)
                echo "      $STYLE_BLEND"
                echo "      $LOGFILE"

                STYLE_NAME=$(echo $STYLE_BLEND |
                                 awk -F'/' '{print $NF;}' |
                                 awk '{gsub(/.*outlines[0-9]+_/, ""); gsub(/.blend/, ""); print;}')

                STYLE_ODIR=$LINE_DIR/line${STY}.${STYLE_NAME}
                echo "      outputting to $STYLE_ODIR"
                mkdir -p $STYLE_ODIR

                blender --background --python-exit-code 1 --factory-startup "$STYLE_BLEND" \
                        --python blender/render_main.py -- \
                        --frame_output_prefix=$STYLE_ODIR/frame \
                        --rendered_frames=-1 \
                        $USERARG > $LOGFILE 2>&1
                echo "      --> Ok: $STYLE_ODIR"
            done
        fi

        if [[ "$STAGES" == *:9:* ]]; then
            echo "STEP 9: Rendering shading styles"

            if [ "$ONESTYLE" -ne "0" ]; then
                read_onestylestyle_info $ONESTYLECONFIG
            fi

            for (( STY=0; STY<$NSTYLESB; STY++)); do
                LOGFILE=$LOGDIR/log_stage9_shading${STY}.txt
                echo "      rendering shading $STY ..."
                STYLE_BLEND=$($(which ls) -1 ${SHADING_BLEND_PREFIX}${STY}_* | head -n1)
                echo "      $STYLE_BLEND"
                echo "      $LOGFILE"

                STYLE_NAME=$(echo $STYLE_BLEND |
                                 awk -F'/' '{print $NF;}' |
                                 awk '{gsub(/.*shading[0-9]+_/, ""); gsub(/.blend/, ""); print;}')

                STYLE_ODIR=$SHADING_DIR/shading${STY}.${STYLE_NAME}
                echo "      outputting to $STYLE_ODIR"
                mkdir -p $STYLE_ODIR

                blender --background --python-exit-code 1 --factory-startup "$STYLE_BLEND" \
                        --python blender/render_main.py -- \
                        --frame_output_prefix=$STYLE_ODIR/frame \
                        --rendered_frames=-1 \
                        $USERARG > $LOGFILE 2>&1
                echo "      --> Ok: $STYLE_ODIR"
            done
        fi

        if [[ "$STAGES" == *:10_0:* ]]; then
            echo "STEP 10_0: Purging stylit cached styles"

            AUX_STYLIT_DIR=$AUXDIR/stylit
            rm -rf $AUX_STYLIT_DIR
            echo "      --> Ok: removed $AUX_STYLIT_DIR"
        fi

        if [[ "$STAGES" == *:10:* ]]; then
            echo "STEP 10: Using stylit to stylize"

            if [ ${USE_STYLIT} -ne "1" ]; then
                echo "      --> Skipping: No stylit styles requested"
            else
                if [ "$ONESTYLE" -ne "0" ]; then
                    read_onestylestyle_info $ONESTYLECONFIG
                fi

                AUX_STYLIT_DIR=$AUXDIR/stylit
                mkdir -p $AUX_STYLIT_DIR
                for (( STY=0; STY<$NSTYLESS; STY++)); do
                    STYLE=$(cat $AUXDIR/stylit_info${STY}.txt)
                    STYLEDIR=$ABCV_STYLIT_STYLES/$STYLE

                    STYLE_ODIR=$SHADING_DIR/shading$((NSTYLESB + STY)).$STYLE
                    mkdir -p $STYLE_ODIR

                    RANDPROB=60
                    echo "      using style $STYLE"
                    echo "      outputting to $STYLE_ODIR"
                    ${SCRIPT_DIR}/stylize.sh -r $RANDPROB $STYLEDIR \
                                 $REDMATDIR \
                                 $NORMDIR \
                                 $IDXDIR \
                                 $STYLE_ODIR \
                                 $AUX_STYLIT_DIR
                    echo "      --> Ok: $STYLE_ODIR"
                done
            fi
        fi


        if [[ "$STAGES" == *:11:* ]]; then
            echo "STEP 11: Compositing"

            if [ "$ONESTYLE" -ne "0" ]; then
                read_onestylestyle_info $ONESTYLECONFIG
            fi

            for (( STY=0; STY<$NSTYLES; STY++)); do
                LINE=$($(which ls) -d $LINE_DIR/line${STY}.*)
                SHADING=$($(which ls) -d $SHADING_DIR/shading${STY}.*)
                LINE_FLAG=$(head -n$((STY+1)) $LINE_SPECS | tail -n1 | awk '{printf "%s", $2}')

                LINE_NAME=$(echo $LINE | awk -F'.' '{printf "%s", $NF}')
                SHADING_NAME=$(echo $SHADING | awk -F'.' '{printf "%s", $NF}')

                if [ "$STY" -lt "$NSTYLESB" ]; then
                    # Blender styles render with alpha
                    STYLE_COMPOSITE_ODIR=$COMPOSITEDIR_NOBG/style.${SHADING_NAME}.${LINE_NAME}
                else
                    # Stylit styles render without opacity
                    STYLE_COMPOSITE_ODIR=$COMPOSITEDIR/style.${SHADING_NAME}.${LINE_NAME}
                fi

                echo "      ... making style $(basename $STYLE_COMPOSITE_ODIR)"
                mkdir -p $STYLE_COMPOSITE_ODIR
                FIRST=1
                for FRR in $($(which ls) $SHADING/*.png); do
                    FR=$(basename $FRR)
                    FG=$LINE/$FR
                    BG=$SHADING/$FR
                    RES=$STYLE_COMPOSITE_ODIR/$FR

                    if [ "$LINE_FLAG" == "LINE" ]; then
                        # convert -compose overlay -gravity center -composite \
                        composite -dissolve 100 -gravity center -alpha Set \
                                $FG $BG $RES
                    elif [ "$LINE_FLAG" == "NONE" ]; then
                        echo "copyng"
                        cp $BG $RES
                    else
                        echo "Malformed line $STY in $LINE_SPECS"
                        exit 1
                    fi

                    if [ "$FIRST" -eq "1" ]; then
                        mkdir -p $TESTFRAMES
                        cp $RES $TESTFRAMES/style.${SHADING_NAME}.${LINE_NAME}_${FNAME}_cam${CAM}.png
                        FIRST=0
                    fi
                done
                echo "      -> Ok: $STYLE_COMPOSITE_ODIR"
            done

        fi

        if [[ "$STAGES" == *:12:* ]]; then
            LOGFILE=$LOGDIR/log_stage12.txt
            echo "STEP 12: Unpacking EXR metadata $EXRDIR"
            echo "        $LOGFILE"

            mkdir -p $FLOWDIR
            mkdir -p $BACKFLOWDIR
            mkdir -p $OCCDIR
            mkdir -p $DEPTHDIR
            mkdir -p $DEPTHIMGDIR

            mkdir -p $FIN_METADIR
            mkdir -p $FIN_METADIR_SUPP
            echo "  ... unpacking and compressing all the core data"
            ./blender/unpack_exr_main.py \
                --input_dir=$EXRDIR \
                --flow_odir=$FLOWDIR \
                --back_flow_odir=$BACKFLOWDIR \
                --depth_odir=$DEPTHDIR \
                --depth_range_ofile=$DEPTHIMGDIR/range.txt \
                --occlusions_odir=$OCCDIR \
                --flow_zip=$FIN_METADIR/flow.zip \
                --back_flow_zip=$FIN_METADIR_SUPP/backflow.zip \
                --depth_zip=$FIN_METADIR_SUPP/depth.zip \
                > $LOGFILE 2>&1
            echo "      --> Ok: $FLOWDIR"
            echo "            : $BACKFLOWDIR"
            echo "            : $DEPTHDIR"
            echo "            : $OCCDIR"
            echo "            : $FIN_METADIR/flow.zip"
            echo "            : $FIN_METADIR_SUPP/backflow.zip"
            echo "            : $FIN_METADIR_SUPP/depth.zip"
            echo "            : $DEPTHIMGDIR/range.txt"

            echo "  ... outputting depth images"
            ./blender/depth_images_main.py \
                --depth_array_dir=$DEPTHDIR \
                --depth_range_file=$DEPTHIMGDIR/range.txt \
                --depth_img_odir=$DEPTHIMGDIR \
                > $LOGFILE 2>&1
            echo "      --> Ok: $DEPTHIMGDIR"

            echo "  ... getting flow information"
            FLOWINFO=$ODIR/pipeline/info/${FNAME}_cam${CAM}_flowinfo.txt
            ./blender/compressed_info_main.py \
                --flowzip=$FIN_METADIR/flow.zip \
                --objiddir=$IDXDIR \
                --out_file=$FLOWINFO \
                > $LOGFILE 2>&1
            echo "     --> Ok: $FLOWINFO"
        fi

        if [[ "$STAGES" == *:13_0:* ]]; then
            echo "STEP 13_0: Purging previously created backgrounds"

            rm -rf $AUXDIR/bg*.png
            echo "     --> Ok: removed $AUXDIR/bg*.png"
        fi

        if [[ "$STAGES" == *:13:* ]]; then
            NBGS=$(wc -l $ABCV_BACKGROUNDS | awk '{printf "%s", $1}')
            echo "STEP 13: Compositing backgrounds by randomly selecting from $NBGS images"

            if [ -d $COMPOSITEDIR_NOBG ]; then
                SDIRS="$($(which ls) $COMPOSITEDIR_NOBG)"
                for S in $SDIRS; do
                    STYLE_INPUT_DIR=$COMPOSITEDIR_NOBG/$S
                    STYLE_COMPOSITE_ODIR=$COMPOSITEDIR/$S
                    mkdir -p $STYLE_COMPOSITE_ODIR

                    # Pick and prepare background image
                    BG_IMG=$AUXDIR/bg_${S}.png
                    if [ ! -f $BG_IMG ]; then
                        # Note: if backgrounds are copied on demand from a large image
                        # storage, we may only have just enough available, so picking
                        # a random one does not make sense.
                        if [ $RANDBG -eq "1" ]; then
                            LN=$((1 + ((RANDOM * RANDOM + RANDOM) % NBGS)))
                        else
                            LN=$((1 + (BGNUM % NBGS)))
                            BGNUM=$((BGNUM + 1))
                        fi
                        BG_LINE=$(head -n$LN $ABCV_BACKGROUNDS | tail -n1)
                        IMID=$(echo "$BG_LINE" | awk -F'|' '{printf "%s", $2}')
                        ORIG_IMG=$ABCV_BACKGROUND_DIR/$(echo "$BG_LINE" | awk -F'|' '{printf "%s", $1}')
                        echo "Creating background image $BG_IMG from $ORIG_IMG"

                        if [ ! -f $ORIG_IMG ]; then
                            echo "Cannot locate original image: $ORIG_IMG"
                            exit 1
                        fi

                        $SCRIPT_DIR/make_attribution.sh "$BG_LINE" $STYLE_COMPOSITE_ODIR/LICENSE.txt
                        echo "      ... selected background for style $S: $BG_LINE"
                    fi

                    echo "      ... compositing style $S with $BG_IMG"
                    for FRR in $($(which ls) $STYLE_INPUT_DIR/*.png); do
                        FR=$(basename $FRR)
                        IN=$STYLE_INPUT_DIR/$FR
                        RES=$STYLE_COMPOSITE_ODIR/$FR

                        if [ ! -f $BG_IMG ]; then
                            DIMS=$(convert $IN -format "%wx%h" info:)
                            convert $ORIG_IMG -resize "${DIMS}^" -gravity center \
                                    -crop "${DIMS}+0+0" +repage $BG_IMG
                            cp $BG_IMG $AUXDIR/bg_${S}_$IMID.png
                        fi


                        # Composite with the bg image
                        composite -dissolve 100 -gravity center -alpha Set \
                                  $IN $BG_IMG $RES
                    done
                done
            fi
        fi

        if [[ "$STAGES" == *:14:* ]]; then
            echo "STEP 14: Compressing"

            FRATE=12
            CRF=20

            # COMPOSITE RENDERS ------------------------------------------------
            mkdir -p $FIN_COMPDIR
            echo "     processing $COMPOSITEDIR"
            if [ "$(ls -A $COMPOSITEDIR)" ]; then
                set +e
                STYLES=$($(which ls) -1 $COMPOSITEDIR | grep -v "original")
                ECODE=$?
                set -e

                if [ $ECODE -ne "0" ]; then
                    echo "       --> ? : missing entries in $COMPOSITEDIR"
                    echo "               (was stage 11 executed?)"
                else
                    echo "" > $ODIR/pipeline/info/${FNAME}_cam${CAM}_stylevideos.txt
                    for S in $STYLES; do
                        SDIR=$COMPOSITEDIR/$S
                        echo "      ... compressing style $SDIR"

                        STYLE_VIDEO=$FIN_COMPDIR/$S.mp4
                        ./datagen/to_animation.sh \
                            -y -f $FRATE -c $CRF $SDIR/frame%06d.png $STYLE_VIDEO
                        echo "       --> Ok: $STYLE_VIDEO"
                        echo "$STYLE_VIDEO" >> $ODIR/pipeline/info/${FNAME}_cam${CAM}_stylevideos.txt

                        if [ -f $SDIR/LICENSE.txt ]; then
                            cp $SDIR/LICENSE.txt $FIN_COMPDIR/${S}_LICENSE.txt
                            echo "       --> Ok: license attached"
                        fi
                    done
                fi
            else
                echo "       --> ? : missing entries in $COMPOSITEDIR"
            fi

            # LINE RENDERS -----------------------------------------------------
            echo "     processing $LINE_DIR"
            if [ "$(ls -A $LINE_DIR)" ]; then
                for (( STY=0; STY<$NSTYLES; STY++)); do
                    LINE=$($(which ls) -d $LINE_DIR/line${STY}.*)
                    LINE_NAME=$(echo $LINE | awk -F'.' '{printf "%s", $NF}')
                    echo "      ... compressing line style $LINE"

                    # Add a white background, since most lines are dark
                    if [ ! -f $WHITEBG ]; then
                        make_white_bg $($(which ls) -1 $LINE/*.png | head -n1)
                    fi

                    mkdir -p $FIN_LINEDIR
                    LINE_VIDEO=$FIN_LINEDIR/line$STY.$LINE_NAME.mp4
                    ./datagen/frames_to_overlay_video.sh \
                        $WHITEBG "$LINE/*.png" "frame%06d.png" $FRATE $CRF $LINE_VIDEO
                    echo "       --> Ok: $LINE_VIDEO"

                    # Also make an alpha video for the line, if somebody wants
                    # to use custom background
                    LINE_ALPHA_VIDEO=$FIN_LINEDIR/line$STY.$LINE_NAME.alpha.mp4
                    ./datagen/frames_to_alpha_video.sh \
                        "$LINE/*.png" "frame%06d.png" $FRATE $LINE_ALPHA_VIDEO
                    echo "       --> Ok: $LINE_ALPHA_VIDEO"

                done
            else
                echo "       --> ? : missing entries in $LINE_DIR"
            fi

            # SHADING RENDERS --------------------------------------------------
            echo "     processing $SHADING_DIR"
            if [ "$(ls -A $SHADING_DIR)" ]; then
                for (( STY=0; STY<$NSTYLES; STY++)); do
                    SHADING=$($(which ls) -d $SHADING_DIR/shading${STY}.*)
                    SHADING_NAME=$(echo $SHADING | awk -F'.' '{printf "%s", $NF}')
                    echo "      ... compressing shading style $SHADING"

                    mkdir -p $FIN_SHADEDIR
                    SHADING_VIDEO=$FIN_SHADEDIR/shading$STY.$SHADING_NAME.mp4
                    ./datagen/to_animation.sh \
                        -y -f $FRATE -c $CRF $SHADING/frame%06d.png $SHADING_VIDEO
                    echo "       --> Ok: $SHADING_VIDEO"
                done
            else
                echo "       --> ? : missing entries in $SHADING_DIR"
            fi

            # METADATA ---------------------------------------------------------
            echo "     processing $ORIGDIR"
            if [ -d $ORIGDIR ]; then
                mkdir -p $FIN_METADIR
                ORIG_VIDEO=$FIN_METADIR/original.mp4
                ./datagen/to_animation.sh \
                    -y -f $FRATE -c $CRF "$ORIGDIR/frame%06d.png" $ORIG_VIDEO
                echo "       --> Ok: $ORIG_VIDEO"
            else
                echo "       --> ? : missing entries in $ORIGDIR"
            fi

            echo "     processing $REDMATDIR"
            if [ -d $REDMATDIR ]; then
                mkdir -p $FIN_METADIR
                REDMAT_VIDEO=$FIN_METADIR/redmat.mp4
                ./datagen/to_animation.sh \
                    -y -f $FRATE -c $CRF "$REDMATDIR/full%06d.png" $REDMAT_VIDEO
                echo "       --> Ok: $REDMAT_VIDEO"
            else
                echo "       --> ? : missing entries in $REDMATDIR"
            fi

            echo "     processing $ALPHADIR"
            if [ "$(ls -A $ALPHADIR)" ]; then
                mkdir -p $FIN_METADIR
                ALPHA_VIDEO=$FIN_METADIR/alpha.mp4
                ./datagen/to_animation.sh \
                    -y -f $FRATE -c $CRF "$ALPHADIR/alpha%06d.png" $ALPHA_VIDEO
                echo "       --> Ok: $ALPHA_VIDEO"
            else
                echo "       --> ? : missing entries in $ALPHADIR"
            fi

            echo "     processing $DEPTHIMGDIR"
            if [ "$(ls -A $DEPTHIMGDIR)" ]; then
                mkdir -p $FIN_METADIR
                DEPTH_VIDEO=$FIN_METADIR/depthimg.mp4
                ./datagen/to_animation.sh \
                    -y -f $FRATE -c $CRF "$DEPTHIMGDIR/depth%06d.png" $DEPTH_VIDEO
                echo "       --> Ok: $DEPTH_VIDEO"

                cp $DEPTHIMGDIR/range.txt $FIN_METADIR/depth.range.txt
            else
                echo "       --> ? : missing entries in $DEPTHIMGDIR"
            fi

            echo "     processing $CORRDIR"
            if [ "$(ls -A $CORRDIR)" ]; then
                mkdir -p $FIN_METADIR_SUPP
                CORR_VIDEO=$FIN_METADIR_SUPP/corresp_lossless.mp4
                ffmpeg -y -hide_banner -loglevel panic \
                       -framerate $FRATE -i $CORRDIR/corr%06d.png \
                       -c:v libx264 -preset veryslow -crf 0 $CORR_VIDEO
                echo "       --> Ok: $CORR_VIDEO"

                # Also produce a smaller lossy video
                mkdir -p $FIN_METADIR
                CORR_VIDEO=$FIN_METADIR/corresp.mp4
                ./datagen/to_animation.sh \
                    -y -f $FRATE -c $CRF "$CORRDIR/corr%06d.png" $CORR_VIDEO
                echo "       --> Ok: $CORR_VIDEO"
            else
                echo "       --> ? : missing entries in $CORRDIR"
            fi

            echo "     processing $NORMDIR"
            if [ "$(ls -A $NORMDIR)" ]; then
                mkdir -p $FIN_METADIR_SUPP
                NORM_VIDEO=$FIN_METADIR_SUPP/normals_lossless.mp4
                ffmpeg -y -hide_banner -loglevel panic \
                       -framerate $FRATE -i $NORMDIR/normal%06d.png \
                       -c:v libx264 -preset veryslow -crf 0 $NORM_VIDEO
                echo "       --> Ok: $NORM_VIDEO"

                # Also produce a smaller lossy video
                mkdir -p $FIN_METADIR
                NORM_VIDEO=$FIN_METADIR/normals.mp4
                ./datagen/to_animation.sh \
                    -y -f $FRATE -c $CRF "$NORMDIR/normal%06d.png" $NORM_VIDEO
                echo "       --> Ok: $NORM_VIDEO"
            else
                echo "       --> ? : missing entries in $NORMDIR"
            fi

            echo "     processing $IDXDIR"
            if [ "$(ls -A $IDXDIR)" ]; then
                mkdir -p $FIN_METADIR
                IDX_ZIP=$FIN_METADIR/objectids.zip
                zip -j $IDX_ZIP $IDXDIR/* > /dev/null
                echo "       --> Ok: $IDX_ZIP"
            else
                echo "       --> ? : missing entries in $IDXDIR"
            fi

            echo "     processing $OCCDIR"
            if [ "$(ls -A $OCCDIR)" ]; then
                mkdir -p $FIN_METADIR
                OCC_VIDEO=$FIN_METADIR/occlusions.mp4
                ./datagen/to_animation.sh \
                    -y -f $FRATE -c $CRF "$OCCDIR/occlusions%06d.png" $OCC_VIDEO
                echo "       --> Ok: $OCC_VIDEO"
            else
                echo "       --> ? : missing entries in $OCCDIR"
            fi

            # Flow and depth are already compressed, clean up if needed
        fi

        if [[ "$STAGES" == *:15:* ]]; then
            echo "STEP 15: Performing final file sanity checks"

            echo "     15.1: Are all the compressed metadata files written?"
            echo "           (Checking ${FIN_METADIR})"

            if [ ! -d "$FIN_METADIR" ]; then
                echo "       --> FAIL: $FIN_METADIR does not exist"
                exit 1
            fi

            FAIL=0
            # Core metadata
            for B in  "depthimg.mp4" "depth.range.txt"  \
                                     "flow.zip" "occlusions.mp4" "normals.mp4" \
                                     "corresp.mp4"  "objectids.zip"  \
                                     "original.mp4"; do
                if [ ! -f "$FIN_METADIR/$B" ]; then
                    echo "       --> (Missing $B)"
                    FAIL=1
                else
                    echo "       --> Found $B"
                fi
            done

            # Supplementary metadata
            for B in "backflow.zip" "depth.zip" "corresp_lossless.mp4" \
                                    "normals_lossless.mp4"; do
                if [ ! -f "$FIN_METADIR_SUPP/$B" ]; then
                    echo "       --> (Missing $B)"
                    FAIL=1
                else
                    echo "       --> Found $B"
                fi
            done

            if [ $FAIL -eq "1" ]; then
                echo "       --> FAIL: Missing files found"
                exit 1
            else
                echo "       --> OK: All expected files found"
            fi

            echo "     15.2: Are all the compressed renderings written?"
            echo "           (Checking ${FIN_RENDERDIR})"
            for D in "$FIN_LINEDIR" "$FIN_SHADEDIR" "$FIN_COMPDIR"; do
                if [ ! -d "$D" ]; then
                    echo "       --> FAIL: $D does not exist"
                    exit 1
                fi

                NFOUND=$(find "$D" -name "*.mp4" | grep -v "alpha.mp4" | wc -l)
                NEXPECTED=$NSTYLES
                if [ "$NFOUND" -ne "$NSTYLES" ]; then
                    echo "       --> FAIL: found $NFOUND mp4 files in $D (expected $NEXPECTED)"
                    exit 1
                else
                    echo "       --> OK: found $NFOUND mp4 files in $D"
                fi
            done

        fi

        if [[ "$STAGES" == *:16:* ]]; then
            echo "STEP 16: Performing flow/correspondence sanity checks"

            LOGFILE=$LOGDIR/log_stage16_sanity.txt
            DEBUG_SANITY_IMG=$AUXDIR/sanity_debug.png
            echo "         $LOGFILE"
            echo "         $DEBUG_SANITY_IMG"
            ./blender/check_sanity_main.py \
                --flow_pattern=$FLOWDIR/*.flo \
                --objectid_pattern=$IDXDIR/*.png \
                --corresp_pattern=$CORRDIR/*.png \
                --occlusion_pattern=$OCCDIR/*.png \
                --alpha_pattern=$ALPHADIR/*.png \
                --debug_output_file=$DEBUG_SANITY_IMG \
                --debug_only_on_failure \
                --min_sanity=0.8 \
                --max_occlusion_frac=0.8 \
                --nframes=10 --npixels=2000 > $LOGFILE 2>&1
            echo "       --> OK: $(tail -n1 $LOGFILE)"
        fi

        if [[ "$STAGES" == *:17:* ]]; then
            echo "STEP 17: Performing partial data clean up"

            rm -rf $FLOWDIR
            echo "       --> OK: removed $FLOWDIR"
            rm -rf $BACKFLOWDIR
            echo "       --> OK: removed $BACKFLOWDIR"
            rm -rf $DEPTHDIR
            echo "       --> OK: removed $DEPTHDIR"
        fi

        echo "DONE processing camera $CAM for blend $FNAME"
    done

    echo "DONE processing blend $FNAME"
done
