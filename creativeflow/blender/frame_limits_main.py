#!/usr/bin/env python
"""
DETERMINE FRAME LIMITS WHERE MOTION IS PRESENT.

Background:
------------------------------------------------------------------------------
For randomly created blends with object and camera motion it is possible
that some frames contain no motion, or camera is points away from moving
objects. We run this script on quick-to-render objectid image sequences to
find frame sequences where motion is present.
"""
import argparse
import glob
import numpy as np
import os
import re
from skimage.io import imread


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Find sequences of consecutive frames where sufficient '
        'motion is present by looking at objectid renderings.')
    parser.add_argument(
        '--ids_images', action='store', type=str, required=True,
        help='Image files with rendered image IDs, a glob; in the case of ' +
        'an animated sequence, all frame renders should be input at once, as ' +
        'some objects may be hidden in some scenes, causing inconsistencies.')
    parser.add_argument(
        '--output_info_file', action='store', type=str, required=True,
        help='Will write frame limits here.')
    parser.add_argument(
        '--min_changed_pixel_frac', action='store', default=0.07,
        help='Minimum fraction of pixels that are changed in order to detect motion.')
    args = parser.parse_args()

    input_files = glob.glob(args.ids_images)
    input_files.sort()

    if len(input_files) == 0:
        raise RuntimeError('No files matched glob %s' % args.ids_images)

    def parse_frame_number(infile):
        bname = os.path.basename(infile)
        r = re.match('[a-z]+([0-9]+).[a-z]+', bname)
        if r is None:
            raise RuntimeError('Cannot parse frame number from %s' % bname)
        frame = int(r.group(1))
        return frame

    prev_img = imread(input_files[0]).astype(np.uint8)
    prev_num = parse_frame_number(input_files[0])
    npixels = prev_img.shape[0] * prev_img.shape[1]

    sequences = []
    start_frame = -1

    def __add_sequence(new_seq):
        if len(sequences) == 0 or new_seq[0] > sequences[-1][1] + 5:
            sequences.append(new_seq)
        else:  # extend if previous sequence ended recently
            sequences[-1][1] = new_seq[1]

    for i in range(1, len(input_files)):
        img = imread(input_files[i]).astype(np.uint8)
        num = parse_frame_number(input_files[i])

        if num != prev_num + 1:
            raise RuntimeError('Inconsistent frame numbers %s (%d) follows %s (%d)' %
                               (input_files[i], num, input_files[i-1], prev_num))

        diff = np.sum(np.nonzero(
            np.sum(np.abs(prev_img - img), axis=2))) / float(npixels)
        if diff > args.min_changed_pixel_frac:
            if start_frame < 0:
                start_frame = num - 1
        else:
            if start_frame >= 0:
                __add_sequence([start_frame, num - 1])
                start_frame = -1

        prev_img = img
        prev_num = num

    if start_frame >= 0:
        __add_sequence([start_frame, prev_num])

    sequences.sort(key=lambda x: x[1] - x[0], reverse=True)

    if len(sequences) == 0:
        raise RuntimeError('Found no sequences with enough motion in %s' % args.ids_images)

    if sequences[0][1] - sequences[0][0] < 5:
        raise RuntimeError('The moving sequence is too short')

    print('Found moving sequences: %s' % str(sequences))

    with open(args.output_info_file, 'w') as f:
        f.write('\n'.join(['%d %d' % (x[0], x[1]) for x in sequences]))
