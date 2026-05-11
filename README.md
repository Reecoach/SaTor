# SaTor Simulator 

This repository contains the artifact for the IEEE S&P 2026 paper:

> **“SaTor: Exploring Satellite Routing in Tor to Reduce Latency.”**

**SaTor** proposes integrating satellite routing technologies into the Tor network to reduce latency without strengthening global adversary.
 This repository provides a programmatic simulator that models and estimates the latency of the proposed SaTor architecture.

## Overview

SaTor Simulator enables latency estimation under different routing scenarios by integrating satellite and terrestrial network characteristics. 

It can reproduce experimental results from the paper, or serve as a tool for future research.

## Key Features

* **Generic Latency Simulation:** simulates both satellite and terrestrial communication latencies between any two Tor relays (or arbitrary geographic coordinates)
* **Flexible Routing Models:** supports multiple routing modes including *single bent-pipe satellite link, ISL-enabled satellite routing, and terrestrial-only routing*
* **Temporal Variance:** introduces temporal variance through latency sampling to replicate realistic network dynamics

## Execution Environment

All experiments in the paper were conducted under the following environment.

### Hardware
- CPU: x86_64 multi-core CPU (24 logical cores)
- Memory: 128 GB RAM
- GPU: Not required

### Software
- OS: Ubuntu Linux 22.04 LTS (64-bit)
- Python: 3.12
- Required Python packages: see `requirements.txt`

## Installation and Setup

Clone the repository and create a Python virtual environment:

```
git clone https://github.com/Reecoach/SaTor.git
cd SaTor/simulator/

sudo apt-get update && sudo apt install python3-venv
python3 -m venv .sator
source .sator/bin/activate

pip install -r requirements.txt
```

## Usage 

Run the simulator with default configurations:

```
python3 run.py
```

Simulation results will be logged in: data/simulation/

## Repository Structure

```
SaTor/
 └── simulator/
     ├── data/                       
     │   ├── constellation/          # Starlink constellation data (ground stations, PoPs, TLEs)
     │   ├── distribution/           # Satellite and terrestrial traffic speed distributions
     │   ├── simulation/             # Output directory for simulation results
     │   └── tor/                    
     │       └── circuits/           # Predefined Tor circuits (will be decomposed into hop-level in simulation)
     │
     ├── CONSTANTS.py                # Global constants
     ├── net_tools.py                # Online retrieval of network-related data (TLE files and Tor consensus)
     ├── simulation.py               # Core simulation logic
     ├── utils.py                    # Common latency computation tools
     ├── run.py                      # entry point
     └── requirements.txt            
```

## Simulation Config

The simulator is controlled by a configuration dictionary defined in `run.py`  

It specifies routing modes, dataset paths, simulation ranges, and time settings, etc.

Below is the default configuration used in the paper experiments:

| **Category**      | **Field**                                 | **Description**                                              |
| ----------------- | ----------------------------------------- | ------------------------------------------------------------ |
| **Routing**       | `routing_strategy`                        | Selects the routing mode: `"single-bent-pipe"` (single satellite hop), `"ISL-enabled"` (multi-hop inter-satellite routing), or `"terrestrial"` (ground-only). |
| **Paths**         | `speed_sat`, `speed_ter`                  | ECDFs describing satellite and terrestrial link speeds.      |
|                   | `circuits`                                | Input Tor circuit dataset in NDJSON format. Two datasets are provided: a **100k-circuit** dataset generated using the default Tor path selection algorithm, and a **7k-circuit** dataset initiating from **Waterloo, Canada**. |
|                   | `tle`, `ground_stations`, `pops`          | Starlink constellation data used for orbit and path computation. |
|                   | `out_dir`                                 | Output directory for simulation results.                     |
| **Dataset Range** | `start_circuit_id`, `end_circuit_id`      | Defines the range of circuits to simulate.                   |
|                   | `circuit_group_size`                      | Number of circuits processed per batch; each batch produces a separate output file. |
| **Time Window**   | `time_start`, `time_end`, `time_step_sec` | Defines the simulation period and temporal granularity (in seconds). |
| **Execution**     | `clean_previous_results`                  | Controls output handling: `"overwrite"` starts a fresh run, `"resume"` appends results to existing files. |
|                   | `parallel`                                | Configures multiprocessing and worker count. May show limited performance gains due to the **CPU-bound nature** of orbit and latency computations. |

