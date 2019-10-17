"""
This module is not used for the dataset creation. Code here is written specifically for the way Creative Flow+ Dataset
is packaged and distributed to make tasks like selecting and reading training data easier.
"""
import bisect
import logging
import os
import pandas
import re
from enum import Enum

logger = logging.getLogger(__name__)


class DataType(Enum):
    FLOW = 1
    BACKFLOW = 2
    OCCLUSIONS = 3
    CORRESPONDENCES = 4
    OBJECTIDS = 5
    OBJECTIDS_KEY = 6
    ALPHA = 7
    DEPTHIMG = 8
    DEPTHIMG_RANGE = 9
    DEPTH = 10
    NORMALS = 11
    RENDER_ORIGINAL = 12
    RENDER_COMPOSITE = 13
    RENDER_COMPOSITE_LICENSE = 14
    RENDER_SHADING = 15
    RENDER_LINE = 16
    RENDER_LINE_ALPHA = 17


class DatasetHelper(object):
    """
    Using Creative Flow+ Dataset conventions, converts a condensed sequences file
    into actual file paths, allowing filtering by style and data source.
    The actual presence of these file paths depends on the packages you have
    downloaded and decompressed using datagen/pipeline_decompress.sh

    Accepts input file of the format:
    scene_name|scene_source|nframes|cam_idx|nstyles|has_flow|shading_styles|line_styles
    <scene_name>|<scene_source>|<nframes>|<cam_idx>|<nstyles>|<has_flow>|<shading_style0>,<shading_style1>|<line_style0>,<line_style1>

    Example usage:
    helper = DatasetHelper('train_sequences.txt',
                           select_sournces={"mixamo", "web"},
                           select_shading_styles=ShadingStyles.stylit_paintlike_styles_regex())
    helper.check_files(decompressed_data_path,
                       [DataType.FLOW, DataType.RENDER_COMPOSITE, DataType.RENDER_ORIGINAL],
                       print_all_errors=False)

    # Note that each scene has num_scene_frames * ncams * nstyles actual frames.
    # Global frames refer to these frames.
    # Alternatively, can also iterate by scene (which may have more than one camera angle)
    # or by sequence (which may have more than one style)
    for global_frame in range(helper.num_frames_in_all_styles()):
       seq, style_idx, frame_idx = helper.get_sequence_info(global_frame)
       flow_path = seq.get_meta_path(DataType.FLOW, frame_idx,
                                     base_dir=decompressed_data_path)
       composite_path = seq.get_render_path(DataType.RENDER_COMPOSITE, style_idx, frame_idx,
                                            base_dir=decompressed_data_path)
       flow = io_util.read_flow_file(flow_path)
    """

    __OK_TAGS = {'YES', 'OK'}

    def __init__(self, sequences_file,
                 require_flow=True,
                 regex_sources='.*',
                 regex_shading_styles='.*',
                 regex_line_styles='.*'):
        self.global_frame_numbers = []
        self.sequences = []
        self.scene_names = set()
        self.require_flow = require_flow

        data_frame = pandas.read_csv(sequences_file, sep='|')
        for i in data_frame.index:
            row = data_frame.iloc[i]
            seq = DatasetHelper.sequence_from_row(row, i, regex_shading_styles, regex_line_styles)
            if len(seq.shading_styles) == 0:
                logger.debug(
                    'Skipping sequence (one of the shading,outline styles matched regexp %s %s): %s' %
                    (row['shading_styles'], row['line_styles'], str(seq)))
                continue

            if require_flow and not seq.has_flow:
                logger.debug('Skipping sequence (no flow): %s' % str(seq))
                continue

            if not re.match(regex_sources, seq.source):
                logger.debug('Skipping sequence (source did not match regexp %s): %s' % (seq.source, str(seq)))
                continue
            self._add_sequence(seq)

    @staticmethod
    def sequence_from_row(row, row_idx, regex_shading_styles, regex_line_styles):
        shading_styles = row['shading_styles'].split(',')
        line_styles = row['line_styles'].split(',')

        nstyles = int(row['nstyles'])
        if nstyles != len(shading_styles) or nstyles != len(line_styles):
            raise RuntimeError('Error parsing line %d: inconsistent style counts\n"%s"' % (row_idx, str(row)))

        matching_indices = [i for i in range(nstyles) if
                            (re.match(regex_shading_styles, shading_styles[i]) is not None and
                             re.match(regex_line_styles, line_styles[i]) is not None)]
        shading_styles_matching = [shading_styles[i] for i in matching_indices]
        line_styles_matching = [line_styles[i] for i in matching_indices]

        return SequenceInfo(
            row['scene_name'],
            source=row['scene_source'],
            nframes=int(row['nframes']),
            cam_idx=int(row['cam_idx']),
            shading_styles=shading_styles_matching,
            line_styles=line_styles_matching,
            has_flow=(row['has_flow'] in DatasetHelper.__OK_TAGS))

    def _add_sequence(self, seq):
        prev_frames = self.num_frames_in_all_styles()
        self.global_frame_numbers.append(
            prev_frames + seq.nframes_in_all_styles(ignore_final_frame_with_no_flow=self.require_flow))
        self.sequences.append(seq)
        self.scene_names.add(seq.scene_name)

    def check_files(self, base_dir, data_types, fast_fail=False):
        sequences_missing_files = 0
        for sidx in range(self.num_sequences()):
            seq = self.sequences[sidx]
            nframes = seq.nframes - (1 if self.require_flow else 0)
            seq_ok = True
            for data_type in data_types:
                file_names = []
                if data_type in PathsHelper.META_INFO:
                    file_names.append(seq.get_meta_path(data_type, base_dir=base_dir))
                elif data_type in PathsHelper.META_FRAMES:
                    for frame_idx in range(nframes):
                        file_names.append(seq.get_meta_path(data_type, frame_idx, base_dir=base_dir))
                elif data_type in PathsHelper.RENDER_INFO:
                    for style_idx in range(seq.nstyles()):
                        file_names.append(seq.get_render_path(data_type, style_idx, base_dir=base_dir))
                elif data_type in PathsHelper.RENDER_FRAMES:
                    for style_idx in range(seq.nstyles()):
                        for frame_idx in range(nframes):
                            file_names.append(seq.get_render_path(data_type, style_idx, frame_idx, base_dir=base_dir))
                missing_files = []
                for f in file_names:
                    if not os.path.exists(f):
                        if fast_fail:
                            raise RuntimeError('FAIL FAST -- Missing file: %s' % f)
                        missing_files.append(f)
                if len(missing_files) > 0:
                    logger.warning('Seq %s missing %d out of %d files for data type %s' %
                                   (str(seq), len(missing_files), len(file_names), str(data_type)))
                    logger.debug('\n'.join([('Missing: %s' % x) for x in missing_files]))
                    seq_ok = False
            if not seq_ok:
                sequences_missing_files += 1

        data_type_str = ', '.join([str(d) for d in data_types])
        if sequences_missing_files > 0:
            logger.warning('FAIL: Sequences missing files for data types %s: %d out of %d' %
                           (data_type_str, sequences_missing_files, self.num_sequences()))
            return False
        else:
            logger.info('SUCCESS: All %d sequences complete for data types %s' % (self.num_sequences(), data_type_str))
            return True

    def num_frames_in_all_styles(self):
        if len(self.global_frame_numbers) == 0:
            return 0
        return self.global_frame_numbers[-1]

    def get_sequence_info(self, global_frame):
        """
        Returns sequence, style index and frame index within that sequence corresponding to
        the provided global frame number in the entire data collection (subject to filtering).

        :param global_frame:
        :return:
        """
        if global_frame >= self.num_frames_in_all_styles():
            raise RuntimeError('Global frame requested %d is greater than number of frames %d' %
                               (global_frame, self.num_frames_in_all_styles()))
        i = bisect.bisect_left(self.global_frame_numbers, global_frame + 1)
        frame_start = 0
        if i > 0:
            frame_start = self.global_frame_numbers[i - 1]
        seq = self.sequences[i]
        style_idx, frame_idx = seq.get_style_frame_indices(global_frame - frame_start,
                                                           ignore_final_frame_with_no_flow=self.require_flow)
        return seq, style_idx, frame_idx

    def num_scenes(self):
        """
        Scene is a 3D action scene that can be shot from multiple angles.
        :return: number of scenes
        """
        return len(self.scene_names)

    def num_sequences(self):
        """
        Sequence is a scene shot from a specific angle.
        :return: number of sequences
        """
        return len(self.sequences)


