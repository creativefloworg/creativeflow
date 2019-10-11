#!/usr/bin/env python

import argparse
import random

import numpy as np
import numpy.linalg as nplg

if __name__ == "__main__":
    # FLAGS
    # --------------------------------------------------------------------------
    parser = argparse.ArgumentParser(
        description='Picks imagemagick modulation within range that is reasonably ' +
        'far from the modulations already done -- to ensure variety of materials.')

    parser.add_argument(
        '--past_modulations', action='store', type=str, required=True,
        help='File with past modulations of the form: hsv 100 200 150')
    parser.add_argument(
        '--modulation_ranges', action='store', type=str, required=True,
        help='File with 3 lines: hue MIN MAX; sat MIN MAX; val MIN MAX')
    parser.add_argument(
        '--n', action='store', type=str, default=7,
        help='Number of attempts to pick furthest modulation.')
    args = parser.parse_args()

    with open(args.past_modulations) as f:
        past_vals = [np.array([int(c) for c in v[1:]], dtype=np.float32)
                     for v in [x.strip().split() for x in f.readlines()]
                     if len(v) > 0]

    with open(args.modulation_ranges) as f:
        ranges = dict([(v[0], (int(v[1]), int(v[2])))
                       for v in [x.strip().split() for x in f.readlines()]
                       if len(v) > 0])

    if 'val' not in ranges and 'value' in ranges:
        ranges['val'] = ranges['value']

    if 'hue' not in ranges or 'sat' not in ranges or 'val' not in ranges:
        raise RuntimeError('Did not find hue/val/sat in %s' % args.modulation_ranges)

    largest_dist = -1
    furthest_val = None
    for i in range(args.n):
        val = np.array(
            [random.randint(ranges['hue'][0], ranges['hue'][1]),
             random.randint(ranges['sat'][0], ranges['sat'][1]),
             random.randint(ranges['val'][0], ranges['val'][1])],
            dtype=np.float32)
        if len(past_vals) == 0:
            furthest_val = val
            break

        best_dist = -1
        for pval in past_vals:
            dist = nplg.norm(val - pval)
            if best_dist < 0 or dist < best_dist:
                smallest_dist = dist
        if largest_dist < 0 or best_dist > largest_dist:
            furthest_val = val
            largest_dist = best_dist

    print('%d %d %d' % (int(furthest_val[0]), int(furthest_val[1]), int(furthest_val[2])))
