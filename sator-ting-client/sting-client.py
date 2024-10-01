import socket
import time
import os
import argparse
import socks
import sys
import traceback
from datetime import datetime, date
from stem.control import Controller, EventType
from stem.descriptor import DocumentHandler, parse_file
from stem.descriptor.remote import DescriptorDownloader

from struct import pack

# Sting Client S
# 1. Download consensus and extract as many Tor relays as possible
# 2. Establish circuits Sting Client S --> Random Tor relay --> Sting Relay W --> Sting Relay Z --> Sting Client D
# 3. Measure the circuit latency for multiple times and record
# Run Tor client either on satellite or terrestrial interface

DEFAULT_CONSENSUS_PATH = "tor-consensus"
MSG_SEND = pack("!c", b'!')
MSG_DONE = pack("!c", b'X')

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

def log(msg):
	sys.stdout.write("{0} {1}\n".format(datetime.now(), msg))
	sys.stdout.flush()

class StingClient:
    def __init__(self, config: dict):
        self._controller_port = config['ControllerPort']
        self._tor_socks_addr = config['TorSocksAddr']
        self._destination_addr = config['DestinationAddr']

        self._num_measures = config['NumMeasures']
        self._socks_timeout = config['SocksTimeout']
        self._max_circuit_builds = config['MaxCircuitBuildAttempts']

        self._relay_W_fp = config['TorRelayW']
        self._relay_Z_fp = config['TorRelayZ']

        self._consensus_filepath = config['ConsensusFilepath']
        self._result_save_path = config['ResultSavePath'] + config["ResultName"]
        self._start_point = config['StartPoint']

        self._initialize_controller(self._controller_port)
        self._daily_socks_errors = 0

    def _initialize_controller(self, controller_port):
        self._controller = Controller.from_port(port = controller_port)
        if not self._controller:
            failure("Couldn't connect to Tor, Controller.from_port failed")
        if not self._controller.is_authenticated():
            self._controller.authenticate()
        self._controller.set_conf("__DisablePredictedCircuits", "1")
        self._controller.set_conf("__LeaveStreamsUnattached", "1")

        # Attaches a specific circuit to the given stream (event)
        def attach_stream(event):
            try:
                self._controller.attach_stream(event.id, self._curr_cid)
            except Exception as e:
                warning("Failed to attach stream to %s, unknown circuit. Closing stream..." % self._curr_cid)
                print("\tResponse Code: %s " % str(e.code))
                print("\tMessage: %s" % str(e.message))
                self._controller.close_stream(event.id)

        # An event listener, called whenever StreamEvent status changes
        def probe_stream(event):
            if event.status == 'DETACHED':
                warning("Stream Detached from circuit {0}...".format(self._curr_cid))
                print("\t" + str(vars(event)))
            if event.status == 'NEW' and event.purpose == 'USER':
                attach_stream(event)

        self._controller.add_event_listener(probe_stream, EventType.STREAM)

    # Tell socks to use tor as a proxy
    def _setup_tor_proxy(self):
        socks.setdefaultproxy(socks.PROXY_TYPE_SOCKS5, self._tor_socks_addr[0], self._tor_socks_addr[1])
        socket.socket = socks.socksocket
        sock = socks.socksocket()
        sock.settimeout(self._socks_timeout)
        return sock

    def _download_save_consensus(self, save_path: str):
        downloader = DescriptorDownloader()
        consensus = downloader.get_consensus(document_handler = DocumentHandler.DOCUMENT).run()[0]
        with open(save_path, 'w') as consensus_file:
            consensus_file.write(str(consensus))
        return consensus

    def _load_consensus(self, consensus_filepath: str):
        # if not exist, download it
        if os.path.exists(consensus_filepath) and os.path.isfile(consensus_filepath):
            log(f"Find consensus at {consensus_filepath}, use it.")
            consensus = next(parse_file(consensus_filepath, descriptor_type = 'network-status-consensus-3 1.0', document_handler = DocumentHandler.DOCUMENT))
        else:
            log(f"No consensus at {consensus_filepath}. Download it...")
            consensus = self._download_save_consensus(consensus_filepath)
        return consensus

    def _build_circuit(self, circuit: list):
        cid, last_exception, failures = None, None, 0
        while failures < self._max_circuit_builds:
            try:
                log("Building ciruit...")
                cid = self._controller.new_circuit(circuit, await_build = True)
                success("Circuit built successfully.")
                return cid
            except Exception as exc:
                failures += 1
                if 'message' in vars(exc):
                    warning("{0}".format(vars(exc)['message']))
                else:
                    warning("Circuit failed to be created, reason unknown.")
                if cid is not None:
                    self._controller.close_circuit(cid)
                last_exception = exc
        self._daily_socks_errors += 1
        raise last_exception

    def _sting(self, name, delay = 0):
        arr, num_seen = [], 0
        msg, done = MSG_SEND, MSG_DONE
        try:
            log("Trying to connect..")
            self._tor_sock.connect(self._destination_addr)
            success("Connected successfully!")

            while num_seen < self._num_measures:
                start_time = time.time()
                self._tor_sock.send(msg)
                _ = self._tor_sock.recv(1)
                end_time = time.time()
                arr.append((end_time - start_time))
                num_seen += 1
                time.sleep(delay)

            self._tor_sock.send(done)
            self._tor_sock.shutdown(socket.SHUT_RDWR)
            self._tor_sock.close()

            return [round((x * 1000), 5) for x in arr]

        except Exception as e:
            traceback.print_exc()
            warning("Failed to connect using the given circuit: " + str(e) + "\nClosing connection.")
            if self._tor_sock:
                try:
                    self._tor_sock.shutdown(socket.SHUT_RDWR)
                except:
                    pass
                self._tor_sock.close()
            self._daily_socks_errors += 1
            raise RuntimeError("Failed to connect using the given circuit: ", name, str(e))

    def run(self):
        consensus = self._load_consensus(self._consensus_filepath)
        results = {
            "StartTime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Results": {}
        }
        idx = 0
        while True:
            for fp, relay in consensus.routers.items():
                if idx <= self._start_point:
                    idx += 1
                    continue
                try:
                    circuit = [fp, self._relay_W_fp, self._relay_Z_fp]
                    print(f"## Measuring {idx}-th circuit {circuit}")
                    cir_start_build_time = time.time()
                    cid = self._build_circuit(circuit)
                    self._curr_cid = cid
                    cir_build_time = round((time.time() - cir_start_build_time), 5)

                    # Start measure
                    self._tor_sock = self._setup_tor_proxy()
                    start_sting_time = time.time()
                    circuit_name = "<->".join(circuit)
                    sting_res = self._sting(name = circuit_name)
                    total_sting_time =  round((time.time() - start_sting_time), 5)
                    temp = {
                        "CircuitBuildTime": cir_build_time,
                        "Measurements": sting_res,
                        "TotalStingTime": total_sting_time,
                        "RelayFPs": [fp, self._relay_W_fp, self._relay_Z_fp],
                        "MeasuredAt": datetime.now().strftime("%Y-%m-%d %H-%M-%S")
                    }
                    print("Result:", temp)
                    # results["Results"][circuit_name] = temp
                    with open(self._result_save_path, 'a') as f:
                        f.write(str(temp) + '\n')
                except Exception as e:
                    print(f"Error at {idx}-th relays. {e}")
                finally:
                    idx += 1

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description = "Sting client arguments.")
    parser.add_argument('-si', "--sip", type = str, help = "Source IP", required = True)
    parser.add_argument('-di', "--dip", type = str, help = "Destination IP", required = True)
    parser.add_argument('-dp', "--dport", type = int, help = "Destination port", required = True)
    parser.add_argument('-w', "--relayw", type = str, help = "Fingerprint of relay W", required = True)
    parser.add_argument('-z', "--relayz", type = str, help = "Fingerprint of relay Z", required = True)
    parser.add_argument('-s', "--start", type = int, help = "Start relay index", required = False, default = 0)
    parser.add_argument('-n', "--resname", type = str, help = "name of result file", required = True)

    # Parse the arguments
    args = parser.parse_args()
    current_date = date.today()
    config = {
        "ControllerPort": 9051,
        "TorSocksAddr": (args.sip, 9050),
        "DestinationAddr": (args.dip, args.dport),
        "NumMeasures": 10,
        "SocksTimeout": 10,
        "MaxCircuitBuildAttempts": 5,
        "TorRelayW": args.relayw,
        "TorRelayZ": args.relayz,
        "ConsensusFilepath": DEFAULT_CONSENSUS_PATH,
        "ResultSavePath": "",
        "StartPoint": args.start,
        "ResultName" : args.resname
    }
    sting_client_S = StingClient(config)
    sting_client_S.run()
