#!/usr/bin/python2.6

# Unittests for paris_rollins. Must be run as root, as actually runs
# paris-traceroute.

import os
import re
import shutil
import tempfile
import thread
import SimpleHTTPServer
import socket
import SocketServer
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
    cache = paris_rollins.RecentIPAddressCache(cache_timeout)
    for cache_refreshes in range(3):
      self.assertFalse(cache.cached(ip))
      cache.add(ip)
      self.assertTrue(cache.cached(ip))
      time.sleep(cache_timeout)

  def test_parse_ss_output(self):
    connections = {}
    paris_rollins.parse_ss_line('ESTAB 0 0 127.0.0.1:9557 128.0.0.1:40171', connections)
    self.assertEqual(len(connections), 1)
    connection = paris_rollins.Connection(local_ip='127.0.0.1', local_port='9557', remote_ip='128.0.0.1', remote_port='40171')
    self.assertTrue(connection in connections)
    self.assertEqual(connections[connection], 'ESTAB')

  def test_isIPv4(self):
    self.assertTrue(paris_rollins.is_IPv4('127.0.0.1'))
    self.assertFalse(paris_rollins.is_IPv4('2620:0:1003:413:ad1b:7f2:9992:63b2'))


class SocketPollingTestCase(unittest.TestCase):
  def setUp(self):
    self.assertTrue(paris_rollins.ignore_ip('127.0.0.1'))
    self._cached_ignored_nets = paris_rollins.IGNORE_IPV4_NETS
    paris_rollins.IGNORE_IPV4_NETS = ()
    self.assertFalse(paris_rollins.ignore_ip('127.0.0.1'))
    handler = SimpleHTTPServer.SimpleHTTPRequestHandler
    self._server = SocketServer.TCPServer(("", 6666), handler)
    thread.start_new_thread(self._server.serve_forever, ())

  def tearDown(self):
    paris_rollins.IGNORE_IPV4_NETS = self._cached_ignored_nets
    self.assertTrue(paris_rollins.ignore_ip('127.0.0.1'))
    self._server.shutdown()
    self._server.server_close()

  def test_polling(self):
    recent_ip_cache = paris_rollins.RecentIPAddressCache(120)
    watcher = paris_rollins.ConnectionWatcher()
    ucc = watcher.uncached_closed_connections(recent_ip_cache)
    for c in ucc:
      self.assertNotEqual(int(c.local_port), 6666)
      self.assertNotEqual(int(c.remote_port), 6666)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(('127.0.0.1', 6666))
    # Must run the polling loop at least once while the socket is live.
    ucc = watcher.uncached_closed_connections(recent_ip_cache)
    for c in ucc:
      self.assertNotEqual(int(c.local_port), 6666)
      self.assertNotEqual(int(c.remote_port), 6666)
    s.close()
    # Now the closed socket should be discovered.
    ucc = watcher.uncached_closed_connections(recent_ip_cache)
    count = 0
    # Because we are connecting both to and from 127.0.0.1, we have no way of
    # knowing which of the two socket endpoints will appear first in the output
    # of ss. Whichever one appears first will put 127.0.0.1 into the
    # recent_ip_cache, and so we will miss the disappearance of the other.
    # Therefore, we have to count the discovery of a connection with
    # remote_port 6666 and remote_ip 127.0.0.1 as a success and we have to
    # count the discovery of a connection with local_port 6666 and local_ip
    # 127.0.0.1 as a success.
    for c in ucc:
      if int(c.local_port) == 6666 or int(c.remote_port) == 6666:
        count += 1
    self.assertEqual(count, 1)


if __name__ == '__main__':
    unittest.main()

