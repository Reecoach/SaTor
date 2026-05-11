from __future__ import annotations

import json

import ephem
import math
from geopy.distance import great_circle
from tqdm.auto import tqdm
import os
from typing import Dict, List, Optional

GLOBAL_VERBOSE_LEVEL = 1
VERBOSE = ["DEBUG", "INFO", "WARNING", "ERROR", "FATAL"]

def verbose_print(*args, level: int = 1) -> None:
    """
    Lightweight logging with global level filter.

    Args:
        *args: message parts to be joined by space.
        level: 0..4 according to VERBOSE.
    """
    if level >= GLOBAL_VERBOSE_LEVEL:
        msg = " ".join(str(arg) for arg in args)
        tqdm.write(f"[{ephem.now()}] {VERBOSE[level]}: {msg}")

def set_log_level(level: int) -> None:
    """
    Set global log level.

    Args:
        level: int in [0, len(VERBOSE)-1]

    Raises:
        ValueError: if level is out of range
    """
    global GLOBAL_VERBOSE_LEVEL
    if level < 0 or level >= len(VERBOSE):
        raise ValueError(f"Log level should be between 0 and {len(VERBOSE) - 1}")
    GLOBAL_VERBOSE_LEVEL = level
    verbose_print("Set log level to", VERBOSE[level], level=1)


# -------------------- FILE IO METHODS ----------------------#


def _read_json(path: str | os.PathLike) -> object:
    """Fast path JSON loader."""
    with open(path, "r") as f:
        circuits = json.loads(f.read())
        return circuits


def read_circuits(path: str, circuits_range: Optional[List[int]] = None) -> List[List]:
    """
    Load TOR circuits with optional slicing.

    Supports:
      - .ndjson/.jsonl → stream slice [start, end)
      - .json (array)  → load full array via _read_json, then slice

    Args:
        path: Path to circuits file
        circuits_range: [start, end), zero-based; None = full

    Returns:
        List of circuits (each circuit = list of relays).
    """
    p = path.lower()
    if p.endswith(".ndjson") or p.endswith(".jsonl"):
        start, end = (circuits_range or (0, float("inf")))
        out: List[List] = []
        with open(path, "rb") as f:
            for i, line in enumerate(f):
                if i >= end:
                    break
                if i >= start:
                    try:
                        s = line.decode("utf-8")
                    except UnicodeDecodeError:
                        if line.startswith(b"\xEF\xBB\xBF"):
                            s = line.decode("utf-8-sig")
                        elif line.startswith(b"\xFF\xFE") or line.startswith(b"\xFE\xFF"):
                            s = line.decode("utf-16")
                        else:
                            s = line.decode("latin-1")
                    out.append(json.loads(s))
        verbose_print("Read", len(out), "circuits from", path, "in range", (start, end), level=1)
        return out
    else:
        circuits = _read_json(path)
        if circuits_range:
            start, end = circuits_range
            circuits = circuits[start:end]
        verbose_print("Read", len(circuits), "circuits from", path, "range=", circuits_range, level=1)
        return circuits



def read_satellite_tles(filename_tles: str) -> List:
    """
    Read TLE triples and return ephem satellite objects.

    Notes:
        Skips incomplete/blank trailing lines to be robust to files with a final newline.
    """
    satellites = []
    with open(filename_tles, "r", encoding="utf-8") as f:
        while True:
            line1 = f.readline()
            if not line1:
                break
            line2 = f.readline()
            line3 = f.readline()
            if not line2 or not line3:
                break
            # Keep original spacing; ephem.readtle handles stripping
            satellites.append(ephem.readtle(line1, line2, line3))
    verbose_print("Read", len(satellites), "satellites.", level = 1)
    return satellites

def read_ground_stations(filename_gs: str) -> List[Dict]:
    """Load ground station list."""
    gs_info = _read_json(filename_gs)
    verbose_print("Read", len(gs_info), "ground stations.", level=1)
    return gs_info  # type: ignore[return-value]

def read_point_of_presences(filename_pops: str) -> List[Dict]:
    """Load PoP list."""
    pops_info = _read_json(filename_pops)
    verbose_print("Read", len(pops_info), "PoPs.", level=1)
    return pops_info  # type: ignore[return-value]