class PathsHelper(object):
    """
    Helps map data types to path locations in the decompressed Creative Flow+ Dataset.
    """
    META_FRAMES = {
        DataType.FLOW: ('flow', 'flow%06d.flo', ),
        DataType.BACKFLOW: ('backflow', 'backflow%06d.flo'),
        DataType.OCCLUSIONS: ('occlusions', 'occlusions%06d.png'),
        DataType.CORRESPONDENCES: ('corresp', 'corr%06d.png'),
        DataType.OBJECTIDS: ('objectid', 'objectid%06d.png'),
        DataType.ALPHA: ('alpha', 'alpha%06d.png'),
        DataType.DEPTHIMG: ('depthimg', 'depth%06d.png'),
        DataType.DEPTH: ('depth', 'depth%06d.array'),
        DataType.NORMALS: ('normals', 'normal%06d.png'),
        DataType.RENDER_ORIGINAL: ('original_render', 'frame%06d.png')
    }
    META_INFO = {
        DataType.OBJECTIDS_KEY: ('objectid', 'KEYS.txt'),
        DataType.DEPTHIMG_RANGE: ('depthimg', 'depth.range.txt')
    }
    RENDER_FRAMES = {
        DataType.RENDER_COMPOSITE: ('composite', 'style.%s', 'frame%06d.png'),
        DataType.RENDER_SHADING: ('shading', 'shading%d.%s', 'frame%06d.png'),
        DataType.RENDER_LINE: ('lines', 'line%d.%s', 'frame%06d.png'),
        DataType.RENDER_LINE_ALPHA: ('lines', 'line%d.%s.alpha', 'frame%06d.png')
    }
    RENDER_INFO = {
        DataType.RENDER_COMPOSITE_LICENSE: ('composite', 'style.%s', 'LICENSE.txt')
        }

    @staticmethod
    def sequence_dir(base_dir, sequence_name, cam_idx):
        return os.path.join(base_dir, sequence_name, 'cam%d' % cam_idx)

    @staticmethod
    def __check_datatype_in(data_type, data_types_dict):
        if data_type not in data_types_dict:
            raise RuntimeError(
                'Wrong data type %s, expected %s' %
                (str(data_type), ','.join([str(x) for x in data_types_dict.keys()])))

    @staticmethod
    def meta_frame_path(data_type, base_dir, sequence_name, cam_idx, frame_idx):
        PathsHelper.__check_datatype_in(data_type, PathsHelper.META_FRAMES)
        seq_dir = PathsHelper.sequence_dir(base_dir=base_dir,
                                           sequence_name=sequence_name,
                                           cam_idx=cam_idx)
        names = PathsHelper.META_FRAMES[data_type]
        return os.path.join(seq_dir, 'metadata', names[0], names[1] % (frame_idx + 1))

    @staticmethod
    def meta_info_path(data_type, base_dir, sequence_name, cam_idx):
        PathsHelper.__check_datatype_in(data_type, PathsHelper.META_INFO)
        seq_dir = PathsHelper.sequence_dir(base_dir=base_dir,
                                           sequence_name=sequence_name,
                                           cam_idx=cam_idx)
        names = PathsHelper.META_INFO[data_type]
        return os.path.join(seq_dir, 'metadata', names[0], names[1])

    @staticmethod
    def render_frame_path(data_type, base_dir, sequence_name, cam_idx, frame_idx, style_idx, style_name):
        PathsHelper.__check_datatype_in(data_type, PathsHelper.RENDER_FRAMES)
        seq_dir = PathsHelper.sequence_dir(base_dir=base_dir,
                                           sequence_name=sequence_name,
                                           cam_idx=cam_idx)
        names = PathsHelper.RENDER_FRAMES[data_type]

        if data_type == DataType.RENDER_COMPOSITE:
            style_dir = names[1] % style_name
        else:
            style_dir = names[1] % (style_idx, style_name)
        return os.path.join(seq_dir, 'renders', names[0], style_dir, names[2] % (frame_idx + 1))

    @staticmethod
    def render_info_path(data_type, base_dir, sequence_name, cam_idx, style_idx, style_name):
        PathsHelper.__check_datatype_in(data_type, PathsHelper.RENDER_INFO)
        seq_dir = PathsHelper.sequence_dir(base_dir=base_dir,
                                           sequence_name=sequence_name,
                                           cam_idx=cam_idx)
        names = PathsHelper.RENDER_INFO[data_type]
        return os.path.join(seq_dir, 'renders', names[0], names[1] % style_name, names[2])


