import math
import numpy as np
import time


class QuickTimer(object):
    def __init__(self):
        self.timers = {}
        self.lastKey = None

    def start(self, key):
        if key not in self.timers:
            self.timers[key] = {'total': 0}
        self.timers[key]['start'] = time.time()
        self.lastKey = key

    def end(self, key=None):
        if not key:
            key = self.lastKey
        self.timers[key]['total'] += time.time() - self.timers[key]['start']

    def summary(self):
        summ = [(x[1]['total'], x[0]) for x in self.timers.items()]
        summ.sort()
        return '\n'.join(['TIMING %s %0.3f' % (x[1], x[0]) for x in summ])

def generate_unique_colors(num, no_black=True):
    # Want colors to be roughly same distance apart
    res = []
    subdivs = int(math.ceil(
        math.pow(float(num + (1 if no_black else 0)), 1/3.0)))
    delta = int(255 / (subdivs-1))
    total = 0
    for r in range(subdivs):
        for g in range(subdivs):
            for b in range(subdivs):
                if total >= num:
                    break

                if (not no_black) or (r != 0) or (g != 0) or (b != 0):
                    res.append([r * delta, g * delta, b * delta])
                    total += 1
    print('Unique colors:')
    print(res)
    return res

# EXPERIMENTAL SCRIPTS BELOW --------------------------------------------------


def get_points_perimeter(x, y, radius, width, height):
    if radius == 0:
        return [np.array([[y], [x]], dtype=np.int64)]

    pts = []
    top = y + radius
    bottom = y - radius
    left = x - radius
    right = x + radius


    def _cap_to(a, val):
        return int(min(max(0, a), val - 1))


    hor_coords = range(_cap_to(left, width), _cap_to(right, width) + 1)
    vert_coords = range(_cap_to(bottom, height), _cap_to(top, width) + 1)
    if top < height:
        pts.extend([np.array([[top], [w]], dtype=np.int64) for w in hor_coords])
    if bottom >= 0:
        pts.extend([np.array([[bottom], [w]], dtype=np.int64) for w in hor_coords])
    if left >= 0:
        pts.extend([np.array([[w], [left]], dtype=np.int64) for w in vert_coords])
    if right < width:
        pts.extend([np.array([[w], [right]], dtype=np.int64) for w in vert_coords])
    return pts


def set_perimeter_mask(zero_mask, x, y, radius):
    def _cap_to(a, val):
        return int(min(max(0, a), val - 1))


    width = zero_mask.shape[1]
    height = zero_mask.shape[0]
    x = _cap_to(x, width)
    y = _cap_to(y, height)

    if radius == 0:
        zero_mask[y, x] = True

    top = y + radius
    bottom = y - radius
    left = x - radius
    right = x + radius

    left_valid = _cap_to(left, width)
    right_valid = _cap_to(right, width)
    bottom_valid = _cap_to(bottom, height)
    top_valid = _cap_to(top, width)

    if top < height:
        zero_mask[top, left_valid:right_valid + 1] = True
    if bottom >= 0:
        zero_mask[bottom, left_valid:right_valid + 1] = True
    if left >= 0:
        zero_mask[bottom_valid:top_valid + 1, left] = True
    if right < width:
        zero_mask[bottom_valid:top_valid + 1, right] = True


