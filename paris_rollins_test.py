#!/usr/bin/python2.6

# Unittests for paris_rollins. Must be run as root, as actually runs
# paris-traceroute.

import os
import re
import shutil
import tempfile
import time
import unittest
import paris_rollins as paris_rollins

class ParisRollinsTestCase(unittest.TestCase):
  # We would prefer to use a local IP, but paris traceroute doesn't
  # let us choose which interface the test runs on - and doesn't
  # necessarily use the loopback interface for tests to 127.0.0.1
  TEST_DEST_IP = '8.8.8.8'

  def setUp(self):
    self.tmpdir = tempfile.mkdtemp()

  def tearDown(self):
    shutil.rmtree(self.tmpdir)

  def test_run(self):
    pool = paris_rollins.ParisTraceroutePool(self.tmpdir)
    test_hostname = 'test.host'
    local_ip = '127.0.0.1'
    local_port = 6666
    base_local_port = 33457
    remote_ip = self.TEST_DEST_IP
    remote_port = 9999
    # run full complement of workers, repeatedly.
    for log_time in range(5):
      workers = 0
      traceroute_port = base_local_port + workers
      while pool.run_async(log_time, test_hostname, traceroute_port,
                           remote_ip, remote_port, local_ip, local_port):
        workers += 1
      # should be able to launch parallel traceroutes
      self.assertTrue(workers > 2)
      # wait until all traceroutes finish
      while not pool.idle():
        time.sleep(1)
      # ensure all log files exist and have expected contents.
      for worker in range(workers):
        expected_log = os.path.join(
          self.tmpdir,
          paris_rollins.make_log_file_name(self.tmpdir, log_time,
                                           test_hostname,
                                           remote_ip, remote_port,
                                           local_ip, local_port))
        self.assertTrue(os.path.isfile(expected_log))
        self.assertTrue(os.path.getsize(expected_log) > 0)
        expected_log_header = re.compile(
          'traceroute \[\(%s:%u\) -> \(%s:%u\)\], protocol icmp, algo exhaustive' % (
              '([\d\.]+)', traceroute_port, remote_ip, remote_port))
        log_contents = open(expected_log).read()
        self.assertTrue(expected_log_header.match(log_contents) is not None)

  def test_recentcache(self):
    ip = self.TEST_DEST_IP
    cache_timeout = 2
    cache = paris_rollins.RecentIPAddressCache(cache_timeout, cache_timeout, cache_timeout)
    for cache_refreshes in range(3):
      self.assertFalse(cache.cached(ip))
      cache.add(ip)
      self.assertTrue(cache.cached(ip))
      time.sleep(cache_timeout + .1)

  def test_cache_randomness(self):
    lo, av, hi = 1, 5, 100
    cache = paris_rollins.RecentIPAddressCache(av, lo, hi)
    times = []
    for _ in range(1000):
      times.append(cache._new_wait_time())
    self.assertTrue(min(times) >= lo)
    self.assertTrue(min(times) < hi)
    self.assertTrue(max(times) <= hi)
    self.assertTrue(max(times) > lo)


if __name__ == '__main__':
    unittest.main()

