#!/bin/bash -e
set -o nounset

LINE=$1
OFILE=$2

LICENSE=$(echo "$LINE" | awk -F'|' '{printf "%s", $4}')
if [ "$LICENSE" == "cc by" ]; then
    LICENSE="$LICENSE (https://creativecommons.org/licenses/by/4.0/)"
elif [ "$LICENSE" == "cc by-nc" ]; then
    LICENSE="$LICENSE (https://creativecommons.org/licenses/by-nc/4.0/)"
else
    echo "Unknown license \"$LICENSE\""
    exit 1
fi

ARTIST=$(echo $LINE | awk -F'|' '{printf "%s (%s)", $6, $5}')
IMID=$(echo $LINE | awk -F'|' '{printf "%s", $2}')

cat > $OFILE <<EOF
Files in this directory are licensed under Creative Commons Attribution-NonCommercial License:
https://creativecommons.org/licenses/by-nc/4.0/.

The background of this clip is a work by $ARTIST,
used under $LICENSE.
The original image has been cropped, rescaled and composited with rendered images.
The URL of the original image can be obtained from the Behance Artistic Media Dataset
(https://bam-dataset.org) V1 by looking up image id $IMID.
EOF