def flow_from_corr(corr0, corr1, ids0, ids1, alpha, max_flow=30, flow_guess=None):
    """
    Slow, sloppily optimized and loosely tested function for adjusting flow estimate
    based on input correlation images (this was used to diagnose Blender bug for
    animated focal length).
    :param corr0: color correlation image for frame 0
    :param corr1: color correlation image for frame 1
    :param ids0: color objectids image for frame 0
    :param ids1: color objectids image for frame 1
    :param alpha: grayscale/binary alpha mask for frame 0
    :param max_flow: maximum distance to search for matches to correlation
    :param flow_guess: if set, will search around the flow guess in the next frame
    :return:
    flow estimate, nmatches, diffs

    where nmatches is an int array for number of best matches (in case of identical color)
    to estimate flow for that pixel, and diffs is a float array of the distance in color for the
    best match.
    """
    print('WARNING: flow_from_corr is a debug function; use at your own risk.')

    height = corr0.shape[0]
    width = corr0.shape[1]

    flows = np.zeros([height, width, 2], dtype=np.float32)
    nmatches = np.zeros(corr0.shape[0:2], dtype=np.int32)
    diffs = np.zeros(corr0.shape[0:2], dtype=np.float32)
    mask = np.zeros(corr0.shape[0:2], dtype=np.bool)
    id_mask = np.zeros(corr0.shape[0:2], dtype=np.bool)

    if flow_guess is None:
        flow_guess = np.zeros(flows.shape, dtype=np.float32)

    rows, cols = np.nonzero(alpha)
    flow = np.zeros([2], dtype=np.float32)
    for idx in range(len(rows)):
        row = rows[idx]
        col = cols[idx]
        color0 = corr0[row, col, :]
        id_mask[:, :] = False
        id_mask = (ids1[:, :, 0] == ids0[row, col, 0]) & \
                  (ids1[:, :, 1] == ids0[row, col, 1]) & \
                  (ids1[:, :, 2] == ids0[row, col, 2])

        best_diff = -1
        best_color = None
        positions = []
        for radius in range(0, max_flow):
            mask[:, :] = False
            set_perimeter_mask(mask, col + int(flow_guess[row, col, 0]),
                               row + int(flow_guess[row, col, 1]), radius)
            # Alternatively: col + flow[1], row + flow[0], radius)

            mask = (np.logical_and(mask, id_mask))
            pts_rows, pts_cols = np.nonzero(mask)
            # print('  > radius %d, candidates %d' % (radius, len(pts_rows)))
            got_better = False
            for pidx in range(len(pts_rows)):
                r = pts_rows[pidx]
                c = pts_cols[pidx]
                position = np.array([[r], [c]], dtype=np.int64)
                color1 = corr1[r, c, :]
                diff = np.linalg.norm(color0.astype(np.float32) - color1.astype(np.float32))
                if best_color is None:
                    best_diff = diff
                    best_color = color1
                    positions = [position]
                    got_better = True
                elif np.array_equal(best_color, color1):
                    positions.append(position)
                    got_better = True
                elif diff < best_diff:
                    # Note: this has to come after checking for color equality,
                    # as equal colors could compete due to float precision
                    best_diff = diff
                    best_color = color1
                    positions = [position]
                    got_better = True
            if not got_better and len(pts_rows) > 0:
                # print('Stopped expansion at radius %d' % radius)
                break

        diffs[row, col] = best_diff
        nmatches[row, col] = len(positions)
        # print('Positions (%d): %s' % (len(positions), str(positions)))
        # print('Best diff %0.3f; best color %s (vs. %s)' %
        #      (best_diff, str(best_color).replace('\n', ' '), str(color0).replace('\n', ' ')))
        if len(positions) == 1:
            best_pos = positions[0]
        elif len(positions) > 0:
            best_pos = np.sum(positions, axis=0).astype(np.float32) / len(positions)
        else:
            # print('Odd, nothing found')
            best_pos = np.array([[row], [col]], dtype=np.float32)
        flow = np.squeeze(best_pos - np.array([[row], [col]], dtype=np.float32))
        print('--------> Done %d/%d, pt (%d, %d), flow = [%0.2f, %0.2f] (vs. [%0.2f, %0.2f])' %
              (idx, len(rows), row, col, flow[1], flow[0], flow_guess[row, col, 0], flow_guess[row, col, 1]))
        try:
            flows[row, col, :] = np.array([flow[1], flow[0]])
        except Exception as e:
            print('Exception occurred: %s' % str(e))

    return flows, nmatches, diffs
