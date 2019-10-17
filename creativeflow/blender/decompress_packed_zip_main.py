#!/usr/bin/env python
"""
DECOMPRESS A SPECIAL ZIP FILE WITH FLOW OR DEPTH.

IMPORTANT:
------------------------------------------------------------------------------
If you are simply decompressing the Creative Flow dataset, you may want to
simply run our decompression script: datagen/pipeline_decompress.sh

Background:
------------------------------------------------------------------------------
The flow and uncompressed depth files are very large.
We compress these files into special zip files, one per animation sequence.
If we simply zip up a directory of .flo files the compression is drastically
worse than if we first concatenate flows into a single numpy array and zip
up that. This main decompresses these special zip files.
"""
import argparse
import os
import skimage.io

import io_util


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Decompresses a special flows or arrays zip (see io_util.py)')
    parser.add_argument(
        '--input_zip', action='store', type=str, required=True)
    parser.add_argument(
        '--input_type', action='store', type=str, required=True,
        help='Must specify whether the ZIP stores packed flows or general arrays: ' +
        'set to FLOW, PNG or ARRAY')
    parser.add_argument(
        '--output_pattern', action='store', type=str, required=True,
        help='Specify output per-frame file format, e.g. /OUTDIR/flow%06d.flo; ' +
        'note that all frames will be 1-based.')
    args = parser.parse_args()

    odir = os.path.dirname(args.output_pattern)
    obasename = os.path.basename(args.output_pattern)
    if args.input_type == 'FLOW':
        flows = io_util.decompress_flows(
            args.input_zip, output_dir=odir, outfile_pattern=obasename)
    elif args.input_type == 'PNG':
        images = io_util.decompress_images(
            args.input_zip, write_function=skimage.io.imsave, output_dir=odir, outfile_pattern=obasename)
    elif args.input_type == 'ARRAY':
        arrays = io_util.decompress_arrays(
            args.input_zip, output_dir=odir, outfile_pattern=obasename)
    else:
        raise RuntimeError('Unrecognized --input_type=%s . Must use FLOW or ARRAY.' %
                           args.input_type)
