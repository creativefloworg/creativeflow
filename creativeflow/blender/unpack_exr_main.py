#!/usr/bin/env python
"""
UNPACK FLOW, BACKFLOW, DEPTH FROM MULTILAYER EXR FILES OUTPUT BY BLENDER.

Background:
------------------------------------------------------------------------------
In order to extract flow and depth from Blender rendering pipeline we write
multilayer EXR files (https://www.openexr.com/). This main extracts flow,
backflow and depth from these files and writes them to file, also writing
compressed versions, if requested. In addition, we compute occlusions
in the same way as described in compute_occlusions_main.py.

Requirements:
------------------------------------------------------------------------------
IMPORTANT! This was only tested for EXR files output using our scripted
pipeline and Blender 2.79 API.
"""
import argparse
import glob
import numpy as np
import os
import re
import time
from skimage.io import imsave

import exr_util
import flow_util
import io_util
from misc_util import QuickTimer


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description='Unpacks multilayer exr from blender to flow, depth.')
    parser.add_argument(
        '--input_dir', action='store', type=str, required=True,
        help='Input directory with exr files, one per frame.')

    parser.add_argument(
        '--flow_odir', action='store', type=str, default='',
        help='Output directory for flow files, if set will output in flo format.')
    parser.add_argument(
        '--back_flow_odir', action='store', type=str, default='',
        help='Output directory for back flow files, if set will output in flo format.')
    parser.add_argument(
        '--depth_odir', action='store', type=str, default='',
        help='Output directory for depth files, if set will output in numpy binary.')
    parser.add_argument(
        '--depth_range_ofile', action='store', type=str, default='',
        help='Output file for aggregate depth range.')
    parser.add_argument(
        '--occlusions_odir', action='store', type=str, default='',
        help='Output directory for occlusion files, if set will output in image format.')

    parser.add_argument(
        '--flow_zip', action='store', type=str, default='',
        help='If set, will compress flow into a special zip; only runs if also --flow_odir.')
    parser.add_argument(
        '--back_flow_zip', action='store', type=str, default='',
        help='If set, will compress back flow into a special zip; only runs if also --back_flow_odir.')
    parser.add_argument(
        '--depth_zip', action='store', type=str, default='',
        help='If set, will compress depth into a special zip; only runs if also --depth_odir.')

    args = parser.parse_args()

    qtimer = QuickTimer()

    fpattern = os.path.join(args.input_dir, '*')
    files = glob.glob(fpattern)
    files.sort()

    if len(files) == 0:
        raise RuntimeError('No files found matching %s' % fpattern)

    def _make_ofile(infile, odir, extension, desired_basename):
        bname = os.path.basename(infile)
        r = re.match('[a-z]+([0-9]+).exr', bname)
        if r is None:
            bname = bname.strip('.exr')
        else:
            bname = '%s%s.%s' % (desired_basename, r.group(1), extension)
        return os.path.join(odir, bname)

    qtimer.start('parse_exr')
    meta = exr_util.read_exr_metadata(files[0])
    qtimer.end()
    dshape = meta['depth'].shape
    depth_range = None
    for i in range(len(files) - 1):
        fname = files[i]
        qtimer.start('I/O')
        if len(args.flow_odir) > 0:
            io_util.write_flow(meta['flow'], _make_ofile(fname, args.flow_odir, 'flo', 'flow'))
        if len(args.back_flow_odir) > 0:
            io_util.write_flow(meta['back_flow'], _make_ofile(fname, args.back_flow_odir, 'flo', 'backflow'))
        if len(args.depth_odir) > 0:
            # Note: depth has 2 channels - Z, alpha
            meta['depth'].reshape([-1]).tofile(_make_ofile(fname, args.depth_odir, 'array', 'depth'))
        qtimer.end()

        qtimer.start('depth_compute')
        if len(args.depth_range_ofile) > 0:
            D = meta['depth'][:, :, 0]  # depth
            A = meta['depth'][:, :, 1]  # alpha
            nonzeroD = D[A > 0]
            if nonzeroD.size > 0:
                if depth_range is None:
                    depth_range = [np.min(nonzeroD), np.max(nonzeroD)]
                else:
                    depth_range[0] = min(depth_range[0], np.min(nonzeroD))
                    depth_range[1] = max(depth_range[0], np.max(nonzeroD))
        qtimer.end()

        qtimer.start('parse_exr')
        meta2 = exr_util.read_exr_metadata(files[i+1])
        qtimer.end()
        if len(args.occlusions_odir) > 0:
            occ_fname = _make_ofile(fname, args.occlusions_odir, 'png', 'occlusions')
            qtimer.start('occlusions_compute')
            occ = flow_util.get_occlusions_vec(meta['flow'], meta2['back_flow'],
                                               pixel_threshold=0.5)
            qtimer.end()
            qtimer.start('I/O')
            imsave(occ_fname, occ)
            qtimer.end()
        meta = meta2

    if len(args.depth_range_ofile) > 0:
        if depth_range is None:
            raise RuntimeError(
                'Depth range cannot be computed: no non-transparent depths in %s' %
                args.input_dir)
        with open(args.depth_range_ofile, 'w') as f:
            f.write('%0.6f %0.6f %s\n' % (depth_range[0], depth_range[1],
                                          ' '.join([('%d' % x) for x in dshape])))

    qtimer.start('compression')
    if len(args.flow_zip) > 0:
        if len(args.flow_odir) == 0:
            raise RuntimeError('Sorry; --flow_zip is only written if --flow_odir is set.')
        else:
            io_util.compress_flows(args.flow_odir, args.flow_zip)

    if len(args.back_flow_zip) > 0:
        if len(args.back_flow_odir) == 0:
            raise RuntimeError('Sorry; --back_flow_zip is only written if --back_flow_odir is set.')
        else:
            io_util.compress_flows(args.back_flow_odir, args.back_flow_zip)

    if len(args.depth_zip) > 0:
        if len(args.depth_odir) == 0:
            raise RuntimeError('Sorry; --depth_zip is only written if --depth_odir is set.')
        else:
            io_util.compress_arrays(args.depth_odir, dshape, args.depth_zip)
    qtimer.end()

    print(qtimer.summary())
