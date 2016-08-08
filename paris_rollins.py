#!/usr/bin/python2.6

# Run up to a configurable limit of simultaneous paris-traceroutes, back

# towards recent M-Lab client IP addresses told to us via SideStream.

# TODO(joshb): this script is written to minimize external dependencies.
# Later versions of subprocess include built in timeout handling, but we
# can't use them because the M-Lab platform doesn't have them. This should
# be revisited if the M-Lab platform is upgraded.

# Needs to be run as root in the NPAD slice.
#
#   export PYTHONPATH=/home/iupui_npad/build/lib/python2.6/site-packages ; \
#   export LD_LIBRARY_PATH=/home/iupui_npad/build/lib ; \
#   ./paris_rollins.py
#
# TODO(joshb): this is for experimental use only. The next step is to replace
# the old wrapper with this one.

import commands
import collections
import multiprocessing
import optparse
import os
import re
import subprocess
import sys
import time

import platform

# What binary to use for paris-traceroute
PARIS_TRACEROUTE_BIN = '/usr/local/bin/paris-traceroute'
# What binary to use for timeout (see comment about python/dependencies, above)
TIMEOUT_BIN = '/usr/bin/timeout'
# paris-traceroute is run at this nice level, to minimize impact on the host.
WORKER_NICE = 19
# paris-traceroute should take no longer than this to complete (timed out,
# partial results will be discarded).
WORKER_TIMEOUT = 60 
# Maximum number of paris-traceoutes to run simultaneously (requests to run
# more will be discarded).
MAX_WORKERS = 10
# Base source port to use when running traceroute
PARIS_TRACEROUTE_SOURCE_PORT_BASE = 33457
# Do not traceroute to an IP more than once in this many seconds
IP_CACHE_TIME_SECONDS = 120
# Don't traceroute to these networks.
# TODO(joshb): would be nice to use IP address library, but it isn't installed
# on M-Lab.
IGNORE_IPV4_NETS = (
  '127.', # localhost
  '128.112.139.', # PLC control
)
# The string that indicates a port is closed according to the output of ss
SS_CLOSED = 'CLOSE-WAIT'

optparser = optparse.OptionParser()
optparser.add_option('-l', '--logpath', default='/tmp', help='directory to log to')


def log_worker(message):
  print time.strftime('%Y%m%d %T %%s', time.gmtime(time.time())) % message


def make_log_file_name(log_file_root, log_time, mlab_hostname,
                       remote_ip, remote_port, local_ip, local_port):
  time_fmt = os.path.join('%Y', '%m', '%d', mlab_hostname, '%Y%m%dT%TZ')
  log_time = time.strftime(time_fmt, time.gmtime(log_time))
  log_ip = '-'.join((remote_ip, str(remote_port), local_ip, str(local_port)))
  log_file_relative = ''.join((log_time, '-', log_ip, '.paris'))
  log_file = os.path.join(log_file_root, log_file_relative)
  return log_file


# Try to run paris-traceroute and log output to a file. We assume any
# errors are transient (Eg, temporarily out of disk space), so do not
# crash if the run fails.
def run_worker(log_file_root, log_time, mlab_hostname, traceroute_port,
               remote_ip, remote_port, local_ip, local_port):
  os.nice(WORKER_NICE)
  command = (
    TIMEOUT_BIN,
    str(WORKER_TIMEOUT) + 's',
    PARIS_TRACEROUTE_BIN,
    '--algo=exhaustive',
    '-picmp',
    '-s',
    str(traceroute_port),
    '-d',
    str(remote_port),
    remote_ip)
  log_command = ' '.join(command)
  log_worker(log_command)
  log_file_name = make_log_file_name(
    log_file_root, log_time, mlab_hostname,
    remote_ip, remote_port, local_ip, local_port)
  log_file_dir = os.path.dirname(log_file_name)
  if not os.path.exists(log_file_dir):
    try:
      os.makedirs(log_file_dir)
    # race with other worker - they created the directory first.
    except OSError:
      pass
  if not os.path.exists(log_file_dir):
    log_worker('cannot create %s' % log_file_dir)
    return False
  try:
    log_file = open(log_file_name, 'w')
  except IOError:
    log_worker('cannot open log file %s' % log_file_name)
    return False
  try:
    returncode = subprocess.call(command, stdout=log_file)
    log_file.close()
    if returncode != 0:
      log_worker('%s returned %d' % (log_command, returncode))
      return False
  except OSError:
    log_worker('could not run %s' % log_command)
    return False
  return True


# Test if an IP address has been seen within the timeout period.
class RecentIPAddressCache(object):

  def __init__(self, cache_timeout):
    self.cache_timeout = cache_timeout
    self.address_cache = {}
    self.address_cache_time_buckets = {}

  # Expire all addresses up to 2 cache timeout periods ago.
  def expire(self, now):
    expire_buckets = []
    for bucket in self.address_cache_time_buckets.keys():
      if bucket + self.cache_timeout < now:
        expire_buckets.append(bucket)
    for bucket in expire_buckets:
      for address in self.address_cache_time_buckets[bucket]:
        del self.address_cache[address]
      del self.address_cache_time_buckets[bucket]

  # Add an IP to the cache, if it isn't there already.
  def add(self, address):
    if not self.cached(address):
      # Not in the cache or stale entry, so add a new entry.
      now = time.time()
      self.address_cache[address] = now
      if now not in self.address_cache_time_buckets:
        self.address_cache_time_buckets[now] = set()
        self.address_cache_time_buckets[now].add(address)

  # Returns true if an address seen without one timeout period.
  def cached(self, address):
    now = time.time()
    self.expire(now)
    return address in self.address_cache


