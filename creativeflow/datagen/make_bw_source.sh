#!/bin/bash -e
set -o nounset

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

USAGE="make_bw_source.sh <flags> style_dir output_source_dir

Makes a monochrome source directorly from a style for applying stylit,
specifically creates:
output_source_dir/ids.png
                 /full.png
                 /normals.png
                 /source0.png  <-- style exemplar 0
                 /source1.png  <-- style exemplar 1 (same style, but no temp coherence)

Flags:
-r if set, randomize input color; or else set values below; or else will use original
-h <0-200> how much to shift hue
-s <0-200> how much to shift saturation
-v <0-200> how much to shift value
-e example number, else randomized
"

RANDOMIZE_COLOR=0
EXAMPLE="example"
unset HUE
unset SAT
unset VALUE
while getopts ':rh:s:v:e:' option; do
    case "$option" in
        r) RANDOMIZE_COLOR=1
           echo "Allowing color randomization"
           ;;
        h) HUE=$OPTARG
           echo "Shifting hue by $HUE"
           ;;
        s) SAT=$OPTARG
           echo "Shifting sat by $SAT"
           ;;
        v) VALUE=$OPTARG
           echo "Shifting value by $VALUE"
           ;;
        e) EXAMPLE="example$OPTARG"
           echo "Specifically using example $OPTARG"
           ;;
        \?) printf "ERROR! illegal option: -%s\n" "$OPTARG" >&2
            echo "$USAGE" >&2
            exit 1
            ;;
    esac
done
shift $((OPTIND - 1))

STYLE_DIR=$1
SOURCE=$2

echo "Style dir: $STYLE_DIR"
echo "Source: $SOURCE"
SHUF=shuf

set +e
command -v shuf
if [ "$?" -ne "0" ]; then
    echo "Shuf does not exist; assuming gshuf is installed instead"
    SHUF=gshuf
fi
set -e

mkdir -p $SOURCE

# Take care of normals and rendering
cp ${SCRIPT_DIR}/../assets/common/stylit/source_1mat/full.png ${SOURCE}/full.png
cp ${SCRIPT_DIR}/../assets/common/stylit/source_1mat/normals.png ${SOURCE}/normals.png

IDS_1MAT=${SCRIPT_DIR}/../assets/common/stylit/source_1mat/ids.png
${SCRIPT_DIR}/../blender/process_ids_main.py --ids_images=${IDS_1MAT} \
             --from_src_template \
             --nids=1 \
             --out_dir=$SOURCE

# If there is more than one examplar (e.g. multi-color styles), then select one of these
EX=$($(which ls) -1 ${STYLE_DIR} | grep "$EXAMPLE" |
         grep -v "modulation" | awk '{gsub(/_[0-1].png/, ""); print;}' |
         sort -u | $SHUF | head -n1)

EXNUM=$(echo $EX | awk '{gsub(/.*example/, ""); print;}')

# File with modulation annotations (we assume it exists)
MODULATION=$($(which ls) -1 ${STYLE_DIR} | grep "modulation_example$EXNUM" | head -n1)
echo "Found modulation spec: $MODULATION"

if [ -z ${HUE+x} ]; then
    if [ "$RANDOMIZE_COLOR" -eq "1" ]; then
        HUE=$(cat $STYLE_DIR/$MODULATION | grep "hue" | ${SCRIPT_DIR}/random_in_range.sh)
        echo "Modulating hue by $HUE for $EX"
    else
        HUE=100
    fi
fi

if [ -z ${SAT+x} ]; then
    if [ "$RANDOMIZE_COLOR" -eq "1" ]; then
        SAT=$(cat $STYLE_DIR/$MODULATION | grep "sat" | ${SCRIPT_DIR}/random_in_range.sh)
        echo "Modulating saturation by $SAT for $EX"
    else
        SAT=100
    fi
fi

if [ -z ${VALUE+x} ]; then
    if [ "$RANDOMIZE_COLOR" -eq "1" ]; then
        VALUE=$(cat $STYLE_DIR/$MODULATION | grep "val" | ${SCRIPT_DIR}/random_in_range.sh)
        echo "Modulating value by $VALUE for $EX"
    else
        VALUE=100
    fi
fi

for S in "0" "1"; do
    if [ "$HUE" -ne "100" ] || [ "$SAT" -ne "100" ] || [ "$VALUE" -ne "100" ]; then
        echo "Shifting HSV by ${HUE}, ${SAT}, ${VALUE} (100 is no-op)"
        convert ${STYLE_DIR}/${EX}_${S}.png -define modulate:colorspace=HSB \
                -modulate ${VALUE},${SAT},${HUE} $SOURCE/style${S}.png
    else
        cp ${STYLE_DIR}/${EX}_${S}.png ${SOURCE}/style${S}.png
    fi
done

echo "Made source in $SOURCE"
