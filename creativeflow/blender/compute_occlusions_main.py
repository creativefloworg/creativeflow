#!/usr/bin/env python
"""
ESTIMATE OCCLUSIONS.

Background:
------------------------------------------------------------------------------
For a pixel (x,y) in frame I0, if back flow at location (x,y)+flow0 in frame I1
disagrees with flow in frame I0 by a given threshold, we mark it as occluded.
Note that the same method was used for MIP Sintel flow dataset. We use a sightly
higher threshold of 0.5 pixels by default, because our resolution is higher.

Note:
------------------------------------------------------------------------------
This main function is not used for pipeline.sh, as occuslions are also computed
in unpack_exr_main.py.

"""
import argparse
import os
from skimage.io import imsave

import flow_util
import io_util

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Computes occlusions by finding forward-back flow discrepancies '
        'over the provided threshold.')
    parser.add_argument(
        '--flow_pattern', action='store', type=str, required=True)
    parser.add_argument(
        '--backflow_pattern', action='store', type=str, required=True)
    parser.add_argument(
        '--threshold', action='store', type=float, default=0.5)
    parser.add_argument(
        '--odir', action='store', type=str, required=True)
    parser.add_argument(
        '--frames', action='store', type=str, default='',
        help='CSV string of frame numbers to process; otherwise process all; e.g. '
        '--frames="1,5,7".')
    args = parser.parse_args()

    data = {}
    io_util.parse_file_sequence(args.flow_pattern, data, 'flow')
    io_util.parse_file_sequence(args.backflow_pattern, data, 'backflow')

    legit_frames = [ k for k in data.keys() if
                     ('flow' in data[k] and k+1 in data and 'backflow' in data[k+1]) ]
    if len(args.frames) > 0:
        frames = [ int(x) for x in args.frames.split(',') if int(x) in legit_frames ]
        print('Only processing frames %s out of %s' % (str(frames), str(legit_frames)))
        legit_frames = frames
    else:
        print('Processing frames %s' % str(legit_frames))
    legit_frames.sort()

    for f in legit_frames:
        flow = io_util.read_flow(data[f]['flow'])
        backflow = io_util.read_flow(data[f+1]['backflow'])
        occ_fname = os.path.join(args.odir, 'occlusions%06d.png' % f)
        occ = flow_util.get_occlusions_vec(flow, backflow,
                                           pixel_threshold=args.threshold)
        imsave(occ_fname, occ)