class ShadingStyles(object):
    """
    Helps select subsets of shading styles from the Creative Flow+ Dataset.
    """
    TRAIN_STYLIT_STYLES = [
        'charcoal1_bw',
        'cpencil2',
        'cpencil3',
        'exp0',
        'ink0_bw',
        'ink2',
        'paint0',
        'paint1',
        'paint2',
        'pastels0',
        'pastels1',
        'pastels2_mono',
        'pencil1',
        'pencil2_bw',
        'watercolor0',
        'watercolor2',
        'watercolor3'
    ]
    TEST_STYLIT_STYLES = [
        'charcoal2_bw',
        'cpencil0',
        'cpencil1',
        'ink1_mono',
        'marker0',
        'paint3',
        'pencil0_bw',
        'watercolor1'
    ]
    TRAIN_BLENDER_STYLES = [
        'flat',
        'textured0',
        'textured2',
        'textured3',
        'textured4',
        'toon1',
        'toon2',
        'toon3',
        'toon4'
    ]
    TEST_BLENDER_STYLES = [
        'flat',
        'textured1',
        'textured5',
        'toon0',
        'toon5'
    ]

    @staticmethod
    def blender_styles_regex():
        return '^(flat|toon|textured)'

    @staticmethod
    def stylit_styles_regex():
        return '^(charcoal|cpencil|pencil|exp|ink|marker|paint|pastels|watercolor)'

    @staticmethod
    def stylit_blackandwhite_styles_regex():
        return '(.*)_bw'

    @staticmethod
    def stylit_paintlike_styles_regex():
        return '^(paint|watercolor)'

    @staticmethod
    def stylit_drymedia_styles_regex():
        return '^(charcoal|pencil|cpencil|exp|pastels)'

    @staticmethod
    def stylit_other_styles_regex():
        return '^(marker|ink)'


