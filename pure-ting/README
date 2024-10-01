TING

Version: 1.0
Released: Friday, November 6, 2015
Contact: Frank Cangialosi (frank@cs.umd.edu)


0 | Overview
============

This is an implementation of the Ting technique as outlined in our IMC 2015
paper Ting: Exploiting and Measuring Latencies Between All Tor Nodes
(https://www.cs.umd.edu/~frank/pubs/ting-imc15.pdf).

Ting can measure the latency between any arbitrary pair of active nodes in the
Tor network quickly and accurately, without requiring extensive measurement
infrastructure or participation from the end hosts. 



1 | Setup
=========

Ting requires running 1 Tor client (used to create circuits) and 2 Tor 
servers (W and Z, as described in Section 3.3).

To get started with the default settings, simply run

  ./configure

This will:
  - install the necessary dependencies (listed in section 5)
  - build the included versions of Tor
  - generate default Tor configuration files 
  - start running the Tor client and servers as daemons
  - generate a default Ting configuration file

If you'd like more control over all of the settings, or run into any issues
during setup, please check out Section 4, which describes Ting's configuration
parameters, and Section 5, which describes all necessary dependencies.



2 | Important Notes
===================

In the current release, Ting requires that the Tor servers W and Z are publicly
listed in the Tor directories. For the next release, we plan to modify Ting to
be able to speak to W and Z without publishing this information to the
directories. 

The default Tor configuration files we generate restrict the exit policy of W
and Z to only allow exiting to this machine's public IP address to minimize
malicious use of your relays (we didn't do this initially, which led a visit
from the FBI :) However, note that this does not mean your Tor relay won't be
used at all by other Tor clients: since it is available on the public list, it
could be chosen as an entry or middle node.

Althrough running W and Z helps to minimize the variance Ting experiences, it is
not an explicit restriction, the math still works out (as described in Section
3.3). For now, if you would prefer not to run your own Tor relays (or are unable
to), you can do the following:
  - remove the Tor installation and setup from the configuration file
  - modify the IP and Fingerprint of W and Z in the tingrc file to match two Tor
    relays. Note that Z's exit policy must allow exiting to your public IP 
    address.
  - run Ting as described below



3 | Using Ting
==============

Ting has two main modes:

  A. Ting -- use ting much like ping to quickly check the latency between two 
  relays. Relays can be identified by ip or fingerprint. We recommend that you
	use fingerprints as ips are not necessarily unique.

    ./ting [fingerprint1] [fingerprint2] [optional args...]
    ./ting [ip1] [ip2] [optional args...]

  B. Collect -- use Ting to measure the latency between all pairs listed in 
  an input file. Again these may be specified by fingerprint or ip, but 
	fingerprint is recommended. 

    ./ting --input-file [input_file] [optional args...]


The number of samples to use and all other relevant settings are read from the
tingrc file in the current directory, however these can optionally also be 
specified from the command line. To see how these are named, simply run:

  ./ting --help



4 | Advanced Configuration
==========================

The default tingrc file should be sufficient for most use cases, however if you
decide to run Tor on different ports, for example, you can easily adjust for
this in the tingrc file. Each possible option is listed below, along with a
description, possible values, and the default value. See the default tingrc for
an example. All options are key value pairs, space-separated, stored one per
line.

ControllerPort    controller port exposed by Tor client that allows stem to talk
                  to the Tor client, default: 9051

SocksPort         port exposed by the Tor client that allows us to
                  default: 9050

SourceAddr        address of this machine, stored in results file simply for
                  record-keeping purposes, default: public address of this machine

DestinationAddr   address of echo server, default: public address of this machine

DestinationPort   port of echo server, default: 16667

NumSamples        number of samples to take for each circuit, default: 200 

NumRepeats        number of times to measure each pair, default: 1

RelayList [internet | FILE]
                  where to find the list of Tor relays, options:
                  internet -- download from onionoo.torproject.org
                  FILE -- path to local FILE containing relays,
                  default: internet

RelayCacheTime    if downloading the relay list from the internet, how long to
                  cache the list locally before downloading a new version, in
                  hours, default: 1
                  
W [IP],[FP]       IP and Fingerprint of W relay 

Z [IP],[FP]       IP and Fingerprint of Z relay 

InputFile [FILE]  if specified, measure all pairs in file.
									if file is "random", keep picking random pairs from the list 
									of currently active Tor relays.
                  default: none

Remote [PORT] 		if specified, bind to PORT and wait. upon recieving message of
									the form "relay1 relay2", measure the latency and respond with
									the result in form "Xms"

SocksTimeout      timeout for SOCKS connection, in seconds,
                  default: 60 

MaxCircuitBuildAttempts
                  after this many attempts to build a circuit, fail and move on,
                  default: 5



5 | Dependencies
================

Packages: 

  * Python 2.7+ 
  * Stem module 1.1.1+
  * SocksiPy module (included in release)
  * Tor (included in release)
  * A public IP address (other Tor relays must be able to connect to you)

In our tests, we used the following versions of Tor. Since Ting builds on
fundamental properties of Tor, it should be possible to implement it atop any
version, however we have only explicitly tested these two. If the Tor control
protocol changes in a newer version of Tor, it may be necessary to tweak the
communication between Ting and Tor. 

  * Client: Tor v0.2.3.25-patched (included in release)
  * Servers: Tor v0.2.4.22 (included in release)
