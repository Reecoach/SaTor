#!/usr/bin/python
# Echo Server
# Just listen to a port and echo message when receiving it from client immediately

import socket
import sys
import argparse
from datetime import datetime
from struct import unpack

class Color:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    SUCCESS = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    END = '\033[0m'

def success(msg):
	sys.stdout.write(Color.SUCCESS + "{0} {1}\n".format(datetime.now(), msg) + Color.END)
	sys.stdout.flush()

def warning(msg):
	sys.stdout.write(Color.WARNING + "{0} {1}\n".format(datetime.now(), msg) + Color.END)
	sys.stdout.flush()

def failure(msg):
	sys.stdout.write(Color.FAIL + "{0} [ERROR] {1}\n".format(datetime.now(), msg) + Color.END)
	sys.stdout.flush()
	sys.exit(-1)

def msg(msg):
	sys.stdout.write("{0} {1}\n".format(datetime.now(), msg))
	sys.stdout.flush()

class StingEchoServer:

    def __init__(self, config: dict):
        self._destination_addr = config['DestinationAddr']

    def run(self):
        # start socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(self._destination_addr)
        s.listen(1) # we only allow one connection
        msg(f"TCP echo server listening on addr {self._destination_addr}")

        msg_size = 1
        while True:
            try:
                server, address = s.accept()
                msg(f"Connection accepted from {address}")
                data = server.recv(msg_size)
                while data and unpack('!c', data) != 'X':
                    # Just echo the client's data back
                    server.send(data)
                    data = server.recv(msg_size)
                server.close()
            except Exception as e:
                print("Socket Error: " + str(e))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description = "Echo server arguments.")
    parser.add_argument('-i', '--ip', type = str, help = "IP address", required = True)
    parser.add_argument('-p', '--port', type = int, help = "Port to listen to", required = True)

    args = parser.parse_args()
    config = {
        "DestinationAddr": (args.ip, args.port)
    }
    sting_echo_server = StingEchoServer(config)
    sting_echo_server.run()

