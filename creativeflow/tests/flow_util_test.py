import unittest

import numpy as np
import os
from skimage.io import imread, imsave

import blender.flow_util as flow_util
import blender.io_util as io_util


class FlowUtilTest(unittest.TestCase):

    def datapath(self, fname):
        test_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(test_dir, 'data', 'flow_util', fname)

    def test_get_val_interpolated(self):
        ff = np.concatenate(
            [np.expand_dims(np.array([[ 1.0,  5.0,  3.0,  7.0],
                                      [ 4.0,  2.0, -1.0, -1.0],
                                      [-2.0,  3.0,  5.0,  8.0]], dtype=np.float32), axis=2),
             np.expand_dims(np.array([[-1.0, -2.0, -3.0,  4.0],
                                      [ 0.0,  3.0, -5.0, -1.0],
                                      [ 1.0,  1.0,  1.0,  1.0]], dtype=np.float32), axis=2)],
            axis=2)

        rows = []
        cols = []

        # Test expected case
        rows.append(0.3)
        cols.append(2.6)
        actual = flow_util.get_val_interpolated(ff, 0.3, 2.6)
        expected0 = ((ff[0][2] * 0.4 + ff[0][3] * 0.6) * 0.7 +
                     (ff[1][2] * 0.4 + ff[1][3] * 0.6) * 0.3)
        np.testing.assert_array_almost_equal(expected0, actual)

        rows.append(1.8)
        cols.append(2.7)
        actual = flow_util.get_val_interpolated(ff, 1.8, 2.7)
        expected1 = ((ff[1][2] * 0.3 + ff[1][3] * 0.7) * 0.2 +
                     (ff[2][2] * 0.3 + ff[2][3] * 0.7) * 0.8)
        np.testing.assert_array_almost_equal(expected1, actual)

        rows.append(0.8)
        cols.append(0.7)
        actual = flow_util.get_val_interpolated(ff, 0.8, 0.7)
        expected2 = ((ff[0][0] * 0.3 + ff[0][1] * 0.7) * 0.2 +
                     (ff[1][0] * 0.3 + ff[1][1] * 0.7) * 0.8)
        np.testing.assert_array_almost_equal(expected2, actual)

        # Test out of bounds
        with self.assertRaises(IndexError):
            flow_util.get_val_interpolated(ff, -1.0, 0.0)

        with self.assertRaises(IndexError):
            flow_util.get_val_interpolated(ff, 1.0, -2.0)

        with self.assertRaises(IndexError):
            flow_util.get_val_interpolated(ff, 3.0, 0.0)

        with self.assertRaises(IndexError):
            flow_util.get_val_interpolated(ff, 1.5, 4.3)

        # Test vectorized version (short test)
        expected = np.concatenate([np.expand_dims(expected0, axis=0),
                                   np.expand_dims(expected1, axis=0),
                                   np.expand_dims(expected2, axis=0)], axis=0)
        actual_val, actual_invalid = flow_util.get_val_interpolated_vec(ff, rows, cols)
        np.testing.assert_array_almost_equal(expected, actual_val)

        # Now we reshape input rows, cols
        rows = np.array([[rows[0], rows[1]], [rows[2], -1]])
        cols = np.array([[cols[0], cols[1]], [cols[2], 0]])
        expected = np.zeros([2,2,2])
        expected[0,0,:] = expected0
        expected[0,1,:] = expected1
        expected[1,0,:] = expected2
        expected_invalid = np.array([[0,0],[0,1]], dtype=np.int32)
        actual_val, actual_invalid = flow_util.get_val_interpolated_vec(ff, rows, cols,
                                                                        fill_val=0.0)
        np.testing.assert_array_almost_equal(expected, actual_val)
        np.testing.assert_array_almost_equal(expected_invalid, actual_invalid)

    def test_get_occlusions(self):
        # Frame 0:       Frame 1:
        # * * * *        * * B B
        # B B * *        * * B B
        # B B * *        * * * *
        # * * * *        * * * *
        ff0 = np.concatenate(
            [np.expand_dims(np.array([[0, 0, 0, 0],
                                      [2.0, 2.0, 0, 0],
                                      [2.0, 2.0, 0, 0],
                                      [0, 0, 0, 0]], dtype=np.float32), axis=2),
             np.expand_dims(np.array([[0, 0, 0, 0],
                                      [-1.0, -1.0, 0, 0],
                                      [-1.0, -1.0, 0, 0],
                                      [0, 0, 0, 0]], dtype=np.float32), axis=2)],
            axis=2)
        bf1 = np.concatenate(
            [np.expand_dims(np.array([[0, 0, -2, -2],
                                      [0, 0, -2, -2],
                                      [0, 0, 0, 0],
                                      [0, 0, 0, 0]], dtype=np.float32), axis=2),
             np.expand_dims(np.array([[0, 0, 1, 1],
                                      [0, 0, 1, 1],
                                      [0, 0, 0, 0],
                                      [0, 0, 0, 0]], dtype=np.float32), axis=2)],
            axis=2)
        # Pixels in Frame0, not visible in Frame1
        occ_expected = np.array(
            [[0, 0, 255, 255],
              [0, 0, 255, 255],
              [0, 0, 0, 0],
              [0, 0, 0, 0]], dtype=np.uint8)
        occ_actual = flow_util.get_occlusions(ff0, bf1)
        np.testing.assert_array_equal(occ_expected, occ_actual)

        # Test vectorized version
        occ_actual = flow_util.get_occlusions_vec(ff0, bf1)
        np.testing.assert_array_equal(occ_expected, occ_actual)

    def get_unique_colors(self, img):
        return np.unique(img.reshape(-1, img.shape[2]), axis=0)

    def get_unequal_mask(self, img0, img1, threshold):
        diff = np.linalg.norm(img0 - img1, axis=2)
        return diff > threshold

    def get_mean_flow(self, flow):
        norm = np.linalg.norm(flow, axis=2)
        count = np.sum(norm > 0.0001)
        sum = np.sum(flow.reshape((-1, 2)), axis=0)
        if count == 0:
            return sum, count
        else:
            return sum / count, count

    def check_flows_close(self, f_expected, f_resampled, msg='', verbose=False):
        self.assertEqual(f_expected.shape, f_resampled.shape,
                         msg='(%s) Expected shape %s, but got resampled shape %s' %
                             (msg, str(f_expected.shape), str(f_resampled.shape)))

        mean_expected, nonzero_expected = self.get_mean_flow(f_expected)
        mean_resampled, nonzero_resampled = self.get_mean_flow(f_resampled)
        norm = np.linalg.norm(mean_expected)
        diff = np.linalg.norm(mean_expected - mean_resampled)
        info_msg = ('(%s) Expected mean %s, got resampled mean %s (%0.1f%% difference)' %
                    (msg, str(mean_expected), str(mean_resampled), diff / norm * 100))
        if verbose:
            print(info_msg)
        self.assertTrue(np.allclose(mean_expected, mean_resampled, rtol=0.05), msg=info_msg)
        diff = abs(nonzero_resampled - nonzero_expected) * 100 / nonzero_expected
        info_msg = ('(%s) Expected %d nonzero flow pixels, got %d (%0.1f%% difference)' %
                    (msg, nonzero_expected, nonzero_resampled, diff))
        if verbose:
            print(info_msg)
        self.assertGreater(nonzero_expected, 100)  # Test data sanity
        self.assertLess(abs(nonzero_expected - nonzero_resampled), nonzero_expected * 0.05, msg=info_msg)

        meanval = sum(np.abs(mean_expected)) / 2.0
        thresh = meanval * 0.03
        disagreed = self.get_unequal_mask(f_expected, f_resampled, threshold=thresh)
        # imsave('/tmp/mask.png', disagreed.astype(np.uint8) * 255)
        num_disagree = np.sum(disagreed)
        max_disagreement_frac = 0.05
        max_disagreement = nonzero_expected * max_disagreement_frac
        diff = num_disagree * 100 / nonzero_expected
        info_msg = ('(%s) Expected <%0.f%% of %d pixels to disagree by over %0.2f, and %d pixels disagree (%0.1f%%)' %
                    (msg, max_disagreement_frac * 100, nonzero_expected, thresh, num_disagree, diff))
        if verbose:
            print(info_msg)
        self.assertLess(num_disagree, max_disagreement, msg=info_msg)

    def check_resampled_objectids(self, ids_expected, ids_resampled, msg=''):
        expected_colors = self.get_unique_colors(ids_expected)
        resampled_colors = self.get_unique_colors(ids_resampled)
        self.assertEqual(expected_colors.shape, resampled_colors.shape,
                         msg='(%s) expected unique colors of shape %s, but got %s' %
                             (msg, str(expected_colors.shape), str(resampled_colors.shape)))
        unequal_pixels = np.sum(self.get_unequal_mask(ids_expected, ids_resampled, threshold=0.1))
        max_disagreement = ids_expected.shape[0] * ids_expected.shape[1] * 0.05
        self.assertLess(unequal_pixels, max_disagreement,
                        '(%s) Expected less than %0.1f pixels to differ, but %d pixels disagree' %
                        (msg, max_disagreement, unequal_pixels))

    def test_resample(self):
        testcases = [ 'bunny_teapot_frame2', 'bunny_teapot_frame7', 'character_frame1', 'character_frame5']
        for prefix in testcases:
            flow750_path = self.datapath('%s_flow750.flo' % prefix)
            flow750 = io_util.read_flow(flow750_path)
            flow500 = io_util.read_flow(self.datapath('%s_flow500.flo' % prefix))
            ids750_path = self.datapath('%s_ids750.png' % prefix)
            ids750 = imread(ids750_path)
            ids500 = imread(self.datapath('%s_ids500.png' % prefix))

            # Check flow re-sampling down
            flow500_resampled = flow_util.resample_flow(flow750, (500, 500))
            io_util.write_flow(flow500_resampled, '/tmp/resampled.flo')
            self.check_flows_close(flow500, flow500_resampled, msg=flow750_path)

            # TODO: Check flow re-sampling up

            # Check ids re-sampling down
            ids500_resampled = flow_util.resample_objectids(ids750, (500, 500))
            self.check_resampled_objectids(ids500, ids500_resampled, msg=ids750_path)

            # Check ids re-sampling up
            ids750_resampled = flow_util.resample_objectids(ids500, (750, 750))
            self.check_resampled_objectids(ids750, ids750_resampled, msg=ids750_path)


if __name__ == '__main__':
    unittest.main()
