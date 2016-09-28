#!/usr/bin/python2.6

# Run up to a configurable limit of simultaneous paris-traceroutes, back

# towards recent M-Lab client IP addresses told to us via SideStream.

# TODO(joshb): this script is written to minimize external dependencies.
# Later versions of subprocess include built in timeout handling, but we
# can't use them because the M-Lab platform doesn't have them. This should
# be revisited if the M-Lab platform is upgraded.

# Needs to be run as root, with the Web100 libraries installed, in the NPAD
# slice.
#
#   export PYTHONPATH=/home/iupui_npad/build/lib/python2.6/site-packages ; \
#   export LD_LIBRARY_PATH=/home/iupui_npad/build/lib ; \
#   ./paris_rollins.py
#
# TODO(joshb): this is for experimental use only. The next step is to replace
# the old wrapper with this one.

import multiprocessing
import optparse
import os
import re
import subprocess
import sys
import time

import platform
import Web100

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
# Whether a TCP connection is closed.
WEB100_STATE_CLOSED = 1
# Whether a TCP connection was over IPv4
WEB100_IPV4 = 1
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


# return list of recently closed connections, not already seen.
def uncached_closed_connections(agent, recent_ip_cache):
   closed_connections = []
   for connection in agent.all_connections():
     try:
       state = connection.read('State')
       remote_ip = connection.read('RemAddress')
       remote_port = connection.read('RemPort')
       local_ip = connection.read('LocalAddress')
       local_port = connection.read('LocalPort')
       address_type = connection.read('LocalAddressType')
     except Web100.error:
       continue

     if (state == WEB100_STATE_CLOSED and
         address_type == WEB100_IPV4 and
         not ignore_ip(remote_ip) and
         not recent_ip_cache.cached(remote_ip)):
       recent_ip_cache.add(remote_ip)
       log_time = time.time()
       closed_connections.append((
           log_time, remote_ip, remote_port, local_ip, local_port))
   return closed_connections


# Return short version (mlabN.xyzNN) of hostname, if an M-Lab host.
# Otherwise return just hostname.
def get_mlab_hostname():
   hostname = platform.node()
   mlab_match = re.match('^(mlab\d+\.[a-z]{3}\d+)', hostname)
   if mlab_match:
     return mlab_match.group(1)
   return hostname


if __name__ == '__main__':
    (options, args) = optparser.parse_args()
    mlab_hostname = get_mlab_hostname()
    recent_ip_cache = RecentIPAddressCache(IP_CACHE_TIME_SECONDS)
    pool = ParisTraceroutePool(options.logpath)
    agent = Web100.Web100Agent()

    while True:
      connections = uncached_closed_connections(agent, recent_ip_cache)
      for log_time, remote_ip, remote_port, local_ip, local_port in connections:
          traceroute_port = PARIS_TRACEROUTE_SOURCE_PORT_BASE + pool.busy_workers_count()
          pool.run_async(log_time, mlab_hostname, traceroute_port,
                         remote_ip, remote_port, local_ip, local_port)
      time.sleep(5)
