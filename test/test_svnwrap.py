#!/usr/bin/env python

import unittest
import svnwrap
import warnings


class TestSvnwrap(unittest.TestCase):

    def setUp(self):
        warnings.simplefilter('error')

    def test_svnwrap_config(self):
        svnwrap.svnwrap_config()

    def test_paths_equal(self):
        self.assertTrue(svnwrap.paths_equal(
            'somepath',
            'somepath'))
        self.assertFalse(svnwrap.paths_equal(
            'somepath1',
            'somepath2'))


if __name__ == '__main__':
    unittest.main()
