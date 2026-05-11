# run_simulation.py
import os
import ephem
import time
import json
from typing import Dict, Tuple, List
from concurrent.futures import ProcessPoolExecutor, as_completed


from utils import verbose_print, read_circuits, set_log_level
# ------------------------- CENTRALIZED CONFIG ------------------------- #
CONFIG: Dict = {
    # Routing topology mode
    "routing_strategy": "ISL-enabled",  # "single-bent-pipe" | "ISL-enabled" | "terrestrial"

    # Paths (all relative paths are resolved against project_root)
    "paths": {
        "project_root": "",  # project root directory

        # inputs
        "speed_sat":        "data/distribution/Starlink_speed_cdf.json",
        "speed_ter":        "data/distribution/terrestrial_speed_cdf.json",
        "circuits":         "data/tor/circuits/waterloo7k.ndjson",
        "tle":              "data/constellation/starlink_satellite_TLEs_2025-09-11.txt",
        "ground_stations":  "data/constellation/starlink_ground_stations.json",
        "pops":             "data/constellation/starlink_pops.json",

        # outputs
        "out_dir":          "data/simulation",
    },

    # Dataset choice & ranges
    "start_circuit_id": 0,
    "end_circuit_id": 100_000,
    "circuit_group_size": 25_000,
    "max_path_limit": 10,  # top-K. Set to 1 for shortest-path only.
    "sat_sat_disable_threshold_m": 1_500_000, # for src/dst satellite pairs closer than this, disable ISL

    # Time window
    "time_start": "2025/09/12 20:00:00",
    "time_end":   "2025/09/13 20:00:00",
    "time_step_sec": 300,

    # Output behavior
    # "overwrite": delete existing and restart; "resume": continue from last time step and append
    "clean_previous_results": "resume",
    "outfile_prefix": "sim",

    # Logging / reproducibility
    "log_level": 1,

    # Parallel settings
    "parallel": {"enabled": False, "workers": 4},
}

def _resolve_paths(cfg: Dict) -> None:
    """
    Resolve CONFIG['paths'] to absolute paths in-place.
    - Makes 'project_root' absolute.
    - For every string value under CONFIG['paths'], if it's not absolute, join with project_root.
    - Does NOT inject any legacy keys into cfg; only normalizes cfg['paths'].
    """
    paths = dict(cfg.get("paths", {}))
    root = os.path.abspath(paths.get("project_root", "."))

    def abs_under_root(val: str) -> str:
        if not isinstance(val, str) or not val:
            return val
        return val if os.path.isabs(val) else os.path.abspath(os.path.join(root, val))

    resolved = {}
    for k, v in paths.items():
        if k == "project_root":
            resolved[k] = root
        elif isinstance(v, str):
            resolved[k] = abs_under_root(v)
        else:
            # Keep non-string values as-is
            resolved[k] = v

    cfg["paths"] = resolved  # in-place replace



def _ensure_dir(path: str) -> None:
    """Ensure output directory exists."""
    if path and not os.path.exists(path):
        os.makedirs(path, exist_ok=True)


def _link_connectivity_from_mode(routing_strategy: str) -> Dict[str, bool]:
    """
    Build link availability map from routing mode.

    Args:
        routing_strategy: "single-bent-pipe" | "ISL-enabled" | "terrestrial"

    Returns:
        Dict of link toggles used by path_simulate_one_time_many_hops.
    """
    if routing_strategy == "single-bent-pipe":
        return {
            "SRC_DST_LINK": False,
            "SRC_SAT_LINK": True,
            "SAT_SAT_LINK": False,
            "SAT_GS_LINK": True,
            "GS_POP_LINK": True,
            "GS_SAT_LINK": False,
            "GS_DST_LINK": False,
            "POP_DST_LINK": True,
        }
    if routing_strategy == "ISL-enabled":
        return {
            "SRC_DST_LINK": False,
            "SRC_SAT_LINK": True,
            "SAT_SAT_LINK": True,
            "SAT_GS_LINK": True,
            "GS_POP_LINK": True,
            "GS_SAT_LINK": False,
            "GS_DST_LINK": False,
            "POP_DST_LINK": True,
        }
    if routing_strategy == "terrestrial":
        return {
            "SRC_DST_LINK": True,
            "SRC_SAT_LINK": False,
            "SAT_SAT_LINK": False,
            "SAT_GS_LINK": False,
            "GS_POP_LINK": False,
            "GS_SAT_LINK": False,
            "GS_DST_LINK": False,
            "POP_DST_LINK": False,
        }
    raise ValueError(f"Unknown routing strategy: {routing_strategy}")