class LineStyles(object):
    """
    Helps select subsets of line styles from the Creative Flow+ Dataset.
    """
    TRAIN_STYLES = [
        'chalk0',
        'chalk1',
        'chalk2',
        'chalk3',
        'chalk6',
        'ink0',
        'ink1',
        'ink2',
        'ink4',
        'ink5',
        'marker1',
        'marker3',
        'marker4',
        'marker5',
        'pen0',
        'pen1',
        'pen4',
        'pen5',
        'pen6',
        'pencil0',
        'pencil2',
        'pencil3',
        'pencil4',
    ]
    TEST_STYLES = [
        'chalk4',
        'chalk5',
        'ink3',
        'ink6',
        'marker0',
        'marker2',
        'paint0',
        'paint1',
        'paint2',
        'paint3',
        'paint4',
        'paint5',
        'paint6',
        'pen2',
        'pen3',
        'pencil5',
        'pencil6'
    ]


class SequenceInfo(object):
    def __init__(self, scene_name, source, nframes, cam_idx, shading_styles, line_styles, has_flow, tags=[]):
        if len(shading_styles) != len(line_styles):
            raise ValueError('Shading and line style counts differ: %s VS %s' %
                             (str(shading_styles), str(line_styles)))
        self.scene_name = scene_name
        self.source = source
        self.nframes = nframes
        self.cam_idx = cam_idx
        self.shading_styles = shading_styles
        self.line_styles = line_styles
        self.has_flow = has_flow
        self.tags = tags

    def nstyles(self):
        return len(self.shading_styles)

    def nframes_in_all_styles(self, ignore_final_frame_with_no_flow=False):
        if ignore_final_frame_with_no_flow:
            return (self.nframes - 1) * len(self.shading_styles)
        else:
            return self.nframes * len(self.shading_styles)

    def get_style_frame_indices(self, global_frame, ignore_final_frame_with_no_flow=False):
        """
        A sequence can be rendered in multiple styles. E.g., if the sequence has 3 frames and 2 styles
        then the frames will be as follows:
        F0                  F1                 F2                 F3                 F4
        [frame0 in style0] [frame1 in style0] [frame2 in style0] [frame0 in style1] [frame1 in style1]...
        This method returns the actual frame and style indices for the input global frame such as F4 above.
        :param ignore_final_frame_with_no_flow: if set, final frame is always skipped, as it has no associated flow
        :param global_frame: frame number within the sequence of all frames in all styles
        :return: style index, frame index
        """
        tot_frames = self.nframes
        if ignore_final_frame_with_no_flow:
            tot_frames = tot_frames - 1
        style_idx = global_frame // tot_frames
        frame_idx = global_frame - tot_frames * style_idx
        return style_idx, frame_idx

    def get_meta_path(self, data_type, frame_idx=None, base_dir=''):
        if frame_idx is None or data_type in PathsHelper.META_INFO:
            return PathsHelper.meta_info_path(
                data_type, base_dir=base_dir, sequence_name=self.scene_name, cam_idx=self.cam_idx)
        else:
            return PathsHelper.meta_frame_path(
                data_type, base_dir=base_dir, sequence_name=self.scene_name, cam_idx=self.cam_idx,
                frame_idx=frame_idx)

    def get_render_path(self, data_type, style_idx, frame_idx=None, base_dir=''):
        if data_type == DataType.RENDER_SHADING:
            style_name = self.shading_styles[style_idx]
        elif data_type == DataType.RENDER_LINE or data_type == DataType.RENDER_LINE_ALPHA:
            style_name = self.line_styles[style_idx]
        else:
            style_name = '%s.%s' % (self.shading_styles[style_idx], self.line_styles[style_idx])
        if frame_idx is None or data_type in PathsHelper.RENDER_INFO:
            return PathsHelper.render_info_path(
                data_type, base_dir=base_dir, sequence_name=self.scene_name, cam_idx=self.cam_idx,
                style_idx=style_idx, style_name=style_name)
        else:
            return PathsHelper.render_frame_path(
                data_type, base_dir=base_dir, sequence_name=self.scene_name, cam_idx=self.cam_idx,
                style_idx=style_idx, style_name=style_name, frame_idx=frame_idx)

    def __str__(self):
        return '%s,cam%d' % (self.scene_name, self.cam_idx)

    def __repr__(self):
        return 'SequenceInfo:%s' % str(self)
