#!/bin/bash

set -o nounset

# Get the directory where current script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

USAGE="$0 <flags> dir0 dir1 extension

Flags:
-o one-way; will only check that dir0/fileX has a counterpart in dir1
-a channels to check in dir0; only applicable to images
-b channels to check against in dir1; only applicable to images
-t maximum per-file average pixel L1 error threshold to accept
-r allow image resize
"

ONEWAY=0
ACHAN=""
BCHAN=""
THRESH="0"
EXTRA_FLAGS=""
while getopts ':a:b:t:orh' option; do
    case "$option" in
        a) ACHAN=$OPTARG
           ;;
        b) BCHAN=$OPTARG
           ;;
        t) THRESH=$OPTARG
           ;;
        o) ONEWAY=1
           ;;
        r) EXTRA_FLAGS="$EXTRA_FLAGS --allow_resize"
           ;;
        h) echo "$USAGE"
           exit 0
           ;;
        \?) printf "ERROR! illegal option: -%s\n" "$OPTARG" >&2
            echo "$USAGE"
            exit 1
            ;;
    esac
done
shift $((OPTIND - 1))

if [ $# -lt 3 ]; then
    echo "$USAGE"
    exit
fi

DIR0=$1
DIR1=$2
EXT=$3

if [ ! -d "$DIR0" ]; then
    echo "Directory not found: $DIR0 "
    exit 1
fi

if [ ! -d "$DIR1" ]; then
    echo "Directory not found: $DIR1 "
    exit 1
fi

# Step 1: check file lists with the given extension
for F in $(find $DIR0 -type f -name "*.$EXT"); do
    BNAME=$(basename $F)
    if [ ! -f "$DIR1/$BNAME" ]; then
        echo "File $BNAME found in $DIR0 is missing from $DIR1"
        exit 1
    fi
done
NFILES=$(find $DIR0 -type f -name "*.$EXT" | wc -l | awk '{printf "%s", $1;}')
echo "OK: All $NFILES files with extension $EXT in $DIR0 also found in $DIR1"

if [ "$ONEWAY" -ne "1" ]; then
    for F in $(find $DIR1 -type f -name "*.$EXT"); do
        BNAME=$(basename $F)
        if [ ! -f "$DIR0/$BNAME" ]; then
            echo "File $BNAME found in $DIR1 is missing from $DIR0"
            exit 1
        fi
    done
    NFILES=$(find $DIR1 -type f -name "*.$EXT" | wc -l | awk '{printf "%s", $1;}')
    echo "OK: All $NFILES files with extension $EXT in $DIR1 also found in $DIR0"
fi


# Step 2: actually check the contents of each file
for F in $(find $DIR0 -type f -name "*.$EXT"); do
    BNAME=$(basename $F)
    ${SCRIPT_DIR}/check_files_similar.py $EXTRA_FLAGS \
                 --file0=$F \
                 --file1=$DIR1/$BNAME \
                 --channels0=$ACHAN \
                 --channels1=$BCHAN \
                 --thresh=$THRESH

    if [ $? -eq "0" ]; then
        echo "OK: file $BNAME within $THRESH per-pixel difference"
    else
        echo "FAIL: file $BNAME differs beyond $THRESH"
        exit 1
    fi
done
