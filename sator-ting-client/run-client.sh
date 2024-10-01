#!/bin/bash
read -p "Enter local interface IP (satellite or terrestrial): " local_ip
read -p "Enter remote server IP: " remote_ip
read -p "Enter remote server port: " remote_port
read -p "Enter results file name: " result_name
read -p "Enter fingerprint of relay w: " relay_w_fp
read -p "Enter fingerprint of relay z: " relay_z_fp

relay_w_fp=${relay_w_fp:-"0E2689063377F62A4B7A2A68BDFC03F0402335EC"}
relay_z_fp=${relay_z_fp:-"8511418707B1777964F41BDD44099BB5EA3F7C6E"}

echo "Generating torrc..."
echo "SocksPort ${local_ip}:9050" > torrc-client
echo "ControlPort 9051" >> torrc-client # default we use 9051
echo "CookieAuthentication 0" >> torrc-client
echo "RunAsDaemon 1" >> torrc-client

start=0

tor -f torrc-client
pip3 install -r requirements.txt
sleep 120
python3 sting-client.py -si "$local_ip" -di "$remote_ip" -dp $remote_port -w "$relay_w_fp" -z "$relay_z_fp" -s $start -n "$result_name"

