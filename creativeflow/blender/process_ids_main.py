#!/usr/bin/env python
"""
PROCESS IDS IMAGES INTO STYLE TAG IMAGES FOR STYLIT.

Background:
------------------------------------------------------------------------------
For some of Creative Flow styles we use Stylit stylization technique
(Fiser et al, SIGGRAPH 2016). One of the inputs is an image tagging styles in
the target images with style tags available in the exemplar. Because we have
a limited number of exemplars and we only randomize colors sometimes, we
typically have fewer style tags than objectids. This script turns objectids
images into images with a specific number of style tags by grouping labels.

This script is also used to create style-tagged image for style exemplars,
where a random number of color variations of original style may be created
programmatically.
"""

import argparse
import glob
import numpy as np
import os
import random
from skimage.io import imread, imsave

from misc_util import generate_unique_colors


def get_unique_colors(img):
    return np.unique(img.reshape(-1, img.shape[2]), axis=0)


def read_image(fname):
    img = imread(fname).astype(np.uint8)
    if len(img.shape) == 2:
        img = np.expand_dims(img, axis=2)
    if img.shape[2] > 3:
        img = img[:,:,0:3]
    elif img.shape[2] == 1:
        img = np.tile(img, [1,1,3])
    return img


class UniqueColors(object):
    def __init__(self):
        self.colors = []
        self.counts = []
        self.nimages = 0
        self.index = {}


    def to_file(self, fname):
        with open(fname, 'w') as f:
            f.write(' '.join([ ('%0.7f' % x) for x in self.counts ]) + '\n')
            f.write(' '.join([ ('%d %d %d' % (x[0], x[1], x[2])) for x in self.colors ]) + '\n')
            f.write('%d\n' % self.nimages)
            f.write(' '.join([ ('%d %d' % (x[0], x[1])) for x in self.index.items() ]) + '\n')


    def from_file(self, fname):
        if not os.path.isfile(fname):
            raise RuntimeError('File does not exist or empty name: %s' % fname)

        with open(fname) as f:
            lines = f.readlines()
            lines = [x.strip() for x in lines]
        counts = [ float(x) for x in lines[0].split() if len(x) > 0 ]
        colors = [ int(x) for x in lines[1].split() if len(x) > 0 ]
        nimages = int(lines[2])
        index = [ int(x) for x in lines[3].split() if len(x) > 0 ]

        if len(counts) * 3 != len(colors) or len(counts) * 2 != len(index):
            raise RuntimeError('Malformed file: %d counts, %d colors, %d index' %
                               (len(counts), len(colors), len(index)))

        self.counts = counts
        self.colors = [np.array([colors[i*3], colors[i*3 + 1], colors[i*3 + 2]],
                                dtype=np.uint8)
                       for i in range(len(counts)) ]
        self.index = dict([ (index[i*2], index[i*2 + 1])
                            for i in range(len(counts)) ])
        self.nimages = nimages


    def __idx(self, color_row):
        return (color_row[0] << 16) + (color_row[1] << 8) + color_row[2]


    def add_image_colors(self, img):
        colors,counts = np.unique(img.reshape(-1, img.shape[2]), axis=0, return_counts=True)

        for c in range(colors.shape[0]):
            color = colors[c, :]
            count = counts[c] / float(img.shape[0] * img.shape[1])
            idx = self.__idx(color)
            if idx in self.index:
                self.counts[self.index[idx]] = (
                    self.nimages / (self.nimages + 1.0) *
                    self.counts[self.index[idx]] + count / (self.nimages + 1.0))
            else:
                self.colors.append(color)
                self.counts.append(count / (self.nimages + 1.0))
                self.index[idx] = len(self.colors) - 1
        self.nimages += 1


    def num(self):
        return len(self.colors)


    def has_black(self):
        return self.__idx([0,0,0]) in self.index


    def sorted(self, no_black=True):
        res = list(zip(self.counts, [x.tolist() for x in self.colors]))
        if no_black and self.has_black():
            del res[self.index[self.__idx([0,0,0])]]
        res.sort(reverse=True)
        print('Color usage:')
        print(res)
        return [x[1] for x in res]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Processes output object ids for the purpose of applying ' +
        'stylit stylization method.')
    parser.add_argument(
        '--ids_images', action='store', type=str, required=True,
        help='Image files with rendered image IDs, a glob; in the case of ' +
        'an animated sequence, all frame renders should be input at once, as ' +
        'some objects may be hidden in some scenes, causing inconsistencies.')
    parser.add_argument(
        '--from_src_template', action='store_true', default=False,
        help='If set, will assume that ids image is an ids template with ' +
        'only one non-zero color and will concatenate copies of this image ' +
        'with unique color id set instead.')
    parser.add_argument(
        '--nids', action='store', type=int, default=-1,
        help='Desired number of output IDs; required for --from_src_template and ' +
        'in the other case caps the total number of ids created (e.g. if input ' +
        'files have fewer total ids, fewer will be present in the outputs.')
    parser.add_argument(
        '--save_colors_file', action='store', type=str, default='',
        help='If true, (and not --from_src_template), will save all the colors ' +
        'in a checkpoint and skip analysis of existing colors step next time.')
    parser.add_argument(
        '--out_dir', action='store', type=str, required=True,
        help='Output directory to write to; basename(s) will be same as for ids_images.')
    args = parser.parse_args()

    input_files = glob.glob(args.ids_images)
    if len(input_files) == 0:
        raise RuntimeError('No files matched glob %s' % args.ids_images)

    ucolors = UniqueColors()
    if args.from_src_template:
        if len(input_files) > 1:
            raise RuntimeError('Cannot process more than one file with --from_src_template')
        if args.nids <= 0:
            raise RuntimeError('Must specify --nids when running with --from_src_template')

        img = read_image(input_files[0])
        ucolors.add_image_colors(img)

        if not ucolors.has_black() or ucolors.num() != 2:
            print(ucolors.colors)
            raise RuntimeError(
                'Error processing %s with --from_src_template: '
                'template must have 2 colors, exactly one black, but '
                ' %d colors found' %
                (args.ids_image, len(ucolors.colors)))
        res = np.zeros((img.shape[0], img.shape[1] * args.nids, 3), dtype=np.uint8)
        out_colors = generate_unique_colors(args.nids)

        for c in range(args.nids):
            not_black = (img[:,:,0] != 0) | (img[:,:,1] != 0) | (img[:,:,2] != 0)
            img[not_black] = np.array(out_colors[c], dtype=np.uint8)
            res[:, c * img.shape[1]:(c+1) * img.shape[1], :] = img

        out_file = os.path.join(args.out_dir, os.path.basename(input_files[0]))
        imsave(out_file, res)
    else:
        # First we read all the image files and establish a consistent mapping
        # for all unique input colors
        try:
            ucolors.from_file(args.save_colors_file)
            print('Restored color list from checkpoint: %s' % args.save_colors_file)
        except Exception as e:
            if len(args.save_colors_file) > 0:
                print('Could not restore colors from checkpoint %s' % args.save_colors_file)
                print(e)

            for fname in input_files:
                img = read_image(fname)
                ucolors.add_image_colors(img)
                print('Processed colors in %s ' % fname)

            if len(args.save_colors_file) > 0:
                ucolors.to_file(args.save_colors_file)

        print('Found %d unique colors (%s black) in %d input files' %
              (ucolors.num(),
               ('with' if ucolors.has_black() else 'no'),
               len(input_files)))
        print(ucolors.colors)

        nids = ucolors.num() - (1 if ucolors.has_black() else 0)
        if args.nids > 0:
            print('Capping nids %d by %d' % (nids, args.nids))
            nids = min(args.nids, nids)

        with open(os.path.join(args.out_dir, 'N.txt'), 'w') as f:
            f.write('%d' % nids)

        input_colors = ucolors.sorted(no_black=True)
        out_colors = generate_unique_colors(nids)

        mapping = [0 for x in range(len(input_colors))]
        for c in range(len(input_colors)):
            if c < len(out_colors):
                mapping[c] = c
            else:
                mapping[c] = random.randint(0, len(out_colors) - 1)

        print('Mapping:')
        print(mapping)

        # Now read all files and apply the mapping again
        for fname in input_files:
            img = read_image(fname)
            result = np.copy(img)

            for c in range(len(input_colors)):
                selected = (img[:,:,0] == input_colors[c][0]) & \
                           (img[:,:,1] == input_colors[c][1]) & \
                           (img[:,:,2] == input_colors[c][2])
                result[selected] = np.array(out_colors[mapping[c]], dtype=np.uint8)

            out_file = os.path.join(args.out_dir, os.path.basename(fname))
            imsave(out_file, result)
            print('Processed %s' % out_file)
