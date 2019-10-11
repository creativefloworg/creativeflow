"""
Contains utilities for working with optical flow arrays.

Note on flow representation:
    io_util.read_flow returns F, an H x W x 2 float32 numpy array, where:
    H - number of rows, i.e. image height
    W - number of columns, i.e. image width
    2 - x, y flow vector value in pixels

    Note:
    F[r][c][0] - translation of pixel (x=c, y=r) from this to next frame in pixels
                  along x direction
    F[r][c][1] - translation of pixel (x=c, y=r) from this to next frame in pixels
                 along y direction (important! pixels moving UP have NEGATIVE flow)
"""
import numpy as np
import math
from skimage.transform import resize


def get_val_interpolated(flow, r_float, c_float):
    """
    Returns flow value for float row, column position using bilinear interpolation.
    """
    rows = flow.shape[0]
    cols = flow.shape[1]

    if (r_float > rows - 1 or r_float < 0 or
            c_float > cols - 1 or c_float < 0):
        raise IndexError('Accessing flow of shape %s with float index (%0.3f, %0.3f)'
                         % (str(flow.shape), r_float, c_float))

    def get_neighbors(v_float, v_size):
        v_prev = int(math.floor(v_float))
        v_next = int(math.ceil(v_float))
        v_alpha = v_next - v_float
        if v_next > v_size - 1:
            v_next = v_prev
        return v_prev, v_next, v_alpha

    r_prev, r_next, r_alpha = get_neighbors(r_float, rows)
    c_prev, c_next, c_alpha = get_neighbors(c_float, cols)

    val_prev = flow[r_prev][c_prev] * c_alpha + flow[r_prev][c_next] * (1 - c_alpha)
    val_next = flow[r_next][c_prev] * c_alpha + flow[r_next][c_next] * (1 - c_alpha)

    return val_prev * r_alpha + val_next * (1 - r_alpha)


def get_val_interpolated_vec(flow, r_float, c_float, fill_val=0.0):
    """
    @param flow: N x M x 2 flow array, with channel 0 - x movement, channel 1 - y movement
    @param r_float: row values to interpolate at, as vector or 2d array
    @param c_float: column values in the same shape as r_float
    @param fill_val: what to put for invalid row,col values
    @return 2-channel array with the same first one or two dimensions as r_float,
            holding interpolated flow values
    """
    rows = flow.shape[0]
    cols = flow.shape[1]

    r_float = np.asarray(r_float)
    c_float = np.asarray(c_float)

    out_shape = [x for x in r_float.shape]
    invalid = np.zeros(out_shape, dtype=np.int32)

    if len(flow.shape) > 2:
        out_shape.append(flow.shape[2])  # add channels

    invalid[r_float > rows - 1] = 1
    invalid[r_float < 0] = 1
    invalid[c_float > cols - 1] = 1
    invalid[c_float < 0] = 1

    r = r_float.reshape([-1])
    c = c_float.reshape([-1])

    r_prev = np.clip(np.floor(r).astype(int), 0, rows - 1)
    r_next = np.clip(np.ceil(r).astype(int), 0, rows - 1)
    c_prev = np.clip(np.floor(c).astype(int), 0, cols - 1)
    c_next = np.clip(np.ceil(c).astype(int), 0, cols - 1)

    r_alpha = np.expand_dims(r_next - r, axis=1)
    c_alpha = np.expand_dims(c_next - c, axis=1)

    val_prev = flow[r_prev, c_prev, :] * c_alpha + flow[r_prev, c_next, :] * (1 - c_alpha)
    val_next = flow[r_next, c_prev, :] * c_alpha + flow[r_next, c_next, :] * (1 - c_alpha)

    val = val_prev * r_alpha + val_next * (1 - r_alpha)
    val = val.reshape(out_shape)
    val[invalid > 0, :] = fill_val

    return val, invalid