# Manage a pool of worker subprocessors to run traceoutes in.
class ParisTraceroutePool(object):

  def __init__(self, log_file_root):
    self.pool = multiprocessing.Pool(processes=MAX_WORKERS)
    self.log_file_root = log_file_root
    self.busy = []

  def busy_workers_count(self):
    self.busy = [result for result in self.busy if not result.ready()]
    return len(self.busy)

  # Return true if we have capacity to run more traceroutes.
  def free(self):
    return self.busy_workers_count() < MAX_WORKERS

  # Return true if no workers running.
  def idle(self):
    return self.busy_workers_count() == 0 

  # Return true if we have spare capacity and we scheduled a traceroute.
  def run_async(self, log_time, mlab_hostname, traceroute_port,
                remote_ip, remote_port, local_ip, local_port):
    if self.free():
      self.busy.append(self.pool.apply_async(run_worker,
        args=(self.log_file_root, log_time, mlab_hostname, traceroute_port,
              remote_ip, remote_port, local_ip, local_port)))
      return True
    return False


# return true if should ignore an IP address (eg localhost).
def ignore_ip(ip):
  for net in IGNORE_IPV4_NETS:
    if ip.startswith(net):
      return True
  return False


# Return short version (mlabN.xyzNN) of hostname, if an M-Lab host.
# Otherwise return just hostname.
def get_mlab_hostname():
   hostname = platform.node()
   mlab_match = re.match('^(mlab\d+\.[a-z]{3}\d+)', hostname) 
   if mlab_match:
     return mlab_match.group(1)
   return hostname


# A struct to hold all the data about a connection
Connection = collections.namedtuple('Connection', ['remote_ip', 'remote_port',
                                                   'local_ip', 'local_port'])

def parse_ss_line(line, connections):
  # Parse a single line of the output of ss and put the result in connections.
  # Line looks like:
  #  ESTAB 0 0 127.0.0.1:9557 127.0.0.1:40171
  # or maybe
  #  CLOSE-WAIT 1 0 2620:0:1003:413:ad1b:7f2:9992:63b2:33855 2607:f8b0:4006:808::2001:443
  # where the fields are separated by tabs or other whitespace
  fields = line.split()
  if len(fields) != 5:
    log_worker('bad line: %s' % line)
    return
  state, _, _, local_ip_port, remote_ip_port = fields
  local_ip_fields = local_ip_port.rsplit(':', 1)
  if len(local_ip_fields) != 2:
    log_worker('bad local_ip:port string: %s' % local_ip_port)
    return
  local_ip, local_port = local_ip_fields
  remote_ip_fields = remote_ip_port.rsplit(':', 1)
  if len(remote_ip_fields) != 2:
    log_worker('bad remote_ip:port string: %s' % remote_ip_port)
  remote_ip, remote_port = remote_ip_fields
  connections[Connection(remote_ip, remote_port, local_ip, local_port)] = state


def measure_connections():
  command = 'ss --tcp --numeric'
  status, connection_text = commands.getstatusoutput(command)
  if status != 0:
    log_worker('%s failed (return code %d)' % (command, status))
    return {}
  lines = connection_text.splitlines()
  if len(lines) <= 1:
    return {}
  connections = {}
  # Parse each line, skipping the first line which is column headers
  for line in lines[1:]:
    parse_ss_line(line, connections)
  return connections


def is_IPv4(s):
  fields = s.split('.')
  if len(fields) != 4:
    return False
  for f in fields:
    if not f.isdigit():
      return False
  return True


class ConnectionWatcher(object):
  def __init__(self):
    self._connections = measure_connections()

  def get_closed_connections(self):
    # Find the connections that have been closed since the last query or are
    # still marked as closed
    old_connections = self._connections
    self._connections = measure_connections()
    closed = []
    # a connection is closed if its status is SS_CLOSED or it isn't present
    for conn in old_connections:
      if conn not in self._connections:
        closed.append(conn)
    for conn, status in self._connections.iteritems():
      if status == SS_CLOSED:
        closed.append(conn)
    return closed

  def uncached_closed_connections(self, recent_ip_cache):
    # return list of recently closed connections, not already seen.
    # Filter out IPv6 addresses (TODO: support IPv6)
    # Filter out cached addresses and update the cache
    filtered = []
    for conn in self.get_closed_connections():
      if (is_IPv4(conn.remote_ip) and
          is_IPv4(conn.local_ip) and
          not ignore_ip(conn.remote_ip) and
          not recent_ip_cache.cached(conn.remote_ip)):
        recent_ip_cache.add(conn.remote_ip)
        filtered.append(conn)
    return filtered


if __name__ == '__main__':
    (options, args) = optparser.parse_args()
    mlab_hostname = get_mlab_hostname()
    recent_ip_cache = RecentIPAddressCache(IP_CACHE_TIME_SECONDS)
    pool = ParisTraceroutePool(options.logpath)
    agent = ConnectionWatcher()

    while True:
      log_time = time.time()
      connections = agent.uncached_closed_connections(recent_ip_cache)
      for remote_ip, remote_port, local_ip, local_port in connections:
          traceroute_port = PARIS_TRACEROUTE_SOURCE_PORT_BASE + pool.busy_workers_count()
          pool.run_async(log_time, mlab_hostname, traceroute_port,
                         remote_ip, remote_port, local_ip, local_port)
      time.sleep(5)