def _time_range(cfg: Dict) -> Tuple[ephem.Date, ephem.Date, int]:
    """
    Build ephem time range.

    Returns:
        (time_start, time_end, step_seconds)
    """
    t0 = ephem.Date(cfg["time_start"])
    t1 = ephem.Date(cfg["time_end"])
    step = int(cfg["time_step_sec"])
    return t0, t1, step


def _log_header(cfg: Dict,
                satellites: List,
                ground_stations: List[Dict],
                point_of_presences: List[Dict]) -> str:
    """
    Compose a single header string for the output file.

    Returns:
        String with simulation metadata lines joined by '\n'.
    """
    lines = [
        f"simulation starts at {cfg['time_start']}",
        f"simulation ends at {cfg['time_end']}",
        f"simulation time step is {cfg['time_step_sec']} seconds",
        f"simulation satellite number is {len(satellites)}",
        f"simulation ground station number is {len(ground_stations)}",
        f"simulation PoP number is {len(point_of_presences)}",
        f"Simulation routing strategy is {cfg['routing_strategy']}",
        f"Simulation gs-satellite link mode is {cfg['gs_satellite_link_mode']}"
    ]
    return "\n".join(lines) + "\n"



def _split_ranges(start: int, end: int, n_groups: int):
    size = (end - start + n_groups - 1) // n_groups
    ranges = []
    cur = start
    while cur < end:
        ranges.append((cur, min(cur + size, end)))
        cur += size
    return ranges

