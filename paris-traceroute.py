#! /usr/bin/python -u

"""
paris-traceroute.py: Poll for newly closed connections and print a traceroute to
the remote address to a log file.
"""

print "Starting paris-traceroute"

from Web100 import *
import errno
import os
import socket
import subprocess
import sys
import time

def mkdirs(name):
    """ Fake mkdir -p """
    try:
      os.makedirs(name)
    except OSError as exc:
      if exc.errno == errno.EEXIST and os.path.isdir(name):
        pass
      else: raise

def postproc(dir):
    """ Remove all write permissions, compute md5sums, etc """
    for f in glob.glob(dir+"*"):
        os.chmod(f, 0444)
    subprocess.call("find . -type f | xargs md5sum > ../manifest.tmp", shell=True, chdir=dir)
    os.rename(dir+"/../manifest.tmp", dir+"/manifest.md5")
    os.chmod(dir+"/manifest.md5", 0555)
    os.chmod(dir, 0555)    # And make it immutable

olddir=""
logc = 0
def getlogf(t):
    global logf, server, logc
    logdir = time.strftime("%Y/%m/%d/", time.gmtime(t))
    if olddir and olddir!=logdir:
        postproc(olddir)
    mkdirs(logdir+server)
    logname = time.strftime("%Y/%m/%d/%%s%Y%m%dT%TZ_ALL%%d.paris",
                            time.gmtime(t)) % (server, logc)
    logc+=1
    return open(logname, "a")

def do_traceroute(rem_address):
    # Ignore connections to loopback and Planet Lab Control (PLC)
    if rem_address == "127.0.0.1":
        return
    if rem_address.startswith("128.112.139"):
        return

    # pick/open a logfile as needed, based on the close poll time
    t = time.time()
    logf = getlogf(t)

    process = subprocess.Popen(["paris-traceroute","-picmp","--algo=exhaustive",rem_address],
                               stdout = subprocess.PIPE)
    (so,se) = process.communicate()
    logf.write(so)
    logf.write("\n")
    logf.close()


CACHE_WINDOW=60*10  # 10 minutes
def ip_is_recent(arg):
    (ip,ts) = arg
    current_ts = time.time()
    if current_ts > ts + CACHE_WINDOW:
        return False
    return True

class RecentList:
    def __init__(self):
        self.iplist=[]

    def clean(self):
        self.iplist = filter(ip_is_recent, self.iplist)

    def add(self, remote_ip):
        self.clean()
        self.iplist.append((remote_ip, time.time()))

    def contain(self, remote_ip):
        self.clean()
        for ip,ts in self.iplist:
            if remote_ip == ip: return True
        return False

def is_valid_ipv4_address(address):
  try:
    socket.inet_pton(socket.AF_INET, address)
  except AttributeError:
    try:
      socket.inet_aton(address)
    except socket.error:
      return False
  except socket.error:
    return False
  return True

def is_valid_ipv6_address(address):
  try:
    socket.inet_pton(socket.AF_INET6, address)
  except AttributeError:
    # This is the case if socket doesn't support IPv6, so it's not strictly
    # accurate to return False, but it is conservative.
    return False
  except socket.error:
    return False
  return True

server=""
def main():
    # Main
    global server
    if len(sys.argv) == 1:
        server=""
    elif len(sys.argv) == 2:
        server=sys.argv[1]+"/"
    else:
        print "Usage: %s [server_name]" % sys.argv[0]
        sys.exit()

    recent_ips = RecentList()

    # Moving "a = Web100Agent()" above "while True" per
    # OTI issue #575: Debug paris-traceroute - salarcon215
    a = Web100Agent()
    while True:
        closed=[]
        cl = a.all_connections()
        newclosed=[]
        for c in cl:
            try:
                if c.read('State') == 1:
                    newclosed.append(c.cid)
                    if not c.cid in closed:
                        rem_ip = c.read("RemAddress")
                        if is_valid_ipv4_address(rem_ip) and not recent_ips.contain(rem_ip):
                            print "Running trace to: %s" % rem_ip
                            do_traceroute(rem_ip)
                            recent_ips.add(rem_ip)
                        #else:
                        #    print "Skipping: %s" % rem_ip
            except Exception, e:
                print "Exception:", e
                pass
        closed = newclosed;
        time.sleep(5)

if __name__ == "__main__":
    main()
