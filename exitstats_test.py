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

  def testSetkey(self):
    exitstats.setkey({'foo':3, 'bar':2, 'baz':1})
    self.assertEqual(sorted(exitstats.active_vars), ['bar', 'baz', 'foo'])
    # stdvars should appear before others...
    exitstats.setkey({'MinA':3, 'MinB':2, 'MinRTT':1})
    self.assertEqual(exitstats.active_vars[0], 'MinRTT')
    self.assertTrue('MinA' in  exitstats.active_vars)

  def testGetName(self):
    '''Check that getlogf successfully create the expected file'''
    gm = time.gmtime(3600*814234)
    logdir, logname = exitstats.logName('server', gm, None)
    self.assertEquals(logdir, '2062/11/20/')
    self.assertEquals(logname, 'server20621120T10:00:00Z_ALL0.web100')

    gm = time.gmtime(3600*814234)
    logdir, logname = exitstats.logName('server', gm, '5.4.3.2')
    self.assertEquals(logdir, '2062/11/20/')
    self.assertEquals(logname, 'server20621120T10:00:00Z_ALL0-5.4.3.2.web100')

  def testGetLogFileOldBehavior(self):
    '''Check that getlogf successfully create the expected file'''
    # Need to set up the variables key to avoid error.
    exitstats.setkey({'foo':3, 'bar':2, 'baz':1})

    logdir = '2062/11/20/'
    logname = 'server20621120T10:00:00Z_ALL0.web100'
    gm = time.gmtime(3600*814234)
    try:
      os.remove(logdir + logname)
      os.removedirs(logdir)
    except OSError:
      pass

    exitstats.server = server = 'server'
    _ = exitstats.getLogFile(3600*814234)

    try:
      os.stat(logdir + logname)
    except OSError as e:
      print('Expected file not created: ' + logdir + logname)
      print(e)

    # Clean up
    try:
      os.remove(logdir + logname)
      os.removedirs(logdir)
    except OSError:
      pass

  def testGetLogFileWithLocalIP(self):
    '''Check that getlogf successfully create the expected file'''
    # Need to set up the variables key to avoid error.
    exitstats.setkey({'foo':3, 'bar':2, 'baz':1})

    logdir = '2062/11/20/'
    logname = 'server20621120T10:00:00Z_ALL0-5.4.3.2.web100'
    gm = time.gmtime(3600*814234)
    try:
      os.remove(logdir + logname)
      os.removedirs(logdir)
    except OSError:
      pass

    exitstats.server = server = 'server'
    _ = exitstats.getLogFile(3600*814234, '5.4.3.2')

    try:
      os.stat(logdir + logname)
    except OSError as e:
      print('Expected file not created: ' + logdir + logname)
      print(e)

    # Clean up
    try:
      os.remove(logdir + logname)
      os.removedirs(logdir)
    except OSError:
      pass


if __name__ == '__main__':
  unittest.main()
