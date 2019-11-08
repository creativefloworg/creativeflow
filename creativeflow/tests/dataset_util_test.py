#!/usr/bin/env python

import unittest
import os
import re

import creativeflow.blender.dataset_util as dataset_util


def get_test_data_path(fname):
    test_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(test_dir, 'data', fname)

def get_matching(pattern, strings):
    return [x for x in strings if re.match(pattern, x) is not None]

class StylesTest(unittest.TestCase):

    def _test_all_matched(self, pattern, strings):
        matched = get_matching(pattern, strings)
        self.assertEqual(
            len(matched), len(strings),
            msg=('Unmatched: %s' % str(set(strings).difference(set(matched)))))

    def _test_none_matched(self, pattern, strings):
        matched = get_matching(pattern, strings)
        self.assertEqual(
            len(matched), 0,
            msg=('Erroneously matched: %s' % str(matched)))

    def test_shading_styles(self):
        self.assertEqual(17, len(set(dataset_util.ShadingStyles.TRAIN_STYLIT_STYLES)))
        self.assertEqual(8, len(set(dataset_util.ShadingStyles.TEST_STYLIT_STYLES)))
        self.assertEqual(9, len(set(dataset_util.ShadingStyles.TRAIN_BLENDER_STYLES)))
        self.assertEqual(5, len(set(dataset_util.ShadingStyles.TEST_BLENDER_STYLES)))

        self._test_all_matched(
            dataset_util.ShadingStyles.blender_styles_regex(),
            dataset_util.ShadingStyles.TEST_BLENDER_STYLES +
            dataset_util.ShadingStyles.TRAIN_BLENDER_STYLES)
        self._test_all_matched(
            dataset_util.ShadingStyles.stylit_styles_regex(),
            dataset_util.ShadingStyles.TEST_STYLIT_STYLES +
            dataset_util.ShadingStyles.TRAIN_STYLIT_STYLES)
        self._test_none_matched(
            dataset_util.ShadingStyles.stylit_styles_regex(),
            dataset_util.ShadingStyles.TEST_BLENDER_STYLES +
            dataset_util.ShadingStyles.TRAIN_BLENDER_STYLES)
        self._test_none_matched(
            dataset_util.ShadingStyles.blender_styles_regex(),
            dataset_util.ShadingStyles.TEST_STYLIT_STYLES +
            dataset_util.ShadingStyles.TRAIN_STYLIT_STYLES)

        paintlike = get_matching(dataset_util.ShadingStyles.stylit_paintlike_styles_regex(),
                                 dataset_util.ShadingStyles.TRAIN_STYLIT_STYLES)
        drymedia = get_matching(dataset_util.ShadingStyles.stylit_drymedia_styles_regex(),
                                dataset_util.ShadingStyles.TRAIN_STYLIT_STYLES)
        other = get_matching(dataset_util.ShadingStyles.stylit_other_styles_regex(),
                             dataset_util.ShadingStyles.TRAIN_STYLIT_STYLES)
        matched = set(paintlike + drymedia + other)
        self.assertEqual(
            len(matched), len(dataset_util.ShadingStyles.TRAIN_STYLIT_STYLES),
            'Unmatched styles: %s' %
            str(set(dataset_util.ShadingStyles.TRAIN_STYLIT_STYLES).difference(matched)))
        self.assertEqual(
            len(paintlike) + len(drymedia) + len(other),
            len(matched),
            msg='Some styles matched several classifying patterns.')

    def test_line_styles(self):
        self.assertEqual(23, len(set(dataset_util.LineStyles.TRAIN_STYLES)))
        self.assertEqual(17, len(set(dataset_util.LineStyles.TEST_STYLES)))


