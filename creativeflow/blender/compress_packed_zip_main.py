#!/usr/bin/env python
"""
COMPRESSES A SPECIAL ZIP FILE WITH FLOW, DEPTH OR IMAGES.
"""
import argparse
import os
import skimage.io

import io_util


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Decompresses a special flows or arrays zip (see io_util.py)')
    parser.add_argument(
        '--output_zip', action='store', type=str, required=True)
    parser.add_argument(
        '--input_type', action='store', type=str, required=True,
        help='Must specify whether the ZIP stores packed flows or images: ' +
        'set to FLOW or PNG (ARRAY not supported)')
    parser.add_argument(
        '--input_dir', action='store', type=str, required=True,
        help='Directory containing input flows or images.')
    args = parser.parse_args()

    if args.input_type == 'FLOW':
        io_util.compress_flows(args.input_dir, args.output_zip)
    elif args.input_type == 'PNG':
        io_util.compress_images(args.input_dir, args.output_zip, read_function=skimage.io.imread)
    else:
        raise RuntimeError('Unrecognized --input_type=%s . Must use FLOW or PNG.' %
                           args.input_type)
