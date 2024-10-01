#!/bin/bash

FILE_PATH="/etc/apt/sources.list.d/tor.list"
DISTRIBUTION=$(lsb_release -cs)

echo "deb [signed-by=/usr/share/keyrings/deb.torproject.org-keyring.gpg] https://deb.torproject.org/torproject.org $DISTRIBUTION main" > tor.list
echo "deb-src [signed-by=/usr/share/keyrings/deb.torproject.org-keyring.gpg] https://deb.torproject.org/torproject.org $DISTRIBUTION main" >> tor.list

mv tor.list $FILE_PATH
chmod 644 $FILE_PATH

wget -qO- https://deb.torproject.org/torproject.org/A3C4F0F979CAA22CDBA8F512EE8CBC9E886DDD89.asc | gpg --dearmor | tee /usr/share/keyrings/deb.torproject.org-keyring.gpg >/dev/null

apt update
apt install tor deb.torproject.org-keyring

# torrc
read -p "Set Relay Nickname: " nickname
read -p "Set OR Port: " orport

echo "Nickname $nickname" > torrc-middle-relay
echo "RelayBandwidthRate 80 KB" >> torrc-middle-relay
echo "RelayBandwidthBurst 80 KB" >> torrc-middle-relay

echo "ORPort $orport" >> torrc-middle-relay
echo "SocksPort 0" >> torrc-middle-relay

echo "ExitRelay 0" >> torrc-middle-relay
echo "ExitPolicy reject *:*" >> torrc-middle-relay

# run Tor
tor -f torrc-middle-relay



