#!/usr/bin/env python

import unittest

import os
import random
import tempfile
import numpy as np
from skimage.io import imsave, imread
from datetime import datetime
import sys

import creativeflow.blender.io_util as io_util
from creativeflow.blender.misc_util import QuickTimer


def createRandomArr(w, h, nchannels=2):
    return ((np.random.rand(w, h, nchannels) - 0.5) * 200).astype(np.float32)


def createRandomUintArr(w, h, nchannels=2):
    return (np.random.rand(w, h, nchannels) * 255).astype(np.uint8)


class ReadWriteFlowTest(unittest.TestCase):
    def setUp(self):
        random.seed(datetime.now())
        self.qtimer = QuickTimer()

    def _run_read_write_test(self, slow_packing, slow_unpacking):
        flow = createRandomArr(random.randint(20, 1000), random.randint(25, 1000))
        directory = tempfile.gettempdir()
        flowfile = os.path.join(directory, 'flow%d.flo' % random.randint(1, 100000))
        self.qtimer.start('write_flow' + ('(slow)' if slow_packing else ''))
        io_util.write_flow(flow, flowfile, slow_packing=slow_packing)
        self.qtimer.end()

        self.qtimer.start('read_flow' + ('(slow)' if slow_unpacking else ''))
        restored_flow = io_util.read_flow(flowfile, slow_unpacking=slow_unpacking)
        self.qtimer.end()
        self.assertTrue(np.allclose(flow, restored_flow), msg='For flow file %s' % flowfile)

    def test_read_write(self):
        niterations = 10

        for x in range(niterations):
            self._run_read_write_test(slow_packing=True, slow_unpacking=True)

        if sys.byteorder == 'little':
            for x in range(niterations):
                self._run_read_write_test(slow_packing=False, slow_unpacking=False)
                self._run_read_write_test(slow_packing=True, slow_unpacking=False)
                self._run_read_write_test(slow_packing=False, slow_unpacking=True)

        print(self.qtimer.summary())


class CompressTest(unittest.TestCase):
    def setUp(self):
        random.seed(datetime.now())
        self.width = 25
        self.flows = [ createRandomArr(self.width, self.width) for x in range(7) ]
        self.arrays = [ createRandomArr(self.width, self.width, 3) for x in range(7) ]

    def test_compress_decompress_flow(self):
        rnum = random.randint(1, 10000)
        directory = tempfile.gettempdir()
        flow_dir = os.path.join(directory, 'flows%d' % rnum)
        os.mkdir(flow_dir)

        # Write all flows
        for i in range(len(self.flows)):
            flowfile = os.path.join(flow_dir, 'flow%02d.flo' % i)
            io_util.write_flow(self.flows[i], flowfile)
        print('Wrote flows to %s' % flow_dir)

        # Compress all flows
        zip_file = os.path.join(directory, 'flow_compr%d.zip' % rnum)
        io_util.compress_flows(flow_dir, zip_file)
        print('Compressed flows to %s' % zip_file)

        flows = io_util.decompress_flows(zip_file)
        self.assertEqual(len(self.flows), len(flows))

        for i in range(len(self.flows)):
            self.assertLess(np.sum(np.abs(self.flows[i] - flows[i])), 0.0001)

    def test_compress_decompress_arrays(self):
        rnum = random.randint(1, 10000)
        directory = tempfile.gettempdir()
        arr_dir = os.path.join(directory, 'arrays%d' % rnum)
        os.mkdir(arr_dir)

        # Write all arrays
        for i in range(len(self.arrays)):
            arrfile = os.path.join(arr_dir, 'meta%02d.array' % i)
            self.arrays[i].reshape([-1]).tofile(arrfile)
        print('Wrote arrays to %s' % arr_dir)

        # Compress all arrays
        zip_file = os.path.join(directory, 'arr_compr%d.zip' % rnum)
        io_util.compress_arrays(arr_dir, self.arrays[0].shape, zip_file)
        print('Compressed arrays to %s' % zip_file)

        arrays = io_util.decompress_arrays(zip_file)
        self.assertEqual(len(self.arrays), len(arrays))

        for i in range(len(self.arrays)):
            self.assertLess(np.sum(np.abs(self.arrays[i] - arrays[i])), 0.0001)

    def test_compress_decompress_images(self):
        orig_images = [createRandomUintArr(self.width, self.width, 3) for x in range(10)]

        rnum = random.randint(1, 10000)
        directory = tempfile.gettempdir()
        arr_dir = os.path.join(directory, 'images%d' % rnum)
        os.mkdir(arr_dir)

        # Write all images
        for i in range(len(orig_images)):
            arrfile = os.path.join(arr_dir, 'meta%02d.png' % i)
            imsave(arrfile, orig_images[i])
        print('Wrote arrays to %s' % arr_dir)

        # Compress all images
        zip_file = os.path.join(directory, 'img_compr%d.zip' % rnum)
        io_util.compress_images(arr_dir, zip_file, read_function=imread)
        print('Compressed images to %s' % zip_file)

        images = io_util.decompress_images(zip_file, write_function=imsave)
        self.assertEqual(len(orig_images), len(images))

        for i in range(len(orig_images)):
            self.assertTrue(np.allclose(orig_images[i], images[i]),
                            msg=('Failed to decompress image %d' % i))


class MiscIoTest(unittest.TestCase):
    def test_get_filename_framenumber(self):
        fnumber = io_util.get_filename_framenumber('/tmp/REG3_500/results/uncompressed/bunny_teapot/cam0/metadata/flow/flow000002.flo')
        self.assertEqual(2, fnumber)

        fnumber = io_util.get_filename_framenumber('some/2233/f233/io15.JPG')
        self.assertEqual(15, fnumber)

        fnumber = io_util.get_filename_framenumber('D://Coding/Animation/cartoon-flow/imaginary.JPG')
        self.assertTrue(fnumber is None)


if __name__ == '__main__':
    unittest.main()
