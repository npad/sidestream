#!/usr/bin/python2.6

# Run up to a configurable limit of simultaneous paris-traceroutes, back
# towards recent M-Lab client IP addresses told to us via SideStream.

# TODO(joshb): this script is written to minimize external dependencies.
# Later versions of subprocess include built in timeout handling, but we
# can't use them because the M-Lab platform doesn't have them. This should
# be revisited if the M-Lab platform is upgraded.

# TODO(joshb): this version just provides functions to run paris-traceroute,
# and manage a cache of recent IP addresses. Next step is to poll Web100 agent.

import os
import multiprocessing
import subprocess
import sys
import time

# What binary to use for paris-traceroute
PARIS_TRACEROUTE_BIN = '/usr/local/bin/paris-traceroute'
# What binary to use for timeout (see comment about python/dependencies, above)
TIMEOUT_BIN = '/usr/bin/timeout'
# paris-traceroute is run at this nice level, to minimize impact on the host.
WORKER_NICE = 19
# paris-traceroute should take no longer than this to complete (timed out,
# partial results will be discarded).
WORKER_TIMEOUT = 20 
# Maximum number of paris-traceoutes to run simultaneously (requests to run
# more will be discarded).
MAX_WORKERS = 10


def log_worker(message):
  print time.strftime('%Y%m%d %T %%s', time.gmtime(time.time())) % message


def make_log_file_name(log_file_root, log_time,
                       remote_ip, remote_port, local_ip, local_port):
  log_time = time.strftime('%Y/%m/%d/%Y%m%dT%TZ', time.gmtime(log_time))
  log_ip = '-'.join((remote_ip, str(remote_port), local_ip, str(local_port)))
  log_file_relative = ''.join((log_time, log_ip, '.paris'))
  log_file = os.path.join(log_file_root, log_file_relative)
  return log_file


# Try to run paris-traceroute and log output to a file. We assume any
# errors are transient (Eg, temporarily out of disk space), so do not
# crash if the run fails.
def run_worker(log_file_root, log_time,
               remote_ip, remote_port, local_ip, local_port):
  os.nice(WORKER_NICE)
  command = (
    TIMEOUT_BIN,
    str(WORKER_TIMEOUT) + 's',
    PARIS_TRACEROUTE_BIN,
    '--algo=exhaustive',
    '-picmp',
    '-s',
    str(local_port),
    '-d',
    str(remote_port),
    remote_ip)
  log_command = ' '.join(command)
  log_worker(log_command)
  log_file_name = make_log_file_name(
    log_file_root, log_time, remote_ip, remote_port, local_ip, local_port)
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
  def expire(self, now_bucket):
    expire_buckets = [] 
    for bucket in self.address_cache_time_buckets.keys():
      if bucket < now_bucket - 1:
        expire_buckets.append(bucket)
    for bucket in expire_buckets:
      for address in self.address_cache_time_buckets[bucket]:
        del self.address_cache[address]
      del self.address_cache_time_buckets[bucket]

  # Returns true if an address seen without one timeout period.
  def isrecent(self, address):
    now = time.time()
    now_bucket = now % self.cache_timeout
    expired_age = now - self.cache_timeout
    self.expire(now_bucket)
    # If in the cache...
    if address in self.address_cache:
      age = self.address_cache[address]
      if age > expired_age:
        return True
      else:
        # Stale entry, we need to refresh.
        stale_bucket = age % self.cache_timeout
        self.address_cache_time_buckets[stale_bucket].remove(address)
    # Not in the cache or stale entry, so add a new entry.
    self.address_cache[address] = now
    if now_bucket not in self.address_cache_time_buckets:
      self.address_cache_time_buckets[now_bucket] = set()  
    self.address_cache_time_buckets[now_bucket].add(address)
    return False


# Manage a pool of worker subprocessors to run traceoutes in.
class ParisTraceroutePool(object):

  def __init__(self, log_file_root):
    self.pool = multiprocessing.Pool(processes=MAX_WORKERS)
    self.log_file_root = log_file_root
    self.busy = []

  # Return true if we have capacity to run more traceroutes.
  def free(self):
    self.busy = [result for result in self.busy if result.ready() == False]
    return len(self.busy) < MAX_WORKERS

  # Return true if we have spare capacity and we scheduled a traceroute.
  def run_async(self, log_time, remote_ip, remote_port, local_ip, local_port):
    if self.free():
      self.busy.append(self.pool.apply_async(run_worker,
        args=(self.log_file_root, log_time,
              remote_ip, remote_port, local_ip, local_port)))
      return True
    return False
