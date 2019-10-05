#!/usr/bin/env python

import os
import logging
import sys

import argparse

logger = logging.getLogger(__name__)

#  Add .. to search path, to avoid running as module
__sdir = os.path.join(os.path.dirname(os.path.realpath(__file__)), os.pardir, os.pardir)
if __sdir not in sys.path:
    sys.path.append(__sdir)

import creativeflow.blender.dataset_util as dataset_util


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Checks expanded paths for specific data types.')
    parser.add_argument(
        '--sequences_file', action='store', type=str, required=True,
        help='Sequences file list.')
    parser.add_argument(
        '--base_dir', action='store', type=str, required=True,
        help='Base directory into which the dataset has been decompressed.')
    parser.add_argument(
        '--datatypes', action='store', type=str, required=True,
        help='dataset_util.DataType elements, csv, e.g. "FLOW,RENDER_COMPOSITE"')
    parser.add_argument(
        '--fail_fast', action='store_true', default=False,
        help='If set, will fail with the first missing file.')
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG)

    data_types = [dataset_util.DataType[x] for x in args.datatypes.split(',')]
    require_flow = dataset_util.DataType.FLOW in data_types
    helper = dataset_util.DatasetHelper(args.sequences_file, require_flow=require_flow)
    success = helper.check_files(args.base_dir, data_types, fast_fail=args.fail_fast)

    if not success:
        raise RuntimeError('Failed to find files')
