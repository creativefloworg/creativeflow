#!/usr/bin/env python

import os
import numpy as np
import skimage
import skimage.transform
import sys
from skimage.io import imread

import argparse

#  Add .. to search path, to avoid running as module
__sdir = os.path.join(os.path.dirname(os.path.realpath(__file__)), os.pardir, os.pardir)
if __sdir not in sys.path:
    sys.path.append(__sdir)

import creativeflow.blender.io_util as io_util


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description='Checks common file types for similarity.')
    parser.add_argument(
        '--file0', action='store', type=str, required=True)
    parser.add_argument(
        '--file1', action='store', type=str, required=True)
    parser.add_argument(
        '--allow_resize', action='store_true', default=False,
        help='If set, will resize to smaller size before comparing.')
    parser.add_argument(
        '--channels0', action='store', type=str, default='')
    parser.add_argument(
        '--channels1', action='store', type=str, default='')
    parser.add_argument(
        '--thresh', action='store', type=float, default=0.0)
    args = parser.parse_args()

    def _get_extension(fname):
        bname = os.path.basename(fname)
        parts = bname.split('.')
        if len(parts) > 1:
            return parts[-1]
        return ''

    def _read_file(fname):
        ext = _get_extension(fname)
        if ext == 'flo':
            res = io_util.read_flow(fname)
        elif ext == 'array':
            res = np.fromfile(fname)
        else:
            res = skimage.img_as_float(imread(fname))
            if len(res.shape) == 2:  # Ensure has channels
                res = np.expand_dims(res, axis=2)
        return res

    def _parse_channels(chstr):
        return [int(x) for x in chstr.split(',')]

    def _check_channel_range(channels, arr, fname):
        for i in channels:
            if i >= arr.shape[2]:
                raise RuntimeError('File %s only has %d channels; %d channel requested' %
                                   (fname, arr.shape[2], i))

    f0 = _read_file(args.file0)
    f1 = _read_file(args.file1)

    if len(args.channels0) > 0 or len(args.channels1) > 0:
        ch0 = _parse_channels(args.channels0)
        ch1 = _parse_channels(args.channels1)
        if len(ch0) != len(ch1):
            raise RuntimeError('Cannot compare %d channels in one array to %d channels in another' %
                               (len(ch0), len(ch1)))

        if len(f0.shape) != 3 and len(f1.shape) != 3:
            raise RuntimeError('Cannot specify channels for non-3D inputs with shapes %s, %s' %
                               (str(f0.shape), str(f1.shape)))

        if f0.shape[0] != f1.shape[0] or f0.shape[1] != f1.shape[1]:
            raise RuntimeError('Array shapes disagree: %s vs %s' %
                               (str(f0.shape), str(f1.shape)))

        _check_channel_range(ch0, f0, args.file0)
        _check_channel_range(ch1, f1, args.file1)
        f0 = f0[:,:,ch0]
        f1 = f1[:,:,ch1]
    elif len(f0.shape) == 3 and len(f1.shape) == 3 and f0.shape[2] >= 3 and f1.shape[2] >= 3:
        # Make alpha comparison optional
        mchan = min(f0.shape[2], f1.shape[2])
        f0 = f0[:,:,0:mchan]
        f1 = f1[:,:,0:mchan]

    if args.allow_resize and (f0.shape[0] != f1.shape[0] or f0.shape[1] != f1.shape[1]):
        if f0.shape[2:] != f1.shape[2:]:
            raise RuntimeError('Incompatible array shapes even for resizing: %s vs %s' %
                               (str(f0.shape), str(f1.shape)))
        mshape = [ min(f0.shape[0], f1.shape[0]), min(f0.shape[1], f1.shape[2]) ] + f1.shape[2:]
        print('Resizing arrays from %s, %s to %s' % (str(f0.shape), str(f1.shape), str(mshape)))
        f0 = skimage.transform.resize(f0, mshape)
        f1 = skimage.transform.resize(f1, mshape)

    diff = np.sum(np.abs(f0 - f1))
    diff /= (1.0 * f0.shape[0] * f0.shape[1])
    if diff > args.thresh:
        raise RuntimeError('Average pixel difference %0.3f exceeds threshold=%0.3f' %
                           (diff, args.thresh))