# -------------------- DISTANCE METHODS ----------------------#
# All distances in meters.

def distance_between_ground_satellite(g_lat: float, g_lon: float, current_time_date_string: str, satellite) -> float:
    """
    Distance between a ground point and a satellite at time t.

    Args:
        g_lat, g_lon: ground position (deg)
        current_time_date_string: ephem-compatible date string
        satellite: ephem body

    Returns:
        Slant range in meters.
    """
    observer = ephem.Observer()
    observer.date = current_time_date_string
    observer.lat = str(g_lat)
    observer.lon = str(g_lon)
    observer.elevation = 0  # ignore elevation
    satellite.compute(observer)
    return float(satellite.range)

def distance_between_satellites(sat_1, sat_2, current_date_time_string: str) -> float:
    """
    Distance between two satellites at time t.

    Args:
        sat_1, sat_2: ephem bodies
        current_date_time_string: ephem date string

    Returns:
        Distance in meters via law of cosines from ranges and separation angle.
    """
    observer = ephem.Observer()
    observer.date = current_date_time_string
    sat_1.compute(observer)
    sat_2.compute(observer)
    # ephem.separation returns an Angle; float(angle) -> radians
    angle = float(ephem.separation(sat_1, sat_2))
    # Guard cos domain against numerical drift
    c = max(-1.0, min(1.0, math.cos(angle)))
    return math.sqrt(sat_1.range ** 2 + sat_2.range ** 2 - 2 * sat_1.range * sat_2.range * c)

def distance_between_ground_stations(g1_loc: List[float], g2_loc: List[float]) -> float:
    """
    Surface great-circle distance between two ground positions.

    Args:
        g1_loc, g2_loc: [lat, lon] in degrees

    Returns:
        Distance in meters.
    """
    from CONSTANTS import EARTH_RADIUS
    return great_circle(
        (float(g1_loc[0]), float(g1_loc[1])),
        (float(g2_loc[0]), float(g2_loc[1])),
        radius=EARTH_RADIUS / 1000.0,  # geopy expects km; we convert radius to km
    ).m

def get_if_satellite_same_orbit(sat_1,
                                sat_2,
                                tolerance: Dict[str, float] = {"inc": 0.1, "raan": 2.0},
                                orbit_elements: List[str] = ["inc", "raan"]) -> bool:
    """
    Heuristically decide if two satellites are in the same orbit using inclination and RAAN.

    Args:
        tolerance: allowed absolute difference in degrees for each element

    Returns:
        True if within tolerance for all chosen elements.
    """
    for element in orbit_elements:
        v1 = getattr(sat_1, element)
        v2 = getattr(sat_2, element)
        if abs(v1 - v2) > tolerance[element]:
            return False
    return True


def generate_hop_id(s_relay: List, d_relay: List) -> str:
    """
    Generate hop id: "src_fp:src_name->dst_fp:dst_name"
    """
    return s_relay[0] + ":" + s_relay[1] + "->" + d_relay[0] + ":" + d_relay[1]


# -------------------- SAMPLING METHODS ----------------------#

def read_ter_speed_samples(filepath_ter_speed_samples: str) -> Dict[str, Dict[str, List[float]]]:
    """
    Read terrestrial speed samples (ECDF bins) from a JSON file.

    Returns:
        Dict: range_key -> {"bin_edges": [...], "cdf": [...]}
    """
    out: Dict[str, Dict[str, List[float]]] = {}
    data = _read_json(filepath_ter_speed_samples)  # type: ignore[assignment]
    for key, values in data.items():
        if "cdf" in key:
            speed_range = key.split("_")[-1]
            out[speed_range] = {"bin_edges": data["bin_edges"], "cdf": values}
    return out


def read_sat_speed_samples(filepath_sat_speed_samples: str) -> Dict[str, List[float]]:
    """
    Read satellite speed ECDF json with keys: 'bin_edges' and 'cdf'.
    """
    return _read_json(filepath_sat_speed_samples)  # type: ignore[return-value]



