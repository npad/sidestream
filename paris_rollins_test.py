#!/usr/bin/python2.6

# Unittests for paris_rollins. Must be run as root, as actually runs
# paris-traceroute.

import os
import shutil
import tempfile
import unittest
import paris_rollins as paris_rollins

class ParisRollinsTestCase(unittest.TestCase):

  def setUp(self):
    self.tmpdir = tempfile.mkdtemp()
  
  def tearDown(self):
    shutil.rmtree(self.tmpdir)

  def test_runworker(self):
    paris_rollins.run_worker(
      self.tmpdir, 999, '127.0.0.1', 33457, '127.0.0.1', 9999)
    expected_log = os.path.join(
      self.tmpdir,
      '1970/01/01/19700101T00:16:39Z127.0.0.1-33457-127.0.0.1-9999.paris')
    self.assertTrue(os.path.isfile(expected_log))
    self.assertTrue(os.path.getsize(expected_log) > 0)


if __name__ == '__main__':
    unittest.main()

