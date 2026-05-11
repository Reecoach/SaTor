# SaTor

This repository contains the artifact for the IEEE S&P 2026 paper:

> **“SaTor: Exploring Satellite Routing in Tor to Reduce Latency.”**

**SaTor** explores the integration of satellite routing technologies into the Tor network to reduce its transmission latency without strengthening the global adversary.

The repository currently contains two components:

- **Measurement** — real-world Tor latency measurement datasets collected from a dual-homed testbed with both terrestrial and satellite connectivity
- **Simulator** — a programmatic framework for estimating terrestrial and satellite routing latency between any pair of Tor relays (or arbitrary geographic coordinates)

# Measurement

The `measurement/` directory contains the real-world measurement datasets.

## Measurement Testbed

We deploy a dual-homed measurement testbed located in Waterloo, Canada, equipped with both:

- a conventional terrestrial Internet connection
- a Starlink satellite connection

Using this testbed as the client origin, we construct Tor circuits toward relays distributed worldwide through both interfaces, and compare their latency characteristics to study the potential latency advantages of satellite routing in live Tor.

## Measurement Methodology

Measurements are conducted in multiple rounds.

In each round:

1. All candidate Tor relays are traversed
2. Tor circuits are constructed through both terrestrial and satellite interfaces
3. Probe packets are sent at 1-second intervals 10 times
4. 10 RTT samples are recorded for each circuit

After one round finishes, the next round begins. The measurement campaign lasted for approximately one month.

After filtering circuits with excessive failures or insufficient valid measurements, the final dataset contains 6,897 relatively stable Tor circuits.

# Simulator

The `simulator/` directory provides a programmatic framework for estimating latency under terrestrial and satellite routing scenarios.

## Key Features

- **Generic Latency Simulation:** simulates both satellite and terrestrial communication latencies between arbitrary Tor relays or geographic locations
- **Flexible Routing Models:** supports multiple routing modes including single bent-pipe satellite routing, ISL-enabled satellite routing, and terrestrial-only routing
- **Temporal Variance:** introduces temporal variance through latency sampling to emulate realistic network dynamics

## Simulator Structure

```text
simulator/
├── data/
│   ├── constellation/     # Satellite constellation datasets
│   ├── distribution/      # Propagation speed distributions
│   ├── simulation/        # Simulation outputs
│   └── tor/               # Tor circuit datasets
│
├── CONSTANTS.py
├── net_tools.py
├── simulation.py
├── utils.py
├── run.py
└── requirements.txt
```

## Simulation Data

The simulator relies on several categories of datasets located under `simulator/data/`.

### Satellite Constellation Data

Located in:

```text
data/constellation/
```

This dataset includes satellite constellation information used for orbit computation and routing simulation, including:

* Satellite TLEs
  obtained from:
  [https://celestrak.org/NORAD/elements/gp.php?GROUP=starlink&FORMAT=tle](https://celestrak.org/NORAD/elements/gp.php?GROUP=starlink&FORMAT=tle)

* Ground stations and PoPs
  obtained from:
  [https://pan.uvic.ca/~clarkzjw/starlink/](https://pan.uvic.ca/~clarkzjw/starlink/)

### Propagation Speed Distributions

Located in:

```text
data/distribution/
```

This dataset contains probabilistic propagation speed distributions for both terrestrial and satellite routing.

The propagation speed approximation datasets are derived from the LENS dataset: [https://github.com/clarkzjw/LENS](https://github.com/clarkzjw/LENS)



### Tor Circuit Dataset

Located in:

```text
data/tor/
```

This dataset contains 100k Tor circuits used for simulation experiments.

The circuits are collected using an instrumented Tor client.

Each dataset is stored in `.ndjson` format.

Each line corresponds to a single Tor circuit consisting of three relays:

```text
[
  [
    "AE68ACD0266C414CDED4338D10BCDF17081563BC",                  # Fingerprint
    "peanut",                                                    # Relay nickname
    "94.23.88.117",                                              # Relay IP address
    8080,                                                        # ORPort
    50.6925,                                                     # Geographic latitude
    3.17828,                                                     # Geographic longitude
    "12, Place de la Liberté, Roubaix, Hauts-de-France, France", # Approximate geographic address
    "FR"                                                         # Country code
  ],
  ...
]
```
**Note:**  
Although primarily designed for Tor circuit simulation, the simulator can also estimate latency between arbitrary geographic locations by simply providing valid latitude and longitude coordinates.

## Execution Environment

All experiments in the paper were conducted under the following environment.

### Hardware

* CPU: x86_64 multi-core CPU (24 logical cores)
* Memory: 128 GB RAM
* GPU: Not required

### Software

* OS: Ubuntu Linux 22.04 LTS (64-bit)
* Python: 3.12
* Required Python packages: see `requirements.txt`

## Installation and Setup

Clone the repository and create a Python virtual environment:

```bash
git clone https://github.com/Reecoach/SaTor.git
cd SaTor/simulator/

sudo apt-get update && sudo apt install python3-venv
python3 -m venv .sator
source .sator/bin/activate

pip install -r requirements.txt
```

## Usage

Run the simulator with default configurations:

```bash
python3 run.py
```

Simulation results will be stored under:

```text
data/simulation/
```

## Simulation Config

The simulator is controlled by a configuration dictionary defined in `run.py`.

It specifies routing modes, dataset paths, simulation ranges, and temporal settings.

Default Configuration Fields:

| Category      | Field                                     | Description                                       |
| ------------- | ----------------------------------------- | ------------------------------------------------- |
| Routing       | `routing_strategy`                        | Selects the routing mode                          |
| Paths         | `speed_sat`, `speed_ter`                  | Satellite and terrestrial propagation speed ECDFs |
|               | `circuits`                                | Tor circuit dataset                               |
|               | `tle`, `ground_stations`, `pops`          | Satellite constellation datasets                  |
|               | `out_dir`                                 | Simulation output directory                       |
| Dataset Range | `start_circuit_id`, `end_circuit_id`      | Circuit simulation range                          |
|               | `circuit_group_size`                      | Batch size                                        |
| Time Window   | `time_start`, `time_end`, `time_step_sec` | Simulation temporal granularity                   |
| Execution     | `clean_previous_results`                  | Output handling strategy                          |
|               | `parallel`                                | Multiprocessing configuration                     |

## Simulation Output Structure (`.ndjson`)

Each simulation produces an .ndjson file under `data/simulation/`.
Every line in this file is an independent, valid JSON object that can be parsed separately, e.g.:

```
with open("data/simulation/sim.ndjson", 'r') as f:
    for line in f:
        record_at_time_t = json.loads(line)
```

In the output .ndjson file, the first line stores the simulation configuration (`CONFIG`). The subsequent each line corresponds to a specific time point in the simulation:

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

# Citation

If you use this repository or datasets in your research, please cite:

```bibtex
@INPROCEEDINGS{,
    author = { Li, Haozhi and Elahi, Tariq },
    booktitle = { 2026 IEEE Symposium on Security and Privacy (SP) },
    title = {{ SaTor: Exploring Satellite Routing in Tor to Reduce Latency }},
    year = {2026},
    ISSN = {2375-1207},
    pages = {1261-1279},
    doi = {10.1109/SP63933.2026.00068},
    publisher = {IEEE Computer Society},
    address = {Los Alamitos, CA, USA},
    month = May
}
```

# Contact

For further questions, please contact:

Haozhi Li (Beijing Institute of Technology)
lihaozhi@bit.edu.cn
