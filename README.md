SideStream  [![Test Status](https://travis-ci.org/gfr10598/sidestream.svg?branch=master)](https://travis-ci.org/gfr10598/sidestream.svg?branch=master) [![Coverage Status](https://coveralls.io/repos/github/gfr10598/sidestream/badge.svg?branch=master)](https://coveralls.io/github/gfr10598/sidestream?branch=master)
==========

Description of how SideStream works and the data that collects.

1) Experiment components

The SideStream experiment consists of 3 components:
  * A standard webserver with sample data,
  * A daemon collecting Web100 exit statistics, and
  * A daemon collecting raw TCP packet traces (tcpdump).
These components are running in the same M-Lab/Planetlab slice as NPAD, and indeed, NPAD shares the same webserver for
its own use.

In addition, two other classes of components are envisioned:
  * External clients to pull emulated application data from the web servers and 
  * External analysis tools to extract useful statistics from the raw TCP instrumentation. 
Note that the external components do not have to be uniform or even coordinated. In principle multiple pools of external
clients could use the same M-Lab components in conjunction with multiple sets of analysis tools to implement slightly
different experiments, all under the SideStream umbrella experiment.

1.1) Software details

NPAD is running a fairly standard Apache configuration on port 8000. The webserver is used to load the NPAD diagnostic
server form, applet and final reports. 

To facilitate the SideStream experiment, each NPAD server includes a directory of synthetic data /Sample/, which can be
listed. In the sample data each file is named by its size, with an appropriate extension for its type. Currently the
only data is (highly compressible, repeating) .txt files in powers of 2 file sizes from 512 Bytes to 1 MByte. Note that
the actual http transfers will be slightly larger than the file sizes due to http overhead, etc.

If there is web caching some place in the user's access network it can be stifled by adding arguments to the client
request. E.g. 
http://npad.iupui.mlab4.nuq01.measurement-lab.org:8000/Sample/1048576.tx...

2) Collected data 

2.1) Web100 stats

Web100 exit statistics are saved by the daemons into ascii files named:
`SideStream/yyyy/mm/dd/nodename/iso_timeZ_ALL0.web100`
  * `ALL` indicates that this is aggregate data across all clients.
  * The `0` might be another small integer to guarantee that the names are unique, for example if the data collection is
    restarted.
Each file contains all the data collected in 1 hour.

There are two types of records.
  * Data keys start out with: `K: cid PollTime LocalAddress LocalPort RemAddress RemPort ....` These specify the format
    for the following data:
    * The `cid` is the connection id: a pid-like identifier unique to each connection for its duration.
    * The `PollTime` is the ISO timestamp when the connection was observed to already be closed (may be up to 5 seconds
      after the actual close).
    * `LocalAddress`, `LocalPort`, `RemAddress`, `RemPort` are the TCP 4-tuple that uniquely identifies the connection.
    * The rest of the line names all Web100 raw instruments. As of 25 Aug 2009, the keys are nominally deterministic, 
      however this property should not be assumed. The format may change in the future, and the keys are different and
      non-deterministic for older data.
  * Records for exit (close) statistics start with `C:` and are in the format suggested by the most recent preceding
    K: record.
In the future we might add other record types, for example "progress" statistics for long running connections. Note that
in all cases these are only summary statistics: total bytes, packets, retransmissions, etc. 

The connection 4-tuple itself is the only evenly remotely sensitive piece of data. (Although it has been shown in some
contexts other parameters, such as transfer length, can sometimes uniquely identify content).

Since web100 does not use network namespaces nor participate in the Planetlab/MLab vserver virtual machine, the exit
statistics cover all TCP connections on a given M-Lab node, including all other experiments, as well as management
traffic for all experiments and Planetlab itself.

2.2) TCP traces
Packet traces are collected to provide a mechanism for validating the Web100 data, or to collect statistics that are
not covered by Web100. They are saved in tcpdump binary files named:
`SideStream/yyyy/mm/dd/nodename/iso_timeZ_ALL0.tra`
  * `ALL` indicate that this is aggregate data across all clients. 
  * In some cases the trailing `0` is replaced by a small integer to avoid overwriting existing files. (E.g. When the
    collection process is restarted.)

These files are normally slightly longer than an hour, running from about 50 seconds before to about 10 seconds after 
the hour, such that consecutive files normally overlap by 1 minute. This was done to minimize potential problems
associated with analyzing packet traces that span more than one tcpdump file.

Since the Planetlab packet capture facility enforces network namespaces, it is not possible to see packets to or from
other M-Lab slices. Furthermore tcpdump only captures TCP connections to local port 8000, which used by the NPAD
webserver. This was done to protect it from NPAD's measurement traffic, which could quite easily overwhelm tcpdump
and/or disk space.The SideStream package for logging web100 statistics from all connections
