#!/usr/bin/python2.6

# Unittests for paris_rollins. Must be run as root, as actually runs
# paris-traceroute.

import os
import shutil
import tempfile
import time
import unittest
import paris_rollins as paris_rollins

class ParisRollinsTestCase(unittest.TestCase):

  def setUp(self):
    self.tmpdir = tempfile.mkdtemp()
  
  def tearDown(self):
    shutil.rmtree(self.tmpdir)

  def test_run(self):
    pool = paris_rollins.ParisTraceroutePool(self.tmpdir)
    local_ip = '127.0.0.1'
    base_local_port = 33457
    remote_ip = '127.0.0.1'
    remote_port = 9999
    # run full complement of workers, repeatedly.
    for log_time in range(5):
      workers = 0
      while pool.run_async(log_time, remote_ip, remote_port,
                           local_ip, base_local_port + workers):
        workers += 1
      # should be able to launch parallel traceroutes
      self.assertTrue(workers > 2)
      # wait until all traceroutes finish
      while not pool.free():
        time.sleep(1)
      # ensure all log files exist and have expected contents.
      for worker in range(workers):
        local_port = base_local_port + worker
        expected_log = os.path.join(
          self.tmpdir,
          paris_rollins.make_log_file_name(self.tmpdir, log_time,
                                           remote_ip, remote_port,
                                           local_ip, local_port))
        self.assertTrue(os.path.isfile(expected_log))
        self.assertTrue(os.path.getsize(expected_log) > 0)
        expected_log_header = (
          'traceroute [(%s:%u) -> (%s:%u)], protocol icmp, algo exhaustive' % (
              local_ip, local_port, remote_ip, remote_port))
        log_contents = open(expected_log).read()
        self.assertTrue(log_contents.startswith(expected_log_header))

  def test_recentcache(self):
    ip = '127.0.0.1'
    cache_timeout = 2
    cache = paris_rollins.RecentIPAddressCache(cache_timeout)
    for cache_refreshes in range(3):
      self.assertFalse(cache.cached(ip))
      cache.add(ip)
      self.assertTrue(cache.cached(ip))
      time.sleep(cache_timeout)


if __name__ == '__main__':
    unittest.main()