def get_occlusions_vec(forward_flow, back_flow, pixel_threshold=0.01):
    """
    Same as get_occlusions, but 100x faster.
    """
    rows = forward_flow.shape[0]
    cols = forward_flow.shape[1]
    res = np.zeros((rows, cols), dtype=np.uint8)

    f_idx = np.indices((rows, cols))
    b_idx = np.concatenate([np.expand_dims(f_idx[0, :, :] + forward_flow[:, :, 1], axis=2),
                            np.expand_dims(f_idx[1, :, :] + forward_flow[:, :, 0], axis=2)],
                           axis=2)

    bf, invalid = get_val_interpolated_vec(back_flow, b_idx[:, :, 0], b_idx[:, :, 1])
    delta = np.sqrt(np.sum(np.square(forward_flow + bf), axis=2))

    res[delta > pixel_threshold] = 255
    res[invalid > 0] = 255
    return res


def get_occlusions(forward_flow, back_flow, pixel_threshold=0.01):
    """
    Calculates pixels in frame 0 which are not visible in frame 1, given:
    @param forward_flow n x n x 2 forward flow for frame 0
    @param back_flow    n x n x 2 back flow for frame 1
    @param pixel_threshold how much the flows are allowed to disagree
    @return uint8 image array with white pixels representing occluded pixels
    """
    rows = forward_flow.shape[0]
    cols = forward_flow.shape[1]
    res = np.zeros((rows, cols), dtype=np.uint8)
    for r in range(rows):
        for c in range(cols):
            ff = forward_flow[r][c]
            b_r = r + ff[1]  # row in frame 1
            b_c = c + ff[0]  # col in frame 1
            # print('R,C (%d, %d) --> (%0.2f, %0.2f)' % (r, c, b_r, b_c))

            is_occluded = False
            if b_r > rows - 1 or b_r < 0 or b_c > cols - 1 or b_c < 0:
                is_occluded = True
            else:
                bf = get_val_interpolated(back_flow, b_r, b_c)
                delta = np.linalg.norm(ff + bf)
                if delta > pixel_threshold:
                    is_occluded = True

            if is_occluded:
                res[r][c] = 255
    return res


def cross_check_sanity(flow0, ids0, ids1, corresp0, corresp1, occlusions0, row0, col0,
                       verbose=False, output_sanity_type=False):
    """
    Cross checks that flow and correspondeces agree, or that the pixel is marked as occluded.
    If we follow flow for a non-occluded pixel, then the new location should have the same
    objectid and approximately same color in the correspondence image in the next frame.
    This function performs test a single pixel at location row0, col0 in the first frame.
    While this check is approximate, checking that most pixels are "sane" helps ensure the
    integrity of our data.

    If output_sanity_type, will output:
    0 - Sane
    1 - Flow and correspondences agree, but pixel not marked as occluded
    2 - Next frame pixel out of bounds, but pixel not marked as occluded
    3 - Ids disagree, but pixel not marked as occluded
    4 - Correspondences disagree, but pixel not marked as occluded
    """
    ids_atol = 1
    corr_atol = 4
    if ids0.dtype != np.uint8 or ids1.dtype != np.uint8:
        ids_atol = 0.01
        print('WARNING: Ids image dtype (%s) is not uint8; thresholds might be off' %
              str(ids0.dtype))

    if corresp0.dtype != np.uint8 or corresp1.dtype != np.uint8:
        corr_atol = 0.016
        print('WARNING: Correspondence image dtype (%s) is not uint8; thresholds might be off' %
              str(corresp0.dtype))

    if len(corresp0.shape) != 3 or len(corresp1.shape) != 3:
        raise RuntimeError('Correspondences must have the color component.')

    rows = flow0.shape[0]
    cols = flow0.shape[1]
    ff = flow0[row0][col0]
    is_occluded = occlusions0[row0][col0] > 200

    row1 = row0 + ff[1]  # row in frame 1
    col1 = col0 + ff[0]  # col in frame 1

    in_bounds = row1 >= 0 and col1 >= 0 and row1 <= rows - 1 and col1 <= cols - 1
    all_agree = in_bounds

    if all_agree:
        idcolor0 = ids0[row0][col0]
        idcolor1 = ids1[int(round(row1))][int(round(col1))]
        ids_agree = np.allclose(idcolor0, idcolor1, atol=ids_atol)
        all_agree = all_agree and ids_agree

        if all_agree:
            # Do correspondences agree?
            corrcolor0 = corresp0[row0][col0]
            corrcolor1 = get_val_interpolated(corresp1, row1, col1)
            corr_agree = np.allclose(corrcolor0, corrcolor1, atol=corr_atol)
            all_agree = all_agree and corr_agree

    is_sane = (all_agree and not is_occluded) or (not all_agree and is_occluded)

    sanity_type = 0
    if not is_sane:
        cstr = '(%d, %d) -> (%0.3f, %0.3f)' % (row0, col0, row1, col1)
        if all_agree:
            sanity_type = 1
            if verbose:
                print('Flow and correspondences %s agree, but pixel is marked as occluded' % cstr)
        else:
            if not in_bounds:
                sanity_type = 2
                if verbose:
                    print('Next frame pixel %s out of bounds, but pixel not marked as occluded' % cstr)
            elif not ids_agree:
                sanity_type = 3
                if verbose:
                    print('Ids %s disagree, but pixel not marked as occluded' % cstr)
            else:
                sanity_type = 4

                if verbose:
                    print('Correspondences %s disagree, but pixel not marked as occluded: %s vs. %s' %
                          (cstr, str(corrcolor0).replace('\n', ' '), str(corrcolor1).replace('\n', ' ')))

    if output_sanity_type:
        return sanity_type
    else:
        return is_sane


