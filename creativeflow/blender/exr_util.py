"""
Utilities related to working with OpenEXR files (www.openexr.com). Note that some things, like parsing flow from
multilayer EXR files output by blender, have been experimentally determined by testing specific examples. This
is specific to behavior of Blender 2.79. Regression tests for our pipeline tests for any deviations.
"""
import OpenEXR
import numpy as np


def read_exr_metadata(exr_file):
    exr = OpenEXR.InputFile(exr_file)

    return {'flow': read_flow(exr),
            'back_flow': read_back_flow(exr),
            'depth': read_depth(exr)}


def read_flow(exr):
    # It is perplexing, but this appears to be correct based on carefully examined examples.
    # xflow: -Z, yflow: W
    res = channels_to_array(exr, ['Vector.Z', 'Vector.W'])
    res[:, :, 0] = -res[:, :, 0]
    return res


def read_back_flow(exr):
    # This appears to be correct based on carefully examined examples.
    # x backflow: X, ybackflow: -Y
    res = channels_to_array(exr, ['Vector.X', 'Vector.Y'])
    res[:, :, 1] = -res[:,:,1]
    return res


def read_depth(exr):
    return channels_to_array(exr, ['Depth.Z', 'Combined.A'], pick_any=True)


def get_size(exr):
    dw = exr.header()['dataWindow']
    size = (dw.max.x - dw.min.x + 1, dw.max.y - dw.min.y + 1)
    return size


def channels_to_array(exr, channel_patterns, pick_any=False):
    size = get_size(exr)

    if len(channel_patterns) == 1:
        return __parse_channel(exr, channel_patterns[0], size, pick_any=pick_any)

    arrays = []
    for cp in channel_patterns:
        arrays.append(
            np.expand_dims(
                __parse_channel(exr, cp, size, pick_any=pick_any), axis=2))

    return np.concatenate(arrays, axis=2)


def __parse_channel(exr, channel_pattern, size, pick_any=False):
    channels = [k for k in exr.header()['channels'].keys() if channel_pattern in k]
    if len(channels) > 1 and not pick_any:
        likely_match = 'RenderLayer.%s' % channel_pattern
        if likely_match in channels:
            channels = [ likely_match ]
        else:
            raise RuntimeError('More than one channel matched %s: %s' %
                               (channel_pattern, ', '.join(channels)))
    if len(channels) == 0:
        raise RuntimeError('No channel matched %s out of: %s' %
                           (channel_pattern, ', '.join(exr.header()['channels'].keys())))

    Vstr = exr.channel(channels[0])
    V = np.frombuffer(Vstr, dtype = np.float32)
    Vr = V.reshape(size)
    return Vr
