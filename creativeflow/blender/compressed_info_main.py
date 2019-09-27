#!/usr/bin/env python
"""
PRINTS INFO FROM ZIP FILE OF FLOWS.

Background:
------------------------------------------------------------------------------
Allows collecting statistics about flow stored in zip files without
storing decompressed data on disk (takes *a lot* of space).

See decompress_packed_zip_main.py for details.
"""
import io_util
import glob
import os
import numpy as np
from skimage.io import imread

import argparse

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Gets information from a compressed flow zip or dir')
    parser.add_argument(
        '--flowzip', action='store', type=str, default='',
        help='If set, will read all flows in a special compressed flow zip.')
    parser.add_argument(
        '--flowdir', action='store', type=str, default='',
        help='If set, will read all flows in dir.')
    parser.add_argument(
        '--objiddir', action='store', type=str, default='',
        help='If set, will pair flow with objectid mask and only consider flows ' +
        'where ID is non-zero.')
    parser.add_argument(
        '--out_file', action='store', type=str, required=True)
    args = parser.parse_args()

    if len(args.flowzip) == 0 and len(args.flowdir) == 0:
        raise RuntimeError('Must set either --flowzip or --flowdir')
    elif len(args.flowzip) > 0 and len(args.flowdir) > 0:
        raise RuntimeError('Must only set one of --flowzip or --flowdir')

    F = []
    fnames = []
    nflows = []
    if len(args.flowzip) > 0:
        F = io_util.decompress_flows(args.flowzip)
        nflows = len(F)
        print('Read %d flows from zip' % nflows)
    else:
        fnames = glob.glob(os.path.join(args.flowdir, '*.flo'))
        fnames.sort()
        nflows = len(fnames)
        print('Found %d flow files' % nflows)

    thresh = 0.1
    motion_frames = 0
    motion_pixels = 0
    lines = []
    bins = []
    # Bins in terms of frame max percent
    perc_bins = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 30, 40, 50.0], dtype=np.float32)
    width = 0
    height = 0
    for i in range(nflows):
        if len(F) > 0:
            flow = F[i]
        else:
            flow = io_util.read_flow(fnames[i])

        if len(args.objiddir) > 0:
            obj_file = os.path.join(args.objiddir, 'objectid%06d.png' % (i+1))
            if not os.path.isfile(obj_file):
                raise RuntimeError('Could not find %s' % obj_file)

            ids = imread(obj_file)
            ids = ids[:, :, 0:3]  # In case RGBA
            ids = np.sum(ids, axis=2)
            mult = np.zeros(ids.shape, dtype=flow.dtype)
            mult[ids > 0] = 1.0
            flow = flow * np.expand_dims(mult, axis=2)

        width = flow.shape[0]
        height = flow.shape[1]
        npixels = float(flow.shape[0] * flow.shape[1])
        magnitudes = np.sqrt(np.sum(np.square(flow), axis=2))
        max_val = np.max(magnitudes)
        nmoving = np.sum(magnitudes > thresh)
        if nmoving > 0:
            fbins = perc_bins / 100.0 * max(width, height)
            bins = np.array([thresh, 1] + fbins.tolist())
            hist, _ = np.histogram(magnitudes, range=(thresh, max_val),
                                   bins=bins[bins < max_val].tolist() + [max_val])
            motion_frames += 1
            motion_pixels += nmoving / npixels
        else:
            hist = np.array([], dtype=np.int64)
        hist = hist.tolist()
        if len(hist) < len(perc_bins) + 3:
            hist = hist + [0 for x in range(len(perc_bins) + 3 - len(hist))]
        lines.append('F%d %0.5f %s\n' %
                     (i+1, nmoving / npixels * 100, ' '.join([str(x) for x in hist])))
        print(lines[-1][0:-1])

    if motion_frames > 0:
        motion_pixels /= motion_frames

    with open(args.out_file, 'w') as f:
        f.write('SHAPE: %d %d\n' % (width, height))
        f.write('FRAMES: %d %d %f\n' % (nflows, motion_frames, motion_pixels))
        f.write('BINS: %s\n' % ' '.join([str(x) for x in bins]))
        f.writelines(lines)
