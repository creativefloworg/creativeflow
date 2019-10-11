"""
I/O utilities for flow and other types of files.
"""
import glob
import math
import numpy as np
import os
import re
import struct
import sys
import zipfile

# first four bytes, should be the same in little endian
FLO_FILE_TAG_FLOAT = 202021.25  # check for this when READING the file
FLO_FILE_TAG_STRING = "PIEH"  # use this when WRITING the file

FLO_FILE_UNKNOWN_FLOW_THRESH = math.exp(9)
# value to use to represent unknown flow
FLO_FLOW_UNKNOWN_FLOW = math.exp(10)


def read_flow(flo_filename, slow_unpacking=False):
    """
    Loads the flo from a file in the MIDDLEBURY flow format.
    http://vision.middlebury.edu/flow/code/flow-code/README.txt

    Input:
    :param flo_filename: where to read flow from.
    :param slow_unpacking: reads values one at a time, ensuring data is
                           read correctly even on big-endian architectures.

    Output:
    Note on flow representation.
    io_util.read_flow returns F, an H x W x 2 float32 numpy array, where:
    H - number of rows, i.e. image height
    W - number of columns, i.e. image width
    2 - x, y flow vector value in pixels

    Note:
    F[r][c][0] - translation of pixel (x=c, y=r) from this to next frame in pixels
                  along x direction
    F[r][c][1] - translation of pixel (x=c, y=r) from this to next frame in pixels
                 along y direction (important! pixels moving UP have NEGATIVE flow)
    Input:
        flo_filename - The path to the flo file
    Output:
        flow - numpy array of size width x height x 2
    """
    file = open(flo_filename, 'rb')

    tag = struct.unpack('<f',file.read(4))[0]
    width = struct.unpack('<i',file.read(4))[0]
    height = struct.unpack('<i', file.read(4))[0]

    if tag != FLO_FILE_TAG_FLOAT:  # Simple test for correct endian
        raise ValueError("Wrong tag {0}".format_map(tag))

    # Check to sees integers were read correctly
    if width < 1 or width > 99999:
        raise ValueError("Wrong width {0} when reading from flow {1}".format(
            width, flo_filename))
    if height < 1 or height > 99999:
        raise ValueError("Wrong heigth {0} when reading from flow {1}".format(
            width, flo_filename))

    # Check endianness
    if sys.byteorder != 'little' and not slow_unpacking:
        raise RuntimeError(
            'For non-little endian architecture (%s), run read_flow with slow_unpacking=True' % sys.byteorder)

    if slow_unpacking:
        flow = np.zeros((height, width, 2), dtype=np.float32)
        for x in range(height):
            for y in range(width):
                data = file.read(4 * 2)
                if data == "":
                    raise ValueError("Flow file {0} is too short".format(flo_filename))
                flow[x][y] = np.array(struct.unpack('<'+'f'*2, data), dtype=np.float32)
    else:
        data = np.fromfile(file, np.float32, count=2 * width * height)
        flow = np.resize(data, (height, width, 2))

    file.close()
    return flow


def write_flow(flow, flo_filename, slow_packing=False):
    """
    Outputs the flow into a flo_file.

    Input:
        :param flow: 2D numpy array with 2 bands
        :param flo_filename: the full path and file name of the file to be outputed
        :param slow_packing: writes values one at a time, ensuring data is
                             stored correctly even on big-endian architectures.
    """

    width = flow.shape[1]
    height = flow.shape[0]

    if flow.shape[2] != 2:
        raise ValueError('Can only write flow with 2 channels, but input shape is %s)' % str(flow.shape))

    # Check endianness
    if sys.byteorder != 'little' and not slow_packing:
        raise RuntimeError(
            'For non-little endian architecture (%s), run write_flow with slow_packing=True' % sys.byteorder)

    # write the header
    file = open(flo_filename, "wb")
    file.write(struct.pack('<f', FLO_FILE_TAG_FLOAT))
    file.write(struct.pack('<i', width))
    file.write(struct.pack('<i', height))

    # Write the rest of the data
    if slow_packing:
        for x in range(height):
            for y in range(width):
                file.write(struct.pack('<'+'f'*2, flow[x][y][0], flow[x][y][1]))
    else:
        tmp = np.zeros((height, width * 2), dtype=np.float32)
        tmp[:, np.arange(width) * 2] = flow[:, :, 0]
        tmp[:, np.arange(width) * 2 + 1] = flow[:, :, 1]
        tmp.astype(np.float32).tofile(file)

    file.close()


def get_images_in_dir(dir_path):
    return [ f for f in os.listdir(dir_path)
             if f.endswith(('.jpg', '.jpeg', '.png', '.bmp', '.hdr',
                            '.JPG', '.JPEG', '.PNG', '.BMP', '.HDR')) ]