## Simulation Output Structure (`.ndjson`)

Each simulation produces an .ndjson file under `data/simulation/`.
Every line in this file is an independent, valid JSON object that can be parsed separately, e.g.:

```
with open("data/simulation/sim.ndjson", 'r') as f:
    for line in f:
        record_at_time_t = json.loads(line)
```

In the output .ndjson file, the first line stores the simulation configuration (`CONFIG`), ensuring full reproducibility of the experiment; the subsequent each line corresponds to a specific time point in the simulation:

```yaml
NDJSON File
│
├─ Line 1 → Simulation config (metadata)
│
├─ Line 2 → { time: "T1", results: { hop1: [path1...], hop2: [...] } }
│
├─ Line 3 → { time: "T2", results: { hop1: [...], hop2: [...] } }
│
└─ ...
```

Each hop entry within `"results"` stores a list of paths (top-K shortest) with all intermediate nodes and their spatial metrics, like this:

```
{
  "time": "2025/09/12 20:00:00",
  "results": {
    "Client:Waterloo->AE68ACD0266C414CDED4338D10BCDF17081563BC:RandomEntry": [
      {
        "path": [
          "r_Client(Waterloo)",
          "s_STARLINK-11530 [DTC]",
          "g_Calverton, NY - Earth Go Hard GW",
          "p_LON/LHR - LNDNGBR1",
          "r_AE68ACD0266C414CDED4338D10BCDF17081563BC(RandomEntry)"
        ],
        "lats": [43.4595, 0.7411, 40.9089, 51.5115, 50.6925],
        "lons": [-80.485, -1.4071, -72.7976, -0.0013, 3.1783],
        "distances": [370242.5, 783406.6, 5491454.7, 240200.9],
        "latencies": [0.0036, 0.0081, 0.0359, 0.0058],
        "path_distance": 6885304.6,
        "path_latency": 0.0534
      },
      {
        "path": [
          "r_Client(Waterloo)",
          "s_STARLINK-11530 [DTC]",
          "g_Ashburn, VA - The Ash Ketchum GW",
          "p_LON/LHR - LNDNGBR1",
          "r_AE68ACD0266C414CDED4338D10BCDF17081563BC(RandomEntry)"
        ],
        "lats": [43.4595, 0.7411, 39.0153, 51.5115, 50.6925],
        "lons": [-80.485, -1.4071, -77.4597, -0.0013, 3.1783],
        "distances": [370242.5, 612210.7, 5932290.9, 240200.9],
        "latencies": [0.0036, 0.0065, 0.0382, 0.0058],
        "path_distance": 7154945.0,
        "path_latency": 0.0540
      },
      ...
    ],
    ...
  }
}
```

Description of each field:

| **Field**       | **Type**        | **Description**                                              |
| --------------- | --------------- | ------------------------------------------------------------ |
| `time`          | string          | Time of this simulation snapshot.                            |
| `results`       | dict            | Simulation results for all hops in the dataset at this time. |
| *(hop name)*    | list            | Each hop (e.g., `"Client:Waterloo->RandomEntry"`) maps to a list of candidate paths (top-K). |
| `path`          | list of strings | Ordered sequence of nodes in one complete path, including satellites (s), gateways (g), PoPs (p), and Tor relays (r). |
| `lats`, `lons`  | list of floats  | Geographic coordinates (latitude/longitude) for each node in the path. |
| `distances`     | list of floats  | Distances (in meters) between consecutive nodes.             |
| `latencies`     | list of floats  | Per-segment latency values (in seconds).                     |
| `path_distance` | float           | Total route distance (meters).                               |
| `path_latency`  | float           | Total estimated end-to-end latency (seconds). Multiply by 2 to obtain RTT. |

## Contact

For further questions, please contact:
**Haozhi Li** (Beijing Institute of Technology)
lihaozhi@bit.edu.cn
