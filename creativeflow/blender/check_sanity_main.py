#!/usr/bin/env python
"""
RANDOMIZED METADATA INTEGRITY CHECKS.

Background:
------------------------------------------------------------------------------
Blender contains myriads of settings that can affect the rendering of flow
and other metadata. Because we render both flow and correspondences we can
perform sanity checks that these two complementary metadata types agree most
of the time. This file cross checks that flow and correspondences agree for
a sample of foreground pixels in a sample of consecutive frame pairs.

What are correspondences?
In order to render correspondences, we embed each object in the scene in
a bounding box in the first frame. Then, each vertex's RGB color is assigned
based on its normalized position inside the bounding box. Thus, each point
on the object is differentiated by color using the highest dynamic range possible
with simple RGB color. Together with the objectids, this allows approximate
tracking of any point on the object across many frames and even occlusions.

How are occlusions computed?
For a pixel (x,y) in frame I0, if back flow at location (x,y)+flow0 in frame I1
disagrees with flow in frame I0 by a given threshold, we mark it as occluded.
Note that the same method was used for MIP Sintel flow dataset.

How is the sanity check performed?
For a pixel (x,y) in frame I0, we look at location (x,y) + flow0 in frame I1.
We expect the colors in correspondence images at these two locations to be
very close, and for object ids to agree exactly, unless this pixel is marked
as occluded. Pixels passing this check are marked as sane.

Execution:
------------------------------------------------------------------------------
Sample invocation is:
./blender/check_sanity_main.py \
        --flow_pattern="$FLOWDIR/*.flo" \
        --objectid_pattern="$IDXDIR/*.png" \
        --corresp_pattern="$CORRDIR/*.png" \
        --occlusion_pattern="$OCCDIR/*.png" \
        --alpha_pattern="$ALPHADIR/*.png" \
        --debug_output_file="$DEBUG_SANITY_IMG" \
        --min_sanity=0.8 \
        --max_occlusion_frac=0.8 \
        --nframes=5 \
        --npixels=2000
"""
import argparse
import glob
import numpy as np
import random
from datetime import datetime
from skimage.io import imread, imsave