# fast re-sample layer, taken from:
# https://github.com/liruoteng/OpticalFlowToolkit/blob/master/lib/flowlib.py
def resample_flow(img, sz):
    """
    img: flow map to be resampled
    sz: new flow map size. Must be [height,weight]
    """
    original_image_size = img.shape
    in_height = img.shape[0]
    in_width = img.shape[1]
    out_height = sz[0]
    out_width = sz[1]
    out_flow = np.zeros((out_height, out_width, 2))
    # find scale
    height_scale = float(in_height) / float(out_height)
    width_scale = float(in_width) / float(out_width)

    [x, y] = np.meshgrid(range(out_width), range(out_height))
    xx = x * width_scale
    yy = y * height_scale
    x0 = np.floor(xx).astype(np.int32)
    x1 = x0 + 1
    y0 = np.floor(yy).astype(np.int32)
    y1 = y0 + 1

    x0 = np.clip(x0, 0, in_width - 1)
    x1 = np.clip(x1, 0, in_width - 1)
    y0 = np.clip(y0, 0, in_height - 1)
    y1 = np.clip(y1, 0, in_height - 1)

    Ia = img[y0, x0, :]
    Ib = img[y1, x0, :]
    Ic = img[y0, x1, :]
    Id = img[y1, x1, :]

    wa = (y1 - yy) * (x1 - xx)
    wb = (yy - y0) * (x1 - xx)
    wc = (y1 - yy) * (xx - x0)
    wd = (yy - y0) * (xx - x0)
    out_flow[:, :, 0] = (Ia[:, :, 0] * wa + Ib[:, :, 0] * wb +
                         Ic[:, :, 0] * wc + Id[:, :, 0] * wd) * out_width / in_width
    out_flow[:, :, 1] = (Ia[:, :, 1] * wa + Ib[:, :, 1] * wb +
                         Ic[:, :, 1] * wc + Id[:, :, 1] * wd) * out_height / in_height

    return out_flow


def resample_objectids(objids, dims):
    """
    objids: uint8 image
    dims: first two components of the shape
    """
    # Avoid smoothing or distorting colors as much as possible
    new_shape = (dims[0], dims[1], objids.shape[2])
    res = resize(objids, new_shape, order=0, mode='constant', preserve_range=True, anti_aliasing=False)
    return res.astype(np.uint8)  # simple cast
