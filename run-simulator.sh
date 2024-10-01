#!/bin/bash

read -p "Enter routing strategy (single-bent-pipe [default] or ISL-enabled): " routing_strategy
read -p "Enter dataset (snapshot [default] or timespanning): " dataset
read -p "Enter link mode (all-visible [default] or closest-only): " link_mode
read -p "Enter satellite speed samples filepath (if empty, use lightspeed): " sat_speed_samples
read -p "Enter terrestrial speed samples filepath (if empty, use fiber speed): " ter_speed_samples

routing_strategy=${routing_strategy:-"single-bent-pipe"}
dataset=${dataset:-"snapshot"}
link_mode=${link_mode:-"all-visible"}
sat_speed_samples=${sat_speed_samples:-"lightspeed"}
ter_speed_samples=${ter_speed_samples:-"fiberspeed"}

pip3 install -r requirements.txt
python3 run_simulation.py -rs $routing_strategy -ds $dataset -lm $link_mode -ss $sat_speed_samples -ts $ter_speed_samples

