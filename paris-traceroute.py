#! /usr/bin/python -u

"""
paris-traceroute.py: Poll for newly closed connections and print a traceroute to
the remote address to a log file.
"""

print "Starting paris-traceroute"

from Web100 import *
import os
import subprocess
import sys
import time

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
        mkdirs(logdir)
    logname = time.strftime("%Y/%m/%d/%%s%Y%m%dT%TZ_ALL%%d.paris",
                            time.gmtime(t)) % (server, logc)
    ++logc
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

    process = subprocess.Popen(["paris-traceroute","--algo=exhaustive",rem_address],
                               stdout = subprocess.PIPE)
    logf.write(process.communicate())
    logf.write("\n")
    logf.close()

# Main
if len(sys.argv) == 1:
    server=""
elif len(sys.argv) == 2:
    server=sys.argv[1]+"/"
else:
    print "Usage: %s [server_name]" % sys.argv[0]
    sys.exit()

while True:
    a = Web100Agent()
    closed=[]
    cl = a.all_connections()
    newclosed=[]
    for c in cl:
        try:
            if c.read('State') == 1:
                newclosed.append(c.cid)
                if not c.cid in closed:
                    do_traceroute(c.read("RemAddress"))
        except Exception, e:
            print "Exception:", e
            pass
    closed = newclosed;
    time.sleep(5)

