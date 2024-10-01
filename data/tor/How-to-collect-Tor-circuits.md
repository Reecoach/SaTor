How we collect circuits using instrumented Tor client
* Modified codes in Tor client are in tor/src/feature/control/control_cmd.c, line 481-498.
* How it works in general: 
  * If we send a SIGHUP signal using stem to Tor client, it will change consensus into the targeted file.
  * If we send a SIGNEWNYM signal using stem to Tor client, it will select a circuit, save it to file, and immediately stops without actually building the circuit.
* Reset consensus file function: reload_consensus_from_file_spacetor() in tor/src/feature/nodelist/networkstatus.c, line 2864-2936
* Collect circuit function: circuit_establish_circuit_fake() in tor/src/core/or/circuitbuild.c, line 521-551