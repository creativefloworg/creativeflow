#!/usr/bin/env python
"""
CREATES DEPTH IMAGES FROM DEPTH ARRAYS.

Background:
------------------------------------------------------------------------------
Depth arrays take a lot of storage space. We also render out images by
normalizing depth range to 0..255 (across the whole frame sequence).
The actual depth range is stored in the accompanying text file.
"""

import argparse
import glob
import numpy as np
import os
import re
from skimage.io import imsave


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Converts a directory of depth arrays and a depth range ' +
        'to a set of normalized depth images.')
    parser.add_argument(
        '--depth_array_dir', action='store', type=str, required=True,
        help='Directory for depth files, in numpy binary.')
    parser.add_argument(
        '--depth_range_file', action='store', type=str, required=True,
        help='File encoding depth range (min <space> max')
    parser.add_argument(
        '--depth_img_odir', action='store', type=str, required=True,
        help='Output directory for depth image files, will output png.')
    args = parser.parse_args()

    fpattern = os.path.join(args.depth_array_dir, '*')
    files = glob.glob(fpattern)
    files.sort()

    if len(files) == 0:
        raise RuntimeError('No files found matching %s' % fpattern)

    with open(args.depth_range_file) as f:
        elems = f.readlines()[0].strip().split()
        if len(elems) < 4:
            raise RuntimeError('Cannot parse depth range and shape from %s' %
                               args.depth_range_file)

        depth_range = [ float(elems[0]), float(elems[1]) ]
        dshape = [ int(x) for x in elems[2:] ]
        print('Parsed depth range, shape')
        print(depth_range)
        print(dshape)
    depth_denom = max(0.0001, depth_range[1] - depth_range[0])

    def _make_ofile(infile):
        bname = os.path.basename(infile)
        r = re.match('[a-z]+([0-9]+).[a-z]+', bname)
        if r is None:
            bname = infile + '.png'
        else:
            bname = 'depth%s.png' % r.group(1)
        return os.path.join(args.depth_img_odir, bname)

    for f in files:
        depth = np.fromfile(f, dtype=np.float32).reshape(dshape)
        dimg = ((1.0 - (depth[:,:,0] - depth_range[0]) / depth_denom) * 255).clip(0, 255).astype(np.uint8)
        imsave(_make_ofile(f), dimg)
