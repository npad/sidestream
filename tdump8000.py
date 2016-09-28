#! /usr/bin/python -u

"""
tcpdump.py: tcpdump all connections to port 8000, in 1 hour increments.
"""

import os
import sys
import exceptions
import time
import threading
import signal

logtime=(60*60)  # One hour long files
pretime=50  # Start 50 second before the hour
posttime=10  # End 10 seconds after the hour

logf=None
olt = -1

def mkdirs(name):
  """ Fake mkdir -p """
  cp=0
  while True:
    cp=name.find("/",cp+1)
    if cp < 0:
      return
    dirname=name[0:cp]
    try:
      os.mkdir(dirname)
    except OSError, e:
      if e[0] != 17:
        raise e

def capture(when):
  """
  Get a tcpdump starting just before time when through to
  when+logtime+postime.   It should be called at time when-pretime.
  The dumpfile is named per time when (the nominal start time).

  """
  global running, running_tc
  nodup=0
  # get a new logfile
  while True:
    fname=time.strftime("%Y/%m/%d/%%s%Y%m%dT%TZ_ALL%%d.tra", time.gmtime(when))%(server, nodup)
    if not os.path.exists(fname):
      break
    nodup=nodup+1

  pid = os.fork()
  if pid:
    # parent schedules the kill timer
    running_tc.acquire()
    running.append((pid, when+logtime+posttime))
    running_tc.notifyAll()
    running_tc.release()
  else:
    # Child launches tcpdump
    mkdirs(fname)
    args = [ "/usr/sbin/tcpdump", "-i", "eth0", "-p", "-w", fname, "port", "8000"]
    print "Pid %d Writing: %s"%(os.getpid(), fname)
    os.execve(args[0], args, os.environ)

def dienow():
  """
  Gun down any running tcpdumps.

  Ignore all errors.

  Don't worry about locks.

  and then we die.

  """
  global running_tc
  print "Die now..."
  for (p, t) in running[:]:
    try:
      os.kill(p, signal.SIGINT)
    except:
      pass
  sys.exit(0)  # nuke all other threads

def reaper():
  """
  Kill all old tcpdumps using a minimal calendar scheduler.
  """
  global running, running_tc
  try:
    running_tc.acquire()
    while True:
      now=time.time()
      nk=now+600 # default when nothing to kill
      for (p, t) in running[:]:
        if now >= t:
          print "Killing pid %d"%p
          os.kill(p, signal.SIGINT)
          try: # discard all statuses
            os.wait()
          except:
            pass
          running.remove((p, t))
        elif nk > t:
          nk = t
      running_tc.wait(nk-now)
  except:
    dienow()

def spawner():
  """
  Start a new tcpdump file pretime before the top of the hour.
  """
  capture(int(time.time()/logtime)*logtime)
  while True:
    now=time.time()
    nextt=int((now+logtime)/logtime)*logtime
    if nextt-2*pretime <= now:
      nextt = nextt+logtime
    time.sleep(nextt-pretime-now)
    capture(nextt)

# main
if len(sys.argv) == 1:
  server=""
elif len(sys.argv) == 2:
  server=sys.argv[1]+"/"
else:
  print "Usage: %s [server_name]"%sys.argv[0]
  sys.exit()

running = []
running_tc = threading.Condition()
threading.Thread(target=reaper).start()
# threading.Thread(target=spawner).start()
try:
  signal.signal(signal.SIGINT ,dienow)
  signal.signal(signal.SIGTERM ,dienow)
  spawner()
except:
  dienow()

