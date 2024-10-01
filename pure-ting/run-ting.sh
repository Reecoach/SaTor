read -p "Enter Public IP: " public_IP
read -p "Enter Destination Port: " dst_port

echo "Generating torrc..."
# echo "AvoidDiskWrites 1" > torrc-client
echo "ControlPort 9051" >> torrc-client
echo "CookieAuthentication 0" >> torrc-client
echo "CircuitBuildTimeout 10" >> torrc-client
echo "LearnCircuitBuildTimeout 0" >> torrc-client
# echo "UseMicrodescriptors 0" >> torrc-client
echo "SocksPort ${public_IP}:9050" >> torrc-client
echo "ExitPolicy reject *:*" >> torrc-client
echo "PublishServerDescriptor 0" >> torrc-client
echo "RunAsDaemon 1" >> torrc-client

tor -f torrc-client &
echo "Generating tingrc..."
echo "SocksPort 9050" > tingrc
echo "ControllerPort 9051" >> tingrc
echo "SourceAddr ${public_IP}" >> tingrc
echo "DestinationAddr ${public_IP}" >> tingrc
echo "DestinationPort ${dst_port}" >> tingrc
echo "NumSamples 200" >> tingrc
echo "NumRepeats 1" >> tingrc
echo "RelayList internet" >> tingrc
echo "RelayCacheTime 24" >> tingrc
echo "W ${public_IP},E364F3E932BA7BAF059E1C39EE307E9902FD1EC8" >> tingrc
echo "Z ${public_IP},B97F5D3E59FAE1A0E65B8045E230A6E1E839ABA3" >> tingrc
echo "SocksTimeout 60" >> tingrc
echo "MaxCircuitBuildAttempts 5" >> tingrc
echo "InputFile relay_pairs" >> tingrc

sleep 60
python3 echo_server &
python3 ting