class SequenceInfoTest(unittest.TestCase):
    def test_basics(self):
        seq = dataset_util.SequenceInfo('ZombieScene', 'mixamo', 5, 0,
                                        shading_styles=['ink0', 'paint1'],
                                        line_styles=['pencil0', 'pen5'],
                                        has_flow=True)
        self.assertEqual(10, seq.nframes_in_all_styles())

        style_idx, frame_idx = seq.get_style_frame_indices(3)
        self.assertEqual(style_idx, 0)
        self.assertEqual(frame_idx, 3)
        style_idx, frame_idx = seq.get_style_frame_indices(4)
        self.assertEqual(style_idx, 0)
        self.assertEqual(frame_idx, 4)
        style_idx, frame_idx = seq.get_style_frame_indices(7)
        self.assertEqual(style_idx, 1)
        self.assertEqual(frame_idx, 2)

        # Now, skip the last frame which has no flow
        seq = dataset_util.SequenceInfo('ZombieScene', 'mixamo', 5, 0,
                                        shading_styles=['ink0', 'paint1'],
                                        line_styles=['pencil0', 'pen5'],
                                        has_flow=True,
                                        excluded_frames=[-1])
        self.assertEqual(8, seq.nframes_in_all_styles())
        style_idx, frame_idx = seq.get_style_frame_indices(4)
        self.assertEqual(style_idx, 1)
        self.assertEqual(frame_idx, 0)
        style_idx, frame_idx = seq.get_style_frame_indices(7)
        self.assertEqual(style_idx, 1)
        self.assertEqual(frame_idx, 3)

    def test_path_basics(self):
        seq = dataset_util.SequenceInfo('ZombieScene', 'mixamo', 5, 0,
                                        shading_styles=['ink0', 'paint1'],
                                        line_styles=['pencil0', 'pen5'],
                                        has_flow=True)
        for data_type in list(dataset_util.DataType):
            if data_type in dataset_util.PathsHelper.META_FRAMES:
                seq_path = seq.get_meta_path(data_type, frame_idx=5)
            elif data_type in dataset_util.PathsHelper.META_INFO:
                seq_path = seq.get_meta_path(data_type)
            elif data_type in dataset_util.PathsHelper.RENDER_FRAMES:
                seq_path = seq.get_render_path(data_type, style_idx=1, frame_idx=3)
            elif data_type in dataset_util.PathsHelper.RENDER_INFO:
                seq_path = seq.get_render_path(data_type, style_idx=1)
            else:
                self.assertTrue(False, msg='Data type not covered: %s' % str(data_type))
            self.assertGreater(len(seq_path), 0,
                               msg='Got empty path for data type %s' % str(data_type))

    def test_exclude_include_frames(self):
        seq = dataset_util.SequenceInfo('ZombieScene', 'mixamo', 7, 0,
                                        shading_styles=['ink0', 'paint1'],
                                        line_styles=['pencil0', 'pen5'],
                                        has_flow=True,
                                        excluded_frames=[-1],
                                        included_frames=[0,2,3])
        self.assertEqual(6, seq.nframes_in_all_styles())
        style_idx, frame_idx = seq.get_style_frame_indices(5)
        self.assertEqual(style_idx, 1)
        self.assertEqual(frame_idx, 3)

        with self.assertRaises(RuntimeError):
            style_idx, frame_idx = seq.get_style_frame_indices(6)


