#!/bin/bash -e
set -o nounset

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

USAGE="make_color_source.sh <flags> N style_dir output_source_dir

Makes a multicolor source directorly from a style for applying stylit to N
object ids. Assumes the style directory contains files named such as:
prefix_bg0_0.png
prefix_bg0_1.png
prefix_bg1_0.png
prefix_bg1_1.png
prefix_color0_0.png
prefix_color0_1.png
prefix_color1_0.png
prefix_color1_1.png
prefix_example0_0.png
prefix_example0_1.png
prefix_example1_0.png
prefix_example1_1.png

Specifically creates:
output_source_dir/ids.png
                 /full.png
                 /normals.png
                 /source0.png  <-- style exemplar 0
                 /source1.png  <-- style exemplar 1 (same style, but no tep coherence

Flags:
-r if set, randomize color (if not, N should really be 2, because we only have 2
   colors per style)."

SHUF=shuf
set +e
command -v shuf
if [ "$?" -ne "0" ]; then
    echo "Shuf does not exist; assuming gshuf is installed instead"
    SHUF=gshuf
fi
set -e

RANDSEED=$(date '+%N')
if ! [[ $RANDSEED =~ ^[0-9]+$ ]]; then
    echo "Date seems to not work ok (Mac OS?): date '+%N' is not a number; trying gdate."
    RANDSEED=$(gdate '+%N')
fi

RANDOMIZE_COLOR=0
while getopts ':r' option; do
    case "$option" in
        r) RANDOMIZE_COLOR=1
           RANDOM=$RANDSEED
           echo "Allowing color randomization"
           ;;
        \?) printf "ERROR! illegal option: -%s\n" "$OPTARG" >&2
            echo "$USAGE" >&2
            exit 1
            ;;
    esac
done
shift $((OPTIND - 1))

N=$1
STYLE_DIR=$2
SOURCE=$3

if [ -z ${TMPDIR+x} ]; then
    TMPDIR=$3/tmp
    echo "TMPDIR not found, using $TMPDIR"
else
    TMPDIR=$TMPDIR/stylittmp
fi

# We create two sources for odd and even frames
mkdir -p $TMPDIR
mkdir -p $SOURCE

# Take care of background
BG=$($(which ls) ${STYLE_DIR} | grep "_bg" | awk '{gsub(/_[0-1].png/, ""); print;}' | sort -u | $SHUF | head -n1)

# Select background modulation criteria
HUE=100
SAT=100
VALUE=100
if [ "$RANDOMIZE_COLOR" -eq "1" ]; then
    BGNUM=$(echo $BG | awk '{gsub(/.*_bg/, ""); print;}')
    MOD_RANGES=$($(which ls) -1 ${STYLE_DIR} | grep "modulation_example$BGNUM" | head -n1)
    HUE=$(cat $STYLE_DIR/$MOD_RANGES | grep "hue" | ${SCRIPT_DIR}/random_in_range.sh)
    SAT=$(cat $STYLE_DIR/$MOD_RANGES | grep "sat" | ${SCRIPT_DIR}/random_in_range.sh)
    VALUE=$(cat $STYLE_DIR/$MOD_RANGES | grep "val" | ${SCRIPT_DIR}/random_in_range.sh)
fi

for S in "0" "1"; do
    if [ "$RANDOMIZE_COLOR" -eq "1" ]; then
        echo "Shifting BG ${BG}_${S}.png by H,S,V $HUE,$SAT,$VALUE (100 is no-op)"

        convert ${STYLE_DIR}/${BG}_${S}.png -modulate ${VALUE},${SAT},${HUE} \
                -background white -flatten $TMPDIR/bg${S}.png
    else
        convert ${STYLE_DIR}/${BG}_${S}.png \
                -background white -flatten $TMPDIR/bg${S}.png
    fi
done


# Take care of normals and rendering
FULL_1MAT=${SCRIPT_DIR}/../assets/common/stylit/source_1mat/full.png
NORM_1MAT=${SCRIPT_DIR}/../assets/common/stylit/source_1mat/normals.png
FULL=${SOURCE}/full.png
NORM=${SOURCE}/normals.png
for ((X=0; X<$N; X++)); do
    if [ "$X" -eq "0" ]; then
        cp $FULL_1MAT $FULL
        cp $NORM_1MAT $NORM
    else
        convert $FULL $FULL_1MAT +append $FULL
        convert $NORM $NORM_1MAT +append $NORM
    fi
done


# Take care of IDs
IDS_1MAT=${SCRIPT_DIR}/../assets/common/stylit/source_1mat/ids.png
${SCRIPT_DIR}/../blender/process_ids_main.py --ids_images=${IDS_1MAT} \
             --from_src_template \
             --nids=$N \
             --out_dir=$SOURCE