def strip_blender_name(name):
    return re.sub(r'_A(\:[a-z]+)?$', '', re.sub(r'\.[0-9]+$', '', name))


def compress_flows(dirname, zipfilename):
    fnames = glob.glob(os.path.join(dirname, '*.flo'))
    fnames.sort()

    flows = []
    for f in fnames:
        flows.append(np.expand_dims(read_flow(f), axis=0))

    F = np.concatenate(flows)
    compress_4dnparray(F, zipfilename)


def decompress_flows(zipfilename, output_dir=None, outfile_pattern='flow%06d.flo'):
    F = decompress_4dnparray(zipfilename)

    flows = []
    for i in range(F.shape[0]):
        if output_dir:
            write_flow(F[i,:,:,:], os.path.join(output_dir, outfile_pattern % (i + 1)))
        flows.append(F[i,:,:,:])

    return flows


def compress_arrays(dirname, shape, zipfilename, extension='.array'):
    fnames = glob.glob(os.path.join(dirname, '*' + extension))
    fnames.sort()

    arrays = []
    for f in fnames:
        arr = np.expand_dims(np.fromfile(f, dtype=np.float32).reshape(shape), axis=0)
        if len(arr.shape) < 4:
            arr = np.expand_dims(arr, -1)
        arrays.append(arr)

    F = np.concatenate(arrays)
    compress_4dnparray(F, zipfilename)


def decompress_arrays(zipfilename, output_dir=None, outfile_pattern='meta%06d.array'):
    F = decompress_4dnparray(zipfilename)

    arrays = []
    for i in range(F.shape[0]):
        arr = np.squeeze(F[i,:,:,:])
        arrays.append(arr)

        if output_dir:
            arr.tofile(os.path.join(output_dir, outfile_pattern % (i + 1)))

    return arrays


def compress_4dnparray(F, zipfilename):
    """
    Compresses array of size:
    nitems x width x height x nchannels
    """
    if len(F.shape) != 4:
        raise RuntimeError('Compressed array must have 4 dimensions, but is %s' % str(F.shape))

    width = F.shape[1]
    height = F.shape[2]
    nchannels = F.shape[3]
    F = np.reshape(F, [-1])

    # Write the giant NP file
    zipfileprefix = zipfilename.strip('.zip')
    tmpfilename = zipfileprefix + '.tmp.npbinary'
    F.tofile(tmpfilename)

    innerfilename = 'data.%d.%d.%d.binary' % (width, height, nchannels)
    zf = zipfile.ZipFile(zipfilename, "w", zipfile.ZIP_DEFLATED, allowZip64=True)
    zf.write(tmpfilename, '/' + innerfilename)
    zf.close()

    os.remove(tmpfilename)


def decompress_4dnparray(zipfilename):
    zf = zipfile.ZipFile(zipfilename, 'r', allowZip64=True)
    names = zf.namelist()

    # Decode flow dimensions from the inner filename
    if len(names) != 1:
        raise RuntimeError('Expected one file in zip %s' % zipfilename)

    pattern = r'.*data\.([0-9]+)\.([0-9]+)\.([0-9]+)\.binary$'
    r = re.match(pattern, names[0])

    if r is None or len(r.groups()) < 3:
        raise RuntimeError(
            'Expected inner zip filename to match %s in zip: %s' %
            (pattern, zipfilename))

    width = int(r.group(1))
    height = int(r.group(2))
    nchannels = int(r.group(3))

    # Read the actual data
    tmp_dir = os.path.dirname(zipfilename)
    zf.extract(names[0], tmp_dir)
    zf.close()

    extracted_file = os.path.join(tmp_dir, names[0])
    F = np.fromfile(extracted_file, dtype=np.float32)
    os.remove(extracted_file)

    F = F.reshape([-1, width, height, nchannels])
    return F


def get_filename_framenumber(infile):
    bname = os.path.basename(infile)
    r = re.match(r'[a-z_]+([0-9]+)\.[a-zA-Z]+', bname)
    if r is None:
        return None
    elif len(r.groups()) == 0:
        return None
    return int(r.group(1))


def parse_file_sequence(pattern, data, datakey):
    """
    Parses file sequence given a glob pattern and structures output by
    frame number. E.g.:

    out_data = {}
    parse_file_sequence("flow/flow*.flo", out_data, "flow");

    returns:
    data { 0: {"flow": flow0_file}, 1: {"flow": flow1_file}, 2: ...}
    """
    files = glob.glob(pattern)
    for f in files:
        fnum = get_filename_framenumber(f)
        if fnum is None:
            raise RuntimeError('Cannot parse framenumber from %s' % f)
        if fnum not in data:
            data[fnum] = {}
        data[fnum][datakey] = f
