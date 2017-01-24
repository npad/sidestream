"""Tests for sidestream."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import logging
import os
import unittest
import time
from test.test_support import EnvironmentVarGuard
import prometheus_client as prom
import urllib2

import exitstats
class FakeConnection():
  '''Substitute for Web100 connection object for testing.'''
  cid = 0
  values = {}

  def readall(self):
    '''Returns dictionary of metrics'''
    return self.values

  def setall(self, v):
    self.values = v

  def copy(self):
    result = FakeConnection()
    result.cid = self.cid
    result.values = self.values
    return result

  def __iter__(self):
    return values.__iter__()

class TestMonitoring(unittest.TestCase):
  def setUp(self):
    prom.start_http_server(exitstats.PROMETHEUS_SERVER_PORT)
    print('started server on port %s'%(exitstats.PROMETHEUS_SERVER_PORT))

  def testConnectionCount(self):
    c1 = FakeConnection()
    c1.cid = 1234
    c1.setall({"RemAddress": "5.4.3.2", "LocalAddress": "1.2.3.4", "other": "other"})
    exitstats.setkey(c1.values)
    exitstats.logConnection(c1)

    # Read from the httpserver and assert the correct connection count.
    url = "http://localhost:%s"%(exitstats.PROMETHEUS_SERVER_PORT)
    # Read in a while loop, since the server is a daemon and may not start immediately.
    while True:
      try:
        response = urllib2.urlopen(url).read()
        print("ok")
        break;
      except urllib2.URLError as e:
        print('-', end="")
        time.sleep(0.01)
      
    self.assertTrue("connection_count 1.0" in response)
    

class TestExitstats(unittest.TestCase):
  def remove_file(self, logdir, logname):
    ''' Utility to remove a file and its directory'''
    try:
      os.remove(logdir + logname)
      os.removedirs(logdir)
    except OSError:
      pass

  def assertExists(self, logdir, logname):
    '''Utility to assert that file exists'''
    try:
      os.stat(logdir + logname)
    except OSError as e:
      print('Expected file does not exist: ' + logdir + logname)
      print(e)
      self.assertIs(e, None)

  def testSetkey(self):
    exitstats.setkey({'foo':3, 'bar':2, 'baz':1})
    self.assertEqual(sorted(exitstats.active_vars), ['bar', 'baz', 'foo'])
    # stdvars should appear before others...
    exitstats.setkey({'MinA':3, 'MinB':2, 'MinRTT':1})
    self.assertEqual(exitstats.active_vars[0], 'MinRTT')
    self.assertTrue('MinA' in  exitstats.active_vars)

  def testUseLocalIP(self):
    with EnvironmentVarGuard() as env:
      env.set('SIDESTREAM_USE_LOCAL_IP', 'True')
      self.assertTrue(exitstats.useLocalIP())
    with EnvironmentVarGuard() as env:
      env.set('SIDESTREAM_USE_LOCAL_IP', 'False')
      self.assertFalse(exitstats.useLocalIP())

  def testGetName(self):
    '''Check that getlogf successfully create the expected file'''
    gm = time.gmtime(3600*814234)
    logdir, logname = exitstats.logName('server', gm, None)
    self.assertEquals(logdir, '2062/11/20/')
    self.assertEquals(logname, 'server20621120T10:00:00Z_ALL0.web100')

    # When we provide the local_ip address, environment shouldn't matter.
    with EnvironmentVarGuard() as env:
      env.set('SIDESTREAM_USE_LOCAL_IP', 'False')
      self.assertFalse(exitstats.useLocalIP())
      logdir, logname = exitstats.logName('server', gm, '5.4.3.2')
      self.assertEquals(logdir, '2062/11/20/')
      self.assertEquals(logname, 'server20621120T10:00:00Z_ALL0-5.4.3.2.web100')

    with EnvironmentVarGuard() as env:
      env.set('SIDESTREAM_USE_LOCAL_IP', 'True')
      self.assertTrue(exitstats.useLocalIP())
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
    exitstats.server = server = 'server'

    self.remove_file(logdir, logname)
    with EnvironmentVarGuard() as env:
      env.set('SIDESTREAM_USE_LOCAL_IP', 'False')
      self.assertFalse(exitstats.useLocalIP())
      _ = exitstats.getLogFile(3600*814234)

    self.assertExists(logdir, logname)

    logname_with_ip = 'server20621120T10:00:00Z_ALL0-5.4.3.2.web100'
    self.remove_file(logdir, logname_with_ip)
    with EnvironmentVarGuard() as env:
      env.set('SIDESTREAM_USE_LOCAL_IP', 'False')
      self.assertFalse(exitstats.useLocalIP())
      # Shouldn't matter if we specify the ip address.
      _ = exitstats.getLogFile(3600*814234, '5.4.3.2')

    # Check that file does not exist.
    with self.assertRaises(OSError):
      print(os.stat(logdir + logname_with_ip))

    # Clean up
    self.remove_file(logdir, logname)
    self.remove_file(logdir, logname_with_ip)

  def testGetLogFileWithLocalIP(self):
    '''Check that getlogf successfully create the expected file'''
    # Need to set up the variables key to avoid error.
    exitstats.setkey({'foo':3, 'bar':2, 'baz':1})

    logdir = '2062/11/20/'
    logname = 'server20621120T10:00:00Z_ALL0-5.4.3.2.web100'
    gm = time.gmtime(3600*814234)
    exitstats.server = server = 'server'

    self.remove_file(logdir, logname)
    with EnvironmentVarGuard() as env:
      env.set('SIDESTREAM_USE_LOCAL_IP', 'True')
      self.assertTrue(exitstats.useLocalIP())
      _ = exitstats.getLogFile(3600*814234, '5.4.3.2')

    self.assertExists(logdir, logname)

    # Clean up
    self.remove_file(logdir, logname)

if __name__ == '__main__':
  unittest.main()