class DatasetHelperTest(unittest.TestCase):

    def get_all_paths_by_frame(self, helper, data_type, is_meta):
        out = []
        for global_frame in range(helper.num_frames_in_all_styles()):
            seq, style_idx, frame_idx = helper.get_sequence_info(global_frame)
            # print('%d - Seq %s, style %d, frame %d' % (global_frame, str(seq), style_idx, frame_idx))
            if is_meta:
                res = seq.get_meta_path(data_type, frame_idx)
            else:
                res = seq.get_render_path(data_type, style_idx, frame_idx)
            out.append(res)
        return out

    def get_all_paths_by_sequence(self, helper, data_type, is_meta):
        out = []
        for seq_id in range(helper.num_sequences()):
            seq = helper.sequences[seq_id]
            for f in range(seq.nframes_in_all_styles()):  # client responsible for ignoring last frame if flow required
                style_idx, frame_idx = seq.get_style_frame_indices(f)
                if is_meta:
                    res = seq.get_meta_path(data_type, frame_idx)
                else:
                    res = seq.get_render_path(data_type, style_idx, frame_idx)
                out.append(res)
        return out

    def get_all_paths_by_sequence_and_style(self, helper, data_type, is_meta):
        out = []
        for seq_id in range(helper.num_sequences()):
            seq = helper.sequences[seq_id]
            for style_idx in range(seq.nstyles()):
                for frame_idx in range(seq.nframes):  # client responsible for ignoring last frame if flow required
                    if is_meta:
                        res = seq.get_meta_path(data_type, frame_idx)
                    else:
                        res = seq.get_render_path(data_type, style_idx, frame_idx)
                    out.append(res)
        return out

    def test_basic_parsing(self):
        seq_file = get_test_data_path('mock_sequence_list.txt')
        helper = dataset_util.DatasetHelper(seq_file, require_flow=True)
        # these are mock sequences; no files present
        self.assertFalse(helper.check_files('', [dataset_util.DataType.FLOW, dataset_util.DataType.RENDER_COMPOSITE]))
        self.assertEqual(5, helper.num_sequences())
        self.assertEqual(4, helper.num_scenes())
        expected_frame_num = 29 * 3 + 14 * 2 + 19 * 2 + 9 * 2 + 9 * 2  # in all styles
        expected_unique_frame_num = 29 + 14 + 19 + 9 + 9
        self.assertEqual(expected_frame_num, helper.num_frames_in_all_styles())
        seq, style_idx, frame_idx = helper.get_sequence_info(10)
        self.assertEqual('Rockin\'Zombie', seq.scene_name)
        self.assertEqual(0, style_idx)
        self.assertEqual(10, frame_idx)
        seq, style_idx, frame_idx = helper.get_sequence_info(65)
        self.assertEqual('Rockin\'Zombie', seq.scene_name)
        self.assertEqual(2, style_idx)
        self.assertEqual(7, frame_idx)
        seq, style_idx, frame_idx = helper.get_sequence_info(87)
        self.assertEqual('moonrocket', seq.scene_name)
        self.assertEqual(0, style_idx)
        self.assertEqual(0, frame_idx)

        all_paths = self.get_all_paths_by_frame(helper, dataset_util.DataType.FLOW, is_meta=True)
        self.assertEqual(len(all_paths), expected_frame_num)
        self.assertEqual(len(set(all_paths)), expected_unique_frame_num)
        all_paths = self.get_all_paths_by_frame(helper, dataset_util.DataType.RENDER_COMPOSITE, is_meta=False)
        self.assertEqual(len(all_paths), expected_frame_num)
        self.assertEqual(len(set(all_paths)), expected_frame_num)

        # No flow required ----------------------------------------------------
        helper = dataset_util.DatasetHelper(seq_file, require_flow=False)
        self.assertEqual(6, helper.num_sequences())
        self.assertEqual(5, helper.num_scenes())
        expected_frame_num = 30 * 3 + 20 * 2 + 15 * 2 + 20 * 2 + 10 * 2 + 10 * 2
        expected_unique_frame_num = 30 + 20 + 15 + 20 + 10 + 10
        self.assertEqual(expected_frame_num, helper.num_frames_in_all_styles())

        all_paths = self.get_all_paths_by_frame(helper, dataset_util.DataType.FLOW, is_meta=True)
        self.assertEqual(len(all_paths), expected_frame_num)
        self.assertEqual(len(set(all_paths)), expected_unique_frame_num)
        all_paths = self.get_all_paths_by_frame(
            helper, dataset_util.DataType.RENDER_COMPOSITE, is_meta=False)
        self.assertEqual(len(all_paths), expected_frame_num)
        self.assertEqual(len(set(all_paths)), expected_frame_num)
        # Try different ways to iterate
        all_paths1 = self.get_all_paths_by_sequence(
            helper, dataset_util.DataType.RENDER_COMPOSITE, is_meta=False)
        all_paths2 = self.get_all_paths_by_sequence_and_style(
            helper, dataset_util.DataType.RENDER_COMPOSITE, is_meta=False)
        self.assertEqual(set(all_paths), set(all_paths1))
        self.assertEqual(set(all_paths), set(all_paths2))

    def test_style_filtering(self):
        seq_file = get_test_data_path('mock_sequence_list.txt')
        helper = dataset_util.DatasetHelper(
            seq_file, require_flow=True,
            regex_sources='shapenet|web|mixamo',
            regex_shading_styles=dataset_util.ShadingStyles.stylit_drymedia_styles_regex())
        # Rockin'Zombie | charcoal1_bw | pen0
        # moonrocket | pastels1 | marker1
        # TorontoCatBus | cam 1 | cpencil3 | chalk6
        self.assertEqual(3, helper.num_sequences())
        self.assertEqual(3, helper.num_scenes())

        seq = helper.sequences[0]
        self.assertEqual('Rockin\'Zombie', seq.scene_name)
        self.assertEqual(1, seq.nstyles())
        self.assertEqual('charcoal1_bw', seq.shading_styles[0])
        self.assertEqual('pen0', seq.line_styles[0])
        seq = helper.sequences[1]
        self.assertEqual('moonrocket', seq.scene_name)
        self.assertEqual(1, seq.nstyles())
        self.assertEqual('pastels1', seq.shading_styles[0])
        self.assertEqual('marker1', seq.line_styles[0])
        seq = helper.sequences[2]
        self.assertEqual('TotoroCatBus', seq.scene_name)

        expected_frame_num = 30 + 15 + 10 - 3  # ignore last frames due to flow
        self.assertEqual(expected_frame_num, helper.num_frames_in_all_styles())

        # Now even more selective
        helper = dataset_util.DatasetHelper(
            seq_file, require_flow=False,
            regex_sources='shapenet|web|mixamo',
            regex_shading_styles=dataset_util.ShadingStyles.stylit_drymedia_styles_regex(),
            regex_line_styles='marker|chalk')
        self.assertEqual(2, helper.num_sequences())
        self.assertEqual(2, helper.num_scenes())
        seq = helper.sequences[0]
        self.assertEqual('moonrocket', seq.scene_name)
        self.assertEqual(1, seq.nstyles())
        self.assertEqual('pastels1', seq.shading_styles[0])
        self.assertEqual('marker1', seq.line_styles[0])
        expected_frame_num = 15 + 10
        self.assertEqual(expected_frame_num, helper.num_frames_in_all_styles())

    def test_frame_filtering(self):
        # Ground truth flow paths
        gt_file = get_test_data_path(os.path.join('ground_truth', 'mock_flow_paths2.txt'))
        with open(gt_file) as f:
            expected_flow_paths = set([line.strip() for line in f])
        gt_file = get_test_data_path(os.path.join('ground_truth', 'mock_composite_paths2.txt'))
        with open(gt_file) as f:
            expected_composite_paths = set([line.strip() for line in f])

        # Read in paths using our utility
        seq_file = get_test_data_path('mock_sequence_list2.txt')
        helper = dataset_util.DatasetHelper(seq_file, require_flow=True)
        actual_paths = set(self.get_all_paths_by_frame(helper, dataset_util.DataType.RENDER_COMPOSITE, False))
        self.assertEqual(expected_composite_paths, actual_paths)

        actual_paths = set(self.get_all_paths_by_frame(helper, dataset_util.DataType.FLOW, True))
        self.assertEqual(expected_flow_paths, actual_paths)

