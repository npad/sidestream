#! /usr/bin/python -u

"""
exitstats.py: Poll for newly closed connections and print their Web100
stats.
"""

import os
import re
import sys
import time

from collections import namedtuple

import prometheus_client as prom

try:
  from Web100 import *
except ImportError:
  print 'Error importing web100'

PROMETHEUS_SERVER_PORT = 9090
connection_count = prom.Counter('sidestream_connection_count',
                                'Count of connections logged',
                                ['type', 'lsb'])
exception_count = prom.Counter('sidestream_exception_count',
                               'Count of exceptions.',
                               ['type'])

class Web100StatsWriter:
    ''' TODO - add documentation.
    '''
    def __init__(self, server_name):
        self.server = server_name
        self.active_vars = None
        self.closeLogs()

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

    active_vars = None
    server = ""
    one_hour = (60*60)
    LogInfo = namedtuple('LogInfo', ['name', 'f'])

    # Map from IP address to LogInfo
    # May include key=None if we are not using per IP logs.
    logs = {}
    log_time = -1

    def setkey(self, snap):
        """
        Select the variables to be saved.   By default this is the same as
        stdvars above, however since the actual variables present in the kernel
        can be altered by build parameters etc, we audit the std list against
        the actual kernel list.

        Keys in stdvars will be logged in consistent order.  Any new keys will
        be logged in the order they appear in the snapshot, after all the standard
        keys.

        The keys will usually be same from data set to data set, but this
        is not guaranteed.
        """
        self.active_vars=[]
        s=snap.copy()
        for k in self.stdvars:
            if k in s:
                self.active_vars.append(k)
                del s[k]
        for k in s:
            self.active_vars.append(k)

    def logHeader(self, f):
        f.write("K: cid PollTime")
        for k in self.active_vars:
          f.write(" "+k)
        f.write("\n")

    def mkdirs(self, name):
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

    def closeLogs(self):
        ''' Close all log files, e.g. at the top of each hour.
        '''
        for k, v in self.logs.items():
            if v.f: v.f.close()
        self.logs.clear()

    def useLocalIP(self):
        ''' Interpret local environment variable to determine whether to use
            local IP address.
        '''
        env_var = os.environ.get('SIDESTREAM_USE_LOCAL_IP')
        return env_var == 'True' or env_var == 'true' or env_var == '1'

    def logName(self, local_time, local_ip):
        ''' Form directory name and file name for log file.
        '''
        gm = time.gmtime(local_time)
        logdir= time.strftime("%Y/%m/%d/", gm) + self.server
        ts = time.strftime("%Y%m%dT%TZ", gm)
        if local_ip != None:
          return logdir, "%s_%s_%d.web100"%(ts , local_ip, 0)
        else:
          return logdir, "%s_ALL%d.web100"%(ts ,0)

    def openLogFile(self, logdir, logname):
        self.mkdirs(logdir)
        print "Opening:", logdir+logname
        logf = open(logdir+logname, "a")
        self.logHeader(logf)
        # Add the entry to the logs dict.
        return logf

    def getLogFile(self, local_time, local_ip=None):
        ''' getLogFile returns the appropriate logFile for the current time
            and local_ip address.
            If os.environment["SIDESTREAM_USE_LOCAL_IP"] is true, then it
            uses separate files for each local IP address.
        '''
        hour_time = int(local_time / self.one_hour) * self.one_hour

        # Every hour, we close all the log files and start new ones.
        if hour_time > self.log_time:
            print('Closing all log files')
            self.closeLogs()
            self.log_time = hour_time

        use_local = self.useLocalIP()  # Is this a speed concern?
        local_ip = local_ip if self.useLocalIP() else None
        if local_ip in self.logs:
            return self.logs[local_ip].f
        else:
            logdir, logname = self.logName(hour_time, local_ip)
            logf = self.openLogFile(logdir, logname)
            self.logs[local_ip] = self.LogInfo(logdir+logname, logf)
            return logf


    def ipLastSixBits(self, local):
        ''' Parse the last six bits of an IP address into a decimal string.
        '''
        if ':' in local:
            ipv6 = re.match('[0-9A-Fa-f].*:([0-9A-Fa-f]{1,4})$', local)
            if ipv6 == None:
                print 'ipv6 address failed to match pattern: ' + local
                exception_count.labels('ipv6 parse error').inc()
                return 'unparsed'
            else:
                return '{0}'.format(int(ipv6.group(1),16) % 64)
        else:
            ipv4 = re.match('[0-9].*\.([0-9]{1,3})$', local)
            if ipv4 == None:
                print 'ipv4 address failed to match pattern: ' + local
                exception_count.labels('ipv4 parse error').inc()
                return 'unparsed'
            else:
                return '{0}'.format(int(ipv4.group(1),16) % 64)

    def connectionType(self, remote):
        if remote == '127.0.0.1':
            return 'loopback-ipv4'
        elif re.match('ffff:7f00.*', remote, re.I) != None:  # ignore case
            return 'loopback-ipv6'
        elif remote.startswith("128.112.139"):
            # TODO - do we have ipv6 addresses for PLC?
            return 'plc'

        if ':' in remote:
            return 'ipv6'
        else:
            return 'ipv4'

    def logConnection(self, c):
        snap = c.readall()
        if not self.active_vars:
            self.setkey(snap)

        # Update connection count.  Use the least significant bits
        # of the local address to distinguish slices.
        lsb = self.ipLastSixBits(snap["LocalAddress"])
        conn_type = self.connectionType(snap["RemAddress"])
        connection_count.labels(conn_type, lsb).inc()

        # If it isn't loopback or plc, then log it.
        if conn_type.startswith('ipv'):
            # pick/open a logfile as needed, based on the close poll time
            t = time.time()
            logf = self.getLogFile(t, snap["LocalAddress"])
            logf.write("C: %d %s"%
                       (c.cid, time.strftime("%Y-%m-%d-%H:%M:%SZ",
                                             time.gmtime(t))))
            for v in self.active_vars:
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
        print "Usage: %s [server_name]"%argv[0]
        return 0

    # Start prometheus server to export metrics.
    prom.start_http_server(PROMETHEUS_SERVER_PORT)

    stats_writer = Web100StatsWriter(server)

    agent = Web100Agent()
    closed = []
    while True:
        conns = agent.all_connections()
        newclosed = []
        for c in conns:
            try:
                if c.read('State') == 1:
                    newclosed.append(c.cid)
                    if not c.cid in closed:
                        stats_writer.logConnection(c)
            except Exception, e:
                # We should handle all exceptions deeper in the call stack.
                # We instrument this so that we can detect exceptions and
                # track them down.
                exception_count.labels('Exception').inc()
                print e
                pass
        closed = newclosed;
        # Wait 5 seconds before running polling again.
        time.sleep(5)

if __name__ == "__main__":
    sys.exit(main(sys.argv))
