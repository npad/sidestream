"""Tests for sidestream."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import logging
import os
import unittest
import time

import exitstats

class ExitstatsTest(unittest.TestCase):

  def testSetKey(self):
    exitstats.setkey({'foo':3, 'bar':2, 'baz':1})
    self.assertEqual(sorted(exitstats.active_vars), ['bar', 'baz', 'foo'])
    # stdvars go in front...
    exitstats.setkey({'MinA':3, 'MinB':2, 'MinRTT':1})
    self.assertEqual(exitstats.active_vars[0], 'MinRTT')
    self.assertTrue('MinA' in  exitstats.active_vars)

    exitstats.server = server = 'foo'
    _ = exitstats.getlogf(3600*945214)

if __name__ == '__main__':
  unittest.main()