def _simulate_one_group(args):
    (group_idx, group_range, cfg) = args

    p = cfg["paths"]

    from simulation import (
        parse_hops_in_circuits,
        path_simulate_one_time_many_hops,
        read_satellite_tles,
        read_ground_stations,
        read_point_of_presences,
        read_ter_speed_samples,
        read_sat_speed_samples,
    )

    # ---- inputs (absolute) ----
    ecdf_ter = read_ter_speed_samples(p["speed_ter"])
    ecdf_sat = read_sat_speed_samples(p["speed_sat"])
    satellites = read_satellite_tles(p["tle"])
    ground_stations = read_ground_stations(p["ground_stations"])
    point_of_presences = read_point_of_presences(p["pops"])

    link_connectivity = _link_connectivity_from_mode(cfg["routing_strategy"])
    max_path_limit = int(cfg["max_path_limit"])

    t0 = ephem.Date(cfg["time_start"])
    t1 = ephem.Date(cfg["time_end"])
    step_sec = int(cfg["time_step_sec"])

    circuits = read_circuits(p["circuits"], group_range)
    hops, _ = parse_hops_in_circuits(circuits)

    # ---- outputs (absolute) ----
    out_dir = p["out_dir"]
    prefix = cfg["outfile_prefix"]
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(
        out_dir,
        f"{prefix}_{cfg['routing_strategy']}_{group_range[0]}-{group_range[1]}.ndjson"
    )

    mode = cfg.get("clean_previous_results", "overwrite")
    sat_sat_disable_threshold_m = cfg.get("sat_sat_disable_threshold_m", None)

    wrote = 0
    resume_time = None
    file_exists = os.path.exists(out_path)

    if file_exists and mode == "overwrite":
        verbose_print(f"[Group {group_idx}] removing previous result file: {out_path}", level=1)
        os.remove(out_path)

    elif file_exists and mode == "resume":
        # Try to parse last time step from existing file
        with open(out_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if lines:
            last = None
            for line in reversed(lines):
                try:
                    last = json.loads(line)
                    if "time" in last:
                        break
                except Exception:
                    continue
            if last and "time" in last:
                resume_time = ephem.Date(last["time"])
                verbose_print(f"[Group {group_idx}] resuming from {resume_time}", level=1)

    # Open file in append mode if resuming, else write mode
    fmode = "a" if (file_exists and mode == "resume") else "w"
    with open(out_path, fmode, encoding="utf-8") as f:
        if fmode == "w":
            # fresh start: write meta
            f.write(json.dumps({"meta": CONFIG}, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())

        time_cursor = ephem.Date(t0) if resume_time is None else resume_time
        if resume_time is not None:
            time_cursor += step_sec * ephem.second  # start AFTER last saved tick
        idx = 0

        while time_cursor < t1:
            ts_str = str(ephem.Date(time_cursor))
            tick_t0 = time.time()
            verbose_print(f"[Group {group_idx}] simulating time idx={idx}, {ts_str} ...", level=1)

            res = path_simulate_one_time_many_hops(
                hops=hops,
                satellites=satellites,
                ground_stations=ground_stations,
                point_of_presences=point_of_presences,
                current_date_time_string=ts_str,
                link_connectivity=link_connectivity,
                sat_ecdf=ecdf_sat,
                ter_ecdfs=ecdf_ter,
                max_path_limit=max_path_limit,
                show_progress=True,
                progress_position=group_idx,
                sat_sat_disable_threshold_m=sat_sat_disable_threshold_m,
            )

            f.write(json.dumps(res, ensure_ascii=False) + "\n")
            if idx % 1 == 0:  # flush every 1 line
                f.flush()
                os.fsync(f.fileno())

            wrote += 1
            verbose_print(f"[Group {group_idx}] time idx={idx} took {time.time() - tick_t0:.3f}s", level=1)
            time_cursor += step_sec * ephem.second
            idx += 1

    return (group_idx, group_range, out_path, wrote)


def run(config: Dict) -> None:
    set_log_level(config.get("log_level", 0))
    verbose_print("Starting simulation with config:", config, level = 1)
    _resolve_paths(config)


    circuit_num = len(read_circuits(config["paths"]["circuits"]))
    start_id = int(config["start_circuit_id"])
    end_id = min(int(config["end_circuit_id"]), circuit_num)
    group_size = int(config.get("circuit_group_size", end_id - start_id))

    par = config.get("parallel") or {}
    enabled = bool(par.get("enabled", False))
    workers = int(par.get("workers", (os.cpu_count() or 4)))
    workers = max(1, workers)

    if enabled and workers > 1:
        ranges = _split_ranges(start_id, end_id, workers)
        mode = f"parallel {workers} workers"
    else:
        ranges = [
            (i, min(i + group_size, end_id))
            for i in range(start_id, end_id, group_size)
        ]
        mode = f"sequential, group_size={group_size}"

    verbose_print(f"Execution mode: {mode}; groups={ranges}", level=1)

    if enabled and workers > 1:
        # -------- parallel enabled --------
        with ProcessPoolExecutor(max_workers=workers) as ex:
            futures = [ex.submit(_simulate_one_group, (gi, gr, config)) for gi, gr in enumerate(ranges)]
            for fut in as_completed(futures):
                gi, gr, out_path, wrote = fut.result()
                verbose_print(f"[Group {gi}] finished {gr}, wrote {wrote} lines -> {out_path}", level=1)
    else:
        # -------- parallel disabled --------
        for gi, gr in enumerate(ranges):
            verbose_print(f"[Group {gi}] starting {gr} ...", level = 1)
            gi, gr, out_path, wrote = _simulate_one_group((gi, gr, config))
            verbose_print(f"[Group {gi}] finished {gr}, wrote {wrote} lines -> {out_path}", level=1)

    verbose_print("All groups done.", level=1)


if __name__ == "__main__":
    run(CONFIG)

