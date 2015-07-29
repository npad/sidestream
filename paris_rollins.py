#!/usr/bin/python2.6

# Run up to a configurable limit of simultaneous paris-traceroutes, back
# towards recent M-Lab client IP addresses told to us via SideStream.

# TODO(joshb): this script is written to minimize external dependencies.
# Later versions of subprocess include built in timeout handling, but we
# can't use them because the M-Lab platform doesn't have them. This should
# be revisited if the M-Lab platform is upgraded.

# TODO(joshb): this version just provides a function to run paris-traceroute.
# Next step is to use multiprocessing to run multiple traceroutes and poll
# the Web100 agent 

import os
import multiprocessing
import subprocess
import sys
import time

# What binary to use for paris-traceroute
PARIS_TRACEROUTE = '/usr/local/bin/paris-traceroute'
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


def make_log_file_name(log_time, log_file_root, remote_ip, remote_port,
                       local_ip, local_port):
  log_file_relative = (time.strftime('%Y/%m/%d/%Y%m%dT%TZ%%s.paris',
                                     time.gmtime(log_time)) %
                       ('-'.join((remote_ip, str(remote_port),
                                  local_ip, str(local_port)))))
  log_file = os.path.join(log_file_root, log_file_relative)
  return log_file


# Try to run paris-traceroute and log output to a file. We assume any
# errors are transient (Eg, temporarily out of disk space), so do not
# crash if the run fails.
def run_worker(log_file_root, log_time, remote_ip, remote_port,
               local_ip, local_port):
  os.nice(WORKER_NICE)
  command = (
    '/usr/bin/timeout',
    str(WORKER_TIMEOUT) + 's',
    '/usr/local/bin/paris-traceroute',
    '--algo=exhaustive',
    '-picmp',
    remote_ip,
    '-s',
    str(local_port))
  log_command = ' '.join(command)
  log_file_name = make_log_file_name(
    log_time, log_file_root, remote_ip, remote_port, local_ip, local_port)
  log_file_dir = os.path.dirname(log_file_name)
  if not os.path.exists(log_file_dir):
    try:
      os.makedirs(log_file_dir)
    # race with other worker - they created the directory first.
    except OSError:
      pass
  if not os.path.exists(log_file_dir):
    log_worker('cannot create %s' % log_file_dir)
    return
  try:
    log_file = open(log_file_name, 'w')
  except IOError:
    log_worker('cannot open log file %s' % log_file_name)
    return
  log_worker('traceroute to %s' % remote_ip)
  try:
    returncode = subprocess.call(
      command, shell=False, stdout=log_file, stderr=None)
    log_file.close()
    if returncode != 0:
      log_worker('%s returned %d' % (log_command, returncode))
  except OSError:
    log_worker('could not run %s' % log_ommand)
  return