import flow_util
import io_util


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Performs randomized sanity checks on flow and correspondence agreement.')
    parser.add_argument(
        '--flow_pattern', action='store', type=str, required=True,
        help='Glob pattern for flow .flo files for all frames.')
    parser.add_argument(
        '--objectid_pattern', action='store', type=str, required=True,
        help='Glob pattern for object id PNG files for all frames.')
    parser.add_argument(
        '--corresp_pattern', action='store', type=str, required=True,
        help='Glob pattern for correspondence PNG files for all frames.')
    parser.add_argument(
        '--occlusion_pattern', action='store', type=str, required=True,
        help='Glob pattern for occlusion PNG files for all frames.')
    parser.add_argument(
        '--alpha_pattern', action='store', type=str, required=True,
        help='Glob pattern for alpha PNG files for all frames.')
    parser.add_argument(
        '--npixels', action='store', type=int, default=1000,
        help='Number of pixels to test per frame.')
    parser.add_argument(
        '--nframes', action='store', type=int, default=20,
        help='Number of frames to test; set to -1 to test all.')
    parser.add_argument(
        '--debug_output_file', action='store', type=str, default='',
        help='Image filename to write debug output frame to to illustrate types of errors.')
    parser.add_argument(
        '--debug_frame', action='store', type=int, default=-1,
        help='If set, will only run sanity checks on this particular frame.')
    parser.add_argument(
        '--debug_only_on_failure', action='store_true', default=False,
        help='If true and --debug_output_file is set; only produces debug image if the test fails.')
    parser.add_argument(
        '--min_sanity', action='store', type=float, default=1.0,
        help='Minimum sanity fraction that must be obtained, else script exits with an exception.')
    parser.add_argument(
        '--max_occlusion_frac', action='store', type=float, default=-1.0,
        help='If set to nonzero value, will fail if average '
        '# occluded pixels / # nonzero alpha pixels is greater than this value.')
    args = parser.parse_args()

    random.seed(datetime.now())

    def _make_file_ob():
        return { 'flow': None,
                 'objid': None,
                 'corr': None,
                 'occ': None,
                 'alpha': None }

    def _has_all_data(ob):
        return (ob['flow'] is not None and
                ob['objid'] is not None and
                ob['corr'] is not None and
                ob['occ'] is not None and
                ob['alpha'] is not None)

    def _has_obj_corr(ob):
        return (ob['objid'] is not None and
                ob['corr'] is not None)

    data = {}

    def _fill_data(files, datakey):
        for f in files:
            fnum_ = io_util.get_filename_framenumber(f)
            if fnum_:
                if fnum_ not in data:
                    data[fnum_] = _make_file_ob()
                data[fnum_][datakey] = f

    _fill_data(glob.glob(args.flow_pattern), 'flow')
    _fill_data(glob.glob(args.objectid_pattern), 'objid')
    _fill_data(glob.glob(args.corresp_pattern), 'corr')
    _fill_data(glob.glob(args.occlusion_pattern), 'occ')
    _fill_data(glob.glob(args.alpha_pattern), 'alpha')

    # Where next frame is also present
    legit_frames = [ k for k in data.keys() if
                     (_has_all_data(data[k]) and k+1 in data and _has_obj_corr(data[k+1])) ]
    random.shuffle(legit_frames)

    if len(legit_frames) == 0:
        raise RuntimeError('No frames with sufficient flow, ' +
                           'objid, correlations, occlusion, alpha data found.')

    # Check and count sanity ---------------------------------------------------
    sane_count = 0
    insane_count = 0
    num_frames_tested = 0
    occ_fraction_sum = 0

    if args.debug_frame >= 0:
        if args.debug_frame not in legit_frames:
            raise RuntimeError(
                'Cannot debug frame %d, not enough data. Use --debug_frame to set frame'
                % args.debug_frame)
        print('Computing sanity only for --debug_frame %d' % args.debug_frame)
        legit_frames = [args.debug_frame]

    if args.nframes < 0:
        args.nframes = len(legit_frames)
        legit_frames.sort()
    print('Evaluating sanity for %d frames out of: %s' % (args.nframes, str(legit_frames)))

    for i in range(min(args.nframes, len(legit_frames))):
        fnum = legit_frames[i]
        flow = io_util.read_flow(data[fnum]['flow'])
        objid = imread(data[fnum]['objid'])
        corr = imread(data[fnum]['corr'])
        occ = imread(data[fnum]['occ'])
        alpha = imread(data[fnum]['alpha'])

        next_objid = imread(data[fnum + 1]['objid'])
        next_corr = imread(data[fnum + 1]['corr'])

        # Select only non-transparent parts of the frame for a meaningful check
        rows,cols = np.nonzero(alpha)
        if rows.size == 0:
            print('Skipping frame %d: no non-zero alphas' % fnum)
            continue
        idxes = np.random.choice(len(rows), min(len(rows), args.npixels), replace=False)

        pixels_with_flow = np.sum(np.abs(flow) > 0.001)
        if pixels_with_flow == 0:
            print('Skipping frame %d: no pixels with nonzero flow' % fnum)

        # Check occlusions
        num_frames_tested += 1
        if args.max_occlusion_frac > 0:
            num_occluded = np.sum(np.logical_and(occ > 0, alpha > 0))
            occ_fraction_sum += float(num_occluded) / len(rows)

        # Check sanity
        frame_sane_count = 0
        frame_insane_count = 0
        for ix in idxes:
            row = rows[ix]
            col = cols[ix]

            is_sane = flow_util.cross_check_sanity(
                flow, objid, next_objid, corr, next_corr, occ, row, col, verbose=True)

            if not is_sane:
                print('Frame %d, (row,col) = (%d,%d) is not sane' % (fnum, row, col))
                insane_count += 1
                frame_insane_count += 1
            else:
                sane_count += 1
                frame_sane_count += 1
        frame_sanity = frame_sane_count / max(1.0, 1.0 * (frame_sane_count + frame_insane_count))
        print('Frame Sanity (fr %d) %0.2f: %d / %d' %
              (fnum, frame_sanity, frame_sane_count, frame_sane_count + frame_insane_count))

    test_count = sane_count + insane_count
    expected_test_count = min(args.nframes, len(legit_frames)) * args.npixels
    sanity = sane_count / (1.0 * test_count)
    print('Sanity %0.2f: %d / %d' % (sanity, sane_count, test_count))

    failed = (test_count < expected_test_count * 0.5) or (sanity < args.min_sanity)

    # Optional diagnostics -----------------------------------------------------
    if len(args.debug_output_file) > 0 and (not args.debug_only_on_failure or failed):
        if args.debug_frame < 0:
            args.debug_frame = legit_frames[0]

        if args.debug_frame not in legit_frames:
            raise RuntimeError(
                'Cannot debug frame %d, not enough data. Use --debug_frame to set frame'
                % args.debug_frame)

        fnum = args.debug_frame

        flow = io_util.read_flow(data[fnum]['flow'])
        objid = imread(data[fnum]['objid'])
        corr = imread(data[fnum]['corr'])
        occ = imread(data[fnum]['occ'])
        alpha = imread(data[fnum]['alpha'])

        next_objid = imread(data[fnum + 1]['objid'])
        next_corr = imread(data[fnum + 1]['corr'])

        res = np.zeros((flow.shape[0], flow.shape[1], 3), np.uint8)

        rows,cols = np.nonzero(alpha)
        for ix in range(len(rows)):
            row = rows[ix]
            col = cols[ix]

            sanity_type = flow_util.cross_check_sanity(
                flow, objid, next_objid, corr, next_corr, occ, row, col,
                output_sanity_type=True)
            if sanity_type == 0:
                res[row][col][1] = 255  # green
            elif sanity_type == 1:
                res[row][col][0] = 255  # white
                res[row][col][1] = 255
                res[row][col][2] = 255
            elif sanity_type == 2:
                res[row][col][0] = 255  # yellow
                res[row][col][1] = 255
            elif sanity_type == 3:
                res[row][col][0] = 255  # orange
                res[row][col][1] = 150
            elif sanity_type == 4:
                res[row][col][0] = 255  # red

        imsave(args.debug_output_file, res)

    # Perform the actual test --------------------------------------------------
    if test_count < expected_test_count * 0.5:
        raise RuntimeError(
            'Less than 50%% of expected number of frames tested: %d vs %d\n (Alphas: %s)' %
            (expected_test_count, test_count, args.alpha_pattern))

    if sanity < args.min_sanity:
        raise RuntimeError(
            'Failed minimum sanity check: %0.2f (%0.2f required)' % (sanity, args.min_sanity))

    occ_fraction = occ_fraction_sum / num_frames_tested
    if args.max_occlusion_frac > 0 and occ_fraction > args.max_occlusion_frac:
        raise RuntimeError(
            'Failed max occlusion check: %0.2f (max %0.2f allowed) for %d frames' %
            (occ_fraction, args.max_occlusion_frac, num_frames_tested))