# Take care of the colors
NCOLORS=$($(which ls) ${STYLE_DIR} | grep "_color" | \
              awk '{gsub(/_[0-1].png/, ""); print;}' | sort -u | wc -l | awk '{printf "%d", $NF}')

echo "This style has $NCOLORS colors"

# Each of these colors has a different modulation guidance file

# But! we'd like to modulate sat/val the same way for everything
# So, let's make a global guidance for sat and val
if [ "$RANDOMIZE_COLOR" -eq "1" ]; then
    SAT=$(cat ${STYLE_DIR}/*modulation* | grep "sat" | \
              awk 'BEGIN{MI=0;MA=200;}{if ($2 > MI) { MI=$2 } if ($3 < MA) { MA=$3 } }END{printf "%d %d\n", MI, MA}' | \
                  ${SCRIPT_DIR}/random_in_range.sh)
    VALUE=$(cat ${STYLE_DIR}/*modulation* | grep "val" | \
                awk 'BEGIN{MI=0;MA=200;}{if ($2 > MI) { MI=$2 } if ($3 < MA) { MA=$3 } }END{printf "%d %d\n", MI, MA}' | \
                ${SCRIPT_DIR}/random_in_range.sh)

    echo "Setting global saturation,value shift to $SAT,$VALUE"
fi


for ((X=0; X<$N; X++)); do
    CID=$((1 + (X % NCOLORS)))

    if [ "$RANDOMIZE_COLOR" -eq "1" ]; then
        FG=$($(which ls) -1 ${STYLE_DIR} | grep -v "modulation" | grep "_color" | \
                    awk '{gsub(/_[0-1].png/, ""); print;}' | sort -u | $SHUF | head -n${CID} | tail -n1)
    else
        # If not randomizing colors, always want to pick both color exemplars
        FG=$($(which ls) -1 ${STYLE_DIR} | grep -v "modulation" | grep "_color" | \
                    awk '{gsub(/_[0-1].png/, ""); print;}' | sort -u | head -n${CID} | tail -n1)
    fi
    echo "Color $X is $FG"

    if [ "$RANDOMIZE_COLOR" -eq "1" ]; then
        FGNUM=$(echo $FG | awk '{gsub(/.*_color/, ""); print;}')
        MOD_RANGES=$($(which ls) -1 ${STYLE_DIR} | grep "modulation_example$FGNUM" | head -n1)

        PAST_MODS=$TMPDIR/modulations$FGNUM.txt
        touch $PAST_MODS
        #echo "get_distinct_modulation.py --past_modulations=$PAST_MODS --modulation_ranges=$STYLE_DIR/$MOD_RANGES"
        MODULATION=$(${SCRIPT_DIR}/get_distinct_modulation.py \
                                  --past_modulations=$PAST_MODS \
                                  --modulation_ranges=$STYLE_DIR/$MOD_RANGES)
        echo "hsv $MODULATION" >> $PAST_MODS
        HUE=$(echo $MODULATION | awk '{print $1}')
        SAT=$(echo $MODULATION | awk '{print $2}')
        VALUE=$(echo $MODULATION | awk '{print $3}')

        # HUE=$(cat $STYLE_DIR/$MOD_RANGES | grep "hue" | ${SCRIPT_DIR}/random_in_range.sh)
        # SAT=$(cat $STYLE_DIR/$MOD_RANGES | grep "sat" | ${SCRIPT_DIR}/random_in_range.sh)
        # VALUE=$(cat $STYLE_DIR/$MOD_RANGES | grep "val" | ${SCRIPT_DIR}/random_in_range.sh)
    fi

    for S in "0" "1"; do
        EXAMPLAR=${SOURCE}/style${S}.png

        FGIMG=${STYLE_DIR}/${FG}_${S}.png
        COLOR_FG=${TMPDIR}/fg${S}_$X.png
        COLOR=${TMPDIR}/color${S}_$X.png
        COLOR_BG=${TMPDIR}/bg${S}.png

        if [ "$RANDOMIZE_COLOR" -eq "1" ]; then
            echo "Shifting color $X by H,S,V $HUE,$SAT,$VALUE"
            #echo "convert $FGIMG -modulate ${VALUE},${SAT},${HUE} $COLOR_FG"
            convert $FGIMG -modulate ${VALUE},${SAT},${HUE} $COLOR_FG
        else
            cp $FGIMG $COLOR_FG
        fi
        convert  -gravity center -composite $COLOR_BG $COLOR_FG $COLOR

        if [ "$X" -eq "0" ]; then
            cp $COLOR $EXAMPLAR
        else
            convert $EXAMPLAR $COLOR +append $EXAMPLAR
        fi
    done
done

rm -rf $TMPDIR
