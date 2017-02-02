"""Tests for sidestream."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import logging
import os
import re
import time
import unittest
import urllib2

from test.test_support import EnvironmentVarGuard
import prometheus_client as prom
from freezegun import freeze_time

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
  stats_writer = None

  def setUp(self):
    global stats_writer
    prom.start_http_server(exitstats.PROMETHEUS_SERVER_PORT)
    stats_writer = exitstats.Web100StatsWriter('server')

  def tearDown(self):
    # Ideally should shut down the server daemon.
    pass

  @freeze_time("2014-02-23 10:23:34", tz_offset=0)
  def testConnectionCount(self):
    c1 = FakeConnection()
    c1.cid = 1234
    c1.setall({"RemAddress": "5.4.3.2", "LocalAddress": "1.2.3.4",
               "LocalPort":432, "RemPort":234})
    stats_writer.setkey(c1.values)
    # This triggers a log file creation
    stats_writer.logConnection(c1)

    # Read from the httpserver and assert the correct connection count.
    url = "http://localhost:%s"%(exitstats.PROMETHEUS_SERVER_PORT)
    # Read in a while loop, since the server is a daemon and may not start immediately.
    for _ in range(1000):
      try:
        response = urllib2.urlopen(url).read()
        break;
      except urllib2.URLError:
        time.sleep(0.01)
    else:
      raise urllib2.URLError('Page not found')

    rex = re.compile( '^sidestream_connection_count[{]source=\"ipv4\"[}] (.*)$', re.M )
    count_line = rex.search(response)
    self.assertIsNotNone(count_line, response)
    self.assertGreaterEqual(count_line.group(1), 1.0)

one_hour = (60*60)

class TestExitstats(unittest.TestCase):
  stats_writer = None

  def setUp(self):
    global stats_writer
    stats_writer = exitstats.Web100StatsWriter('server/')

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
      print(e)
      self.assertIs(e, 'Expected file does not exist: ' + logdir + logname)

  def testSetkey(self):
    stats_writer.setkey({'foo':3, 'bar':2, 'baz':1})
    self.assertEqual(sorted(stats_writer.active_vars), ['bar', 'baz', 'foo'])
    # stdvars should appear before others...
    stats_writer.setkey({'MinA':3, 'MinB':2, 'MinRTT':1})
    self.assertEqual(stats_writer.active_vars[0], 'MinRTT')
    self.assertTrue('MinA' in  stats_writer.active_vars)

  def testUseLocalIP(self):
    with EnvironmentVarGuard() as env:
      env.set('SIDESTREAM_USE_LOCAL_IP', 'True')
      self.assertTrue(stats_writer.useLocalIP())
    with EnvironmentVarGuard() as env:
      env.set('SIDESTREAM_USE_LOCAL_IP', 'False')
      self.assertFalse(stats_writer.useLocalIP())

  @freeze_time("2014-02-23 10:23:34", tz_offset=0)
  def testLogName(self):
    '''Check that getlogf successfully create the expected file'''
    local_time = time.time()
    local_hour = int(local_time / one_hour) * one_hour
    logdir, logname = stats_writer.logName(time.gmtime(local_hour), None)
    self.assertEquals(logdir, '2014/02/23/server/')
    self.assertEquals(logname, '20140223T10:00:00Z_ALL0.web100')

    # When we provide the local_ip address, environment shouldn't matter.
    with EnvironmentVarGuard() as env:
      env.set('SIDESTREAM_USE_LOCAL_IP', 'False')
      self.assertFalse(stats_writer.useLocalIP())
      logdir, logname = stats_writer.logName(time.gmtime(local_hour), '5.4.3.2')
      self.assertEquals(logdir, '2014/02/23/server/')
      self.assertEquals(logname, '20140223T10:00:00Z_5.4.3.2_0.web100')

    with EnvironmentVarGuard() as env:
      env.set('SIDESTREAM_USE_LOCAL_IP', 'True')
      self.assertTrue(stats_writer.useLocalIP())
      logdir, logname = stats_writer.logName(time.gmtime(local_hour), '5.4.3.2')
      self.assertEquals(logdir, '2014/02/23/server/')
      self.assertEquals(logname, '20140223T10:00:00Z_5.4.3.2_0.web100')

  @freeze_time("2014-02-23 10:23:34", tz_offset=0)
  def testGetLogFileOldBehavior(self):
    '''Check that getlogf successfully create the expected file'''
    # Ensure that the log file cache is empty.
    stats_writer.closeLogs()
    # Need to set up the variables key to avoid error.
    stats_writer.setkey({'foo':3, 'bar':2, 'baz':1})

    local_time = time.time()
#    local_hour = int(local_time / one_hour) * one_hour
    logdir = '2014/02/23/server/'
    logname = '20140223T10:00:00Z_ALL0.web100'
    stats_writer.server = server = 'server/'

    self.remove_file(logdir, logname)
    with EnvironmentVarGuard() as env:
      env.set('SIDESTREAM_USE_LOCAL_IP', 'False')
      self.assertFalse(stats_writer.useLocalIP())
      _ = stats_writer.getLogFile(local_time)

    self.assertExists(logdir, logname)
    self.remove_file(logdir, logname)

  @freeze_time("2014-02-23 10:23:34", tz_offset=0)
  def testGetLogFileOldBehaviorWithIP(self):
    '''Check that old file is created even if local IP is provided'''
    # Ensure that the log file cache is empty.
    stats_writer.closeLogs()
    # Need to set up the variables key to avoid error.
    stats_writer.setkey({'foo':3, 'bar':2, 'baz':1})
    local_time = time.time()
#    local_hour = int(local_time / one_hour) * one_hour
    logdir = '2014/02/23/server/'
    logname = '20140223T10:00:00Z_ALL0.web100'
    logname_with_ip = '20140223T10:00:00Z_5.4.3.2_0.web100'
    stats_writer.server = server = 'server/'

    self.remove_file(logdir, logname)
    self.remove_file(logdir, logname_with_ip)
    with EnvironmentVarGuard() as env:
      env.set('SIDESTREAM_USE_LOCAL_IP', 'False')
      self.assertFalse(stats_writer.useLocalIP())
      # Shouldn't matter if we specify the ip address.
      _ = stats_writer.getLogFile(local_time, '5.4.3.2')

    # Check that IP named file does not exist.
    with self.assertRaises(OSError):
      print(os.stat(logdir + logname_with_ip))
    # Check that ALL file exists.
    self.assertExists(logdir, logname)

    # Clean up
    self.remove_file(logdir, logname)
    self.remove_file(logdir, logname_with_ip)

  @freeze_time("2014-02-23 10:23:34", tz_offset=0)
  def testGetLogFileWithLocalIP(self):
    '''Check that getlogf successfully create the expected file'''
    # Ensure that the log file cache is empty.
    stats_writer.closeLogs()
    # Need to set up the variables key to avoid error.
    stats_writer.setkey({'foo':3, 'bar':2, 'baz':1})

    t = time.time()
    local_hour = int(t / one_hour) * one_hour
    logdir = '2014/02/23/server/'
    logname = '20140223T10:00:00Z_5.4.3.2_0.web100'
    stats_writer.server = server = 'server/'

    self.remove_file(logdir, logname)
    with EnvironmentVarGuard() as env:
      env.set('SIDESTREAM_USE_LOCAL_IP', 'True')
      self.assertTrue(stats_writer.useLocalIP())
      _ = stats_writer.getLogFile(t, '5.4.3.2')

    self.assertExists(logdir, logname)

    # Clean up
    self.remove_file(logdir, logname)

  def testHourRolloverWithLocalIP(self):
    '''Check that log file cache is cleared at end of hour.'''
    # Ensure that the log file cache is empty.
    stats_writer.closeLogs()

    c1 = FakeConnection()
    c1.cid = 1234
    c1.setall({"RemAddress": "5.4.3.2", "LocalAddress": "1.2.3.4",
               "LocalPort":432, "RemPort":234})

    logdir = '2014/02/23/server/'
    logname10 = '20140223T10:00:00Z_1.2.3.4_0.web100'
    logname11 = '20140223T10:00:00Z_1.2.3.4_0.web100'
    # Clean up files possibly left over from previous tests.
    self.remove_file(logdir, logname10)
    self.remove_file(logdir, logname11)

    stats_writer.server = server = 'server/'
    with EnvironmentVarGuard() as env:
      env.set('SIDESTREAM_USE_LOCAL_IP', 'True')
      with freeze_time("2014-02-23 10:23:34", tz_offset=0):
        # This triggers a log file creation
        stats_writer.logConnection(c1)

        self.assertExists(logdir, logname10)

      with freeze_time("2014-02-23 11:00:00", tz_offset=0):
        # This triggers a log file creation
        stats_writer.logConnection(c1)

        self.assertExists(logdir, logname11)

    # Clean up
    self.remove_file(logdir, logname10)
    self.remove_file(logdir, logname11)

if __name__ == '__main__':
  unittest.main()
