#! /usr/bin/python -u

"""
exitstats.py: Poll for newly closed connections and print their Web100
stats.
"""

print "Starting exitstats"

import time
import sys
import os

try:
  from Web100 import *
except ImportError:
  print "Error importing web100"

stdvars=[
"LocalAddress", "LocalPort", "RemAddress", "RemPort", "State", "SACKEnabled",
"TimestampsEnabled", "NagleEnabled", "ECNEnabled", "SndWinScale",
"RcvWinScale", "ActiveOpen", "MSSRcvd", "WinScaleRcvd", "WinScaleSent",
"PktsOut", "DataPktsOut", "DataBytesOut", "PktsIn", "DataPktsIn",
"DataBytesIn", "SndUna", "SndNxt", "SndMax", "ThruBytesAcked", "SndISS",
"RcvNxt", "ThruBytesReceived", "RecvISS", "StartTimeSec", "StartTimeUsec",
"Duration", "SndLimTransSender", "SndLimBytesSender", "SndLimTimeSender",
"SndLimTransCwnd", "SndLimBytesCwnd", "SndLimTimeCwnd", "SndLimTransRwin",
"SndLimBytesRwin", "SndLimTimeRwin", "SlowStart", "CongAvoid",
"CongestionSignals", "OtherReductions", "X_OtherReductionsCV",
"X_OtherReductionsCM", "CongestionOverCount", "CurCwnd", "MaxCwnd",
"CurSsthresh", "LimCwnd", "MaxSsthresh", "MinSsthresh", "FastRetran",
"Timeouts", "SubsequentTimeouts", "CurTimeoutCount", "AbruptTimeouts",
"PktsRetrans", "BytesRetrans", "DupAcksIn", "SACKsRcvd", "SACKBlocksRcvd",
"PreCongSumCwnd", "PreCongSumRTT", "PostCongSumRTT", "PostCongCountRTT",
"ECERcvd", "SendStall", "QuenchRcvd", "RetranThresh", "NonRecovDA",
"AckAfterFR", "DSACKDups", "SampleRTT", "SmoothedRTT", "RTTVar", "MaxRTT",
"MinRTT", "SumRTT", "CountRTT", "CurRTO", "MaxRTO", "MinRTO", "CurMSS",
"MaxMSS", "MinMSS", "X_Sndbuf", "X_Rcvbuf", "CurRetxQueue", "MaxRetxQueue",
"CurAppWQueue", "MaxAppWQueue", "CurRwinSent", "MaxRwinSent", "MinRwinSent",
"LimRwin", "DupAcksOut", "CurReasmQueue", "MaxReasmQueue", "CurAppRQueue",
"MaxAppRQueue", "X_rcv_ssthresh", "X_wnd_clamp", "X_dbg1", "X_dbg2", "X_dbg3",
"X_dbg4", "CurRwinRcvd", "MaxRwinRcvd", "MinRwinRcvd", "LocalAddressType",
"X_RcvRTT", "WAD_IFQ", "WAD_MaxBurst", "WAD_MaxSsthresh", "WAD_NoAI",
"WAD_CwndAdjust"
]

active_vars=None
def setkey(snap):
  """
  Select the variables to be saved.   By default this is the same as
  stdvars above, however since the actual variables present in the kernel
  can be altered by build parameters etc, we audit the std list against
  the actual kernel list.
  
  Thus the keys will usually be same from data set to data set, but this
  is not guaranteed.
  """
  global active_vars, stdvars
  active_vars=[]
  s=snap.copy()
  for k in stdvars:
    if k in s:
      active_vars.append(k)
      del s[k]
#   else:
#     print "Standard variable %s omited"%k
  for k in s:
#   print "Non-std variable found:", k
    active_vars.append(k)

def showkey(f):
  global active_vars
  f.write("K: cid PollTime")
  for k in active_vars:
    f.write(" "+k)
  f.write("\n")

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
      if e[0] != 17:   # ignore "exists"
        raise e

def postproc(dir):
    """
    Remove all write permissions, compute md5sums, etc
    """
    for f in glob.glob(dir+"*"):
        os.chmod(f, 0444)
    subprocess.call("find . -type f | xargs md5sum > ../manifest.tmp", shell=True, chdir=dir)
    os.rename(dir+"/../manifest.tmp", dir+"/manifest.md5")
    os.chmod(dir+"/manifest.md5", 0555)
    os.chmod(dir, 0555)    # And make it immutable 

logtime=(60*60)
logf=None
olt = -1
olddir=""
def getlogf(t):
  global olt, logtime, logf, server
  lt = int(t / logtime)*logtime
  if lt != olt:
    olt=lt
    if logf: logf.close()
    logdir=time.strftime("%Y/%m/%d/", time.gmtime(lt))
    if olddir and olddir!=logdir:
      postproc(olddir)
    mkdirs(logdir)
    logname=time.strftime("%Y/%m/%d/%%s%Y%m%dT%TZ_ALL%%d.web100", time.gmtime(lt))%(server, 0)
    print "Opening:", logname
    logf=open(logname, "a")
    showkey(logf)
  return logf

def showconn(c):
  global active_vars
  snap = c.readall()
  if not active_vars:
    setkey(snap)
  # Ignore connections to loopback and Planet Lab Control (PLC)
  if snap["RemAddress"] == "127.0.0.1":
    return
  if snap["RemAddress"].startswith("128.112.139"):
    return

  # pick/open a logfile as needed, based on the close poll time
  t = time.time()
  logf=getlogf(t, snap)
  logf.write("C: %d %s"%(c.cid, time.strftime("%Y-%m-%d-%H:%M:%SZ", time.gmtime(t))))
  for v in active_vars:
    logf.write(" "+str(snap[v]))
  logf.write("\n")
  logf.flush()


# Main

def main(argv):
  print "Starting exitstats"

  if len(argv) == 1:
    server = ""
  elif len(argv) == 2:
    server = argv[1]+"/"
  else:
    print "Usage: %s [server_name]"%sys.argv[0]
    sys.exit()

  a = Web100Agent()
  closed = []
  while True:
    cl = a.all_connections()
    newclosed = []
    for c in cl:
      try:
        if c.read('State') == 1:
          newclosed.append(c.cid)
          if not c.cid in closed:
            showconn(c)
      except Exception, e:
#       print "Exception:", e
        pass
    closed=newclosed;
    time.sleep(5)

if __name__ == "__main__":
    sys.exit(main(sys.argv))
