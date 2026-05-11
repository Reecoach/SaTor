import heapq
import networkx as nx
from utils import *
import numpy as np
import sys


# ------------------- Caching wrappers ------------------- #

# Position caches keyed by (satellite_id/name, time_str)
_sat_pos_cache = {}
# Distance caches keyed by tuple of endpoints (ordered) + time_str if needed
_dist_sat_sat_cache = {}
_dist_gs_sat_cache = {}
_dist_gs_gs_cache = {}

def _sat_key(sat):
    # Prefer a stable unique id; fallback to name
    return getattr(sat, "name", repr(sat))

def _ordered_pair(a, b):
    return (a, b) if a <= b else (b, a)


# ------------------- Helpers with caches ------------------- #

def get_hops_distance_in_circuits(geo_extended_circuits: list):
    """
    Compute ground-ground distances for each hop in circuits.

    Args:
        geo_extended_circuits: circuits with (lat, lon) for relays.

    Returns:
        { hop_id: distance_meters }
    """
    hops_info = {}
    for circuit in geo_extended_circuits:
        for i in range(len(circuit) - 1):
            s_relay = circuit[i]
            d_relay = circuit[i + 1]
            hop_id = generate_hop_id(s_relay, d_relay)
            d = _distance_gs_gs_cached([s_relay[4], s_relay[5]], [d_relay[4], d_relay[5]])
            hops_info[hop_id] = d
    return hops_info


def satellite_location(satellite, current_time_date_string: str):
    """
    Simulate satellite (lat, lon, alt) at a given time.

    Args:
        satellite: PyEphem or similar satellite object with `.compute()` and `.name`.
        current_time_date_string: Time string acceptable by ephem.Observer.

    Returns:
        tuple(lat, lon, alt) in degrees (lat/lon) and meters (alt), or (None, None, None) on error.
    """
    key = (_sat_key(satellite), current_time_date_string)
    if key in _sat_pos_cache:
        return _sat_pos_cache[key]

    try:
        observer = ephem.Observer()
        observer.date = current_time_date_string
        satellite.compute(observer)
        lat = satellite.sublat
        lon = satellite.sublong
        alt = satellite.elevation
        _sat_pos_cache[key] = (lat, lon, alt)
        return lat, lon, alt
    except Exception as e:
        print(f"[ERROR] satellite_location({satellite}): {e}")
        _sat_pos_cache[key] = (None, None, None)
        return None, None, None


def _distance_sat_sat_cached(src_sat, dst_sat, current_date_time_string: str):
    """
    Cached satellite-satellite distance at time t.

    Args:
        src_sat, dst_sat: satellite objects.
        current_date_time_string: time string.

    Returns:
        Distance in meters (float).
    """
    key = (_ordered_pair(_sat_key(src_sat), _sat_key(dst_sat)), current_date_time_string)
    if key in _dist_sat_sat_cache:
        return _dist_sat_sat_cache[key]
    d = distance_between_satellites(src_sat, dst_sat, current_date_time_string)
    _dist_sat_sat_cache[key] = d
    return d


def _distance_gs_sat_cached(gs_lat, gs_lon, current_date_time_string: str, sat):
    """
    Cached ground-satellite distance.

    Returns:
        Distance in meters (float).
    """
    key = (round(gs_lat, 6), round(gs_lon, 6), _sat_key(sat), current_date_time_string)
    if key in _dist_gs_sat_cache:
        return _dist_gs_sat_cache[key]
    d = distance_between_ground_satellite(gs_lat, gs_lon, current_date_time_string, sat)
    _dist_gs_sat_cache[key] = d
    return d


def _distance_gs_gs_cached(a_lat_lon, b_lat_lon):
    """
    Cached ground-ground (or point-ground) distance.

    Args:
        a_lat_lon: [lat, lon]
        b_lat_lon: [lat, lon]

    Returns:
        Distance in meters (float).
    """
    key = (round(a_lat_lon[0], 6), round(a_lat_lon[1], 6),
           round(b_lat_lon[0], 6), round(b_lat_lon[1], 6))
    if key in _dist_gs_gs_cache:
        return _dist_gs_gs_cache[key]
    d = distance_between_ground_stations(a_lat_lon, b_lat_lon)
    _dist_gs_gs_cache[key] = d
    return d


# ------------------- Sampling latency ------------------- #

def _compile_ecdf(ecdf: dict) -> dict:
    e = np.asarray(ecdf["bin_edges"], dtype=float)
    c = np.asarray(ecdf["cdf"], dtype=float)
    c = np.clip(c, 0.0, 1.0)
    c = np.maximum.accumulate(c)
    mids = (e[:-1] + e[1:]) / 2.0
    return {**ecdf, "_e": e, "_c": c, "_mids": mids}

def compile_all_ecdfs(sat_ecdf: dict, ter_ecdfs: dict):
    sat_comp = _compile_ecdf(sat_ecdf)

    items = sorted(
        ter_ecdfs.items(),
        key = lambda kv: int(str(kv[0]).split("-")[1])
    )
    bounds, buckets = [], []
    for k, v in items:
        ub = int(str(k).split("-")[1])
        bounds.append(ub)
        buckets.append(_compile_ecdf(v))

    bounds = np.asarray(bounds, dtype=int)
    assert len(bounds) == len(buckets) and len(bounds) > 0, \
        "ter_ecdfs' keys should be like '0-2000','2000-5000',..."

    verbose_print("Compiled ECDFs: 1 satellite bucket,", len(buckets), "terrestrial buckets.", level = 0)
    verbose_print("Terrestrial bucket bounds (meters):", bounds, level = 0)

    return sat_comp, bounds, buckets

def sample_speeds_vec(ecdf_comp: dict, n: int) -> np.ndarray:
    _RNG = np.random.default_rng()
    u = _RNG.random(n)
    idx = np.searchsorted(ecdf_comp["_c"], u, side="right") - 1
    idx = np.clip(idx, 0, ecdf_comp["_mids"].size - 1)
    return ecdf_comp["_mids"][idx]

def sample_ter_latencies_vec(distances: np.ndarray,
                             bounds: np.ndarray,
                             buckets: list[dict]) -> np.ndarray:
    bi = np.searchsorted(bounds, distances, side="left")
    bi = np.clip(bi, 0, len(buckets) - 1)

    lat = np.empty_like(distances, dtype=float)
    for b in np.unique(bi):
        mask = (bi == b)
        n = int(mask.sum())
        if n == 0:
            continue
        speeds = sample_speeds_vec(buckets[b], n)
        speeds = np.where(speeds <= 1e-12, 1e-12, speeds)
        lat[mask] = distances[mask] / speeds
    return lat


# ------------------- Selection helpers ------------------- #

def parse_hops_in_circuits(circuits: list):
    """
    Extract hop edges and counts from circuits.

    Args:
        circuits: List of circuits, each is a list of relay tuples.

    Returns:
        (hops, hops_count):
          hops: { hop_id: [src_relay, dst_relay] }
          hops_count: { hop_id: occurrences }
    """
    hops = {}
    hops_count = {}
    for circuit in circuits:
        for i in range(len(circuit) - 1):
            hop_src_id = circuit[i][0] + ':' + circuit[i][1]
            hop_dst_id = circuit[i + 1][0] + ':' + circuit[i + 1][1]
            hop_id = hop_src_id + '->' + hop_dst_id
            hops[hop_id] = [circuit[i], circuit[i + 1]]
            hops_count[hop_id] = hops_count.get(hop_id, 0) + 1
    return hops, hops_count


def get_graph_sat_gs_nodes_at_time_t(
    satellites: list,
    ground_stations: list,
    point_of_presences: list,
    current_date_time_string: str,
):
    """
    Collect node attributes (lat, lon, alt) for all satellites/GS/PoP at time t.

    Args:
        satellites, ground_stations, point_of_presences: lists with required fields.
        current_date_time_string: time string for satellite computation.

    Returns:
        (satellite_nodes, gs_nodes, pop_nodes) dicts keyed by "s_*" / "g_*" / "p_*".
    """
    satellite_nodes_at_time_t = {}
    for satellite in satellites:
        lat, lon, alt = satellite_location(satellite, current_date_time_string)
        sat_name = "s_" + satellite.name
        satellite_nodes_at_time_t[sat_name] = [lat, lon, alt]

    gs_nodes_at_time_t = {f"g_{gs['name']}": [gs["lat"], gs["lng"], 0] for gs in ground_stations}
    pop_nodes_at_time_t = {f"p_{pop['name']}": [pop["lat"], pop["lng"], 0] for pop in point_of_presences}

    return satellite_nodes_at_time_t, gs_nodes_at_time_t, pop_nodes_at_time_t



def get_graph_relay_nodes(s_relay: list, d_relay: list):
    """
    Build relay node dict for source and destination.

    Args:
        s_relay, d_relay: relay tuples [name, id, ip, port, lat, lon] (as in your code).

    Returns:
        { relay_name: [ip, port, lat, lon] }
    """
    relay_nodes = {}
    s_relay_name = "r_" + s_relay[0] + '(' + s_relay[1] + ')'
    d_relay_name = "r_" + d_relay[0] + '(' + d_relay[1] + ')'
    relay_nodes[s_relay_name] = [s_relay[2], s_relay[3], s_relay[4], s_relay[5]]
    relay_nodes[d_relay_name] = [d_relay[2], d_relay[3], d_relay[4], d_relay[5]]
    return relay_nodes


def get_ISL_edges(src_sat, satellites: list, current_date_time_string: str,
                  isl_interface_number: int, sat_ecdf: dict):
    """
    Construct ISL edges from a source satellite using K-nearest neighbors,
    alternating same-orbit and different-orbit peers.

    Args:
        src_sat: satellite object.
        satellites: list of satellites (including src).
        current_date_time_string: time string.
        isl_interface_number: desired number of ISL interfaces.
        sat_ecdf: ECDF of satellite link speeds.

    Returns:
        List of edge dicts: {src, dst, distance, latency}.
        Latency is sampled ONCE per kept edge.
    """
    # Collect candidates with one-pass distance calculation
    same, diff = [], []
    from CONSTANTS import MAX_ISL_DISTANCE
    for dst_sat in satellites:
        if dst_sat is src_sat:
            continue
        d = _distance_sat_sat_cached(src_sat, dst_sat, current_date_time_string)
        if d <= MAX_ISL_DISTANCE:
            item = (d, dst_sat)  # keep distance to avoid recomputation
            if get_if_satellite_same_orbit(src_sat, dst_sat):
                same.append(item)
            else:
                diff.append(item)

    # Limit K by availability
    total_avail = len(same) + len(diff)
    k = min(isl_interface_number or total_avail, total_avail)
    if k <= 0:
        return []

    # Take nearest neighbors in each group
    half = k // 2
    same_k = heapq.nsmallest(max(half, 0), same, key=lambda x: x[0])
    diff_k = heapq.nsmallest(k - len(same_k), diff, key=lambda x: x[0])

    # Interleave same/diff;
    merged = []
    i = j = 0
    while len(merged) < k and (i < len(same_k) or j < len(diff_k)):
        if i < len(same_k):
            merged.append(('same', same_k[i]))
            i += 1
        if len(merged) < k and j < len(diff_k):
            merged.append(('diff', diff_k[j]))
            j += 1

    sat_ecdf_compiled = _compile_ecdf(sat_ecdf)
    dists = np.fromiter((d for _, (d, _) in merged), dtype=float, count=len(merged))
    speeds = sample_speeds_vec(sat_ecdf_compiled, len(merged))
    lats = dists / speeds

    edges = []
    for k, (_, (d, dst_sat)) in enumerate(merged):
        edges.append({
            "src": "s_" + src_sat.name,
            "dst": "s_" + dst_sat.name,
            "distance": float(d),
            "latency": float(lats[k]),
        })

    return edges


def get_graph_edges_no_relays(
        satellites: list,
        ground_stations: list,
        point_of_presences: list,
        current_date_time_string: str,
        link_connectivity: dict,
        sat_ecdf_compiled: dict,
        ter_bounds: np.ndarray,
        ter_buckets: list[dict],
        show_progress: bool = False,
        progress_position: int | None = None,
):
    edges = []
    from CONSTANTS import MAX_GSL_DISTANCE, MAX_ISL_INTERFACE_NUM

    # === SAT-SAT ===
    if link_connectivity.get("SAT_SAT_LINK", False):
        it = satellites
        if show_progress and tqdm is not None:
            it = tqdm(
                satellites,
                desc=f"### Simulating SaTor latency at {current_date_time_string}. Computing SAT-SAT edges",
                position=(progress_position or 0), leave=False,
                dynamic_ncols=False, ncols=150, file=sys.stdout
            )
        for src_sat in it:
            edges.extend(
                get_ISL_edges(
                    src_sat, satellites, current_date_time_string,
                    MAX_ISL_INTERFACE_NUM, sat_ecdf_compiled
                )
            )
        if show_progress and tqdm is not None:
            it.close()

    # === SAT -> GS ===
    if link_connectivity.get("SAT_GS_LINK", False):
        it = satellites
        if show_progress and tqdm is not None:
            it = tqdm(
                satellites,
                desc=f"### Simulating SaTor latency at {current_date_time_string}. Computing SAT-GS edges",
                position=(progress_position or 0), leave=False,
                dynamic_ncols=False, ncols=150, file=sys.stdout
            )
        for sat in it:
            cand_dists, cand_names = [], []
            s_name = "s_" + sat.name
            for gs in ground_stations:
                d = _distance_gs_sat_cached(gs["lat"], gs["lng"], current_date_time_string, sat)
                if d <= MAX_GSL_DISTANCE:
                    cand_dists.append(d)
                    cand_names.append("g_" + gs["name"])
            if cand_dists:
                dists = np.asarray(cand_dists, dtype=float)
                speeds = sample_speeds_vec(sat_ecdf_compiled, dists.size)
                speeds = np.where(speeds <= 1e-12, 1e-12, speeds)
                lats = dists / speeds
                for dst, d, lat in zip(cand_names, dists, lats):
                    edges.append({"src": s_name, "dst": dst, "distance": float(d), "latency": float(lat)})
        if show_progress and tqdm is not None:
            it.close()

    # === GS -> POP ===
    if link_connectivity.get("GS_POP_LINK", False):
        it = ground_stations
        if show_progress and tqdm is not None:
            it = tqdm(
                ground_stations,
                desc=f"### Simulating SaTor latency at {current_date_time_string}. Computing GS-POP edges",
                position=(progress_position or 0), leave=False,
                dynamic_ncols=False, ncols=150, file=sys.stdout
            )
        for gs in it:
            g_name = "g_" + gs["name"]
            dists = []
            names = []
            for pop in point_of_presences:
                d = _distance_gs_gs_cached([gs["lat"], gs["lng"]], [pop["lat"], pop["lng"]])
                dists.append(d)
                names.append("p_" + pop["name"])
            if dists:
                dists = np.asarray(dists, dtype=float)
                lats = sample_ter_latencies_vec(dists, ter_bounds, ter_buckets)
                for dst, d, lat in zip(names, dists, lats):
                    edges.append({"src": g_name, "dst": dst, "distance": float(d), "latency": float(lat)})
        if show_progress and tqdm is not None:
            it.close()

    # === GS -> SAT ===
    if link_connectivity.get("GS_SAT_LINK", False):
        it = ground_stations
        if show_progress and tqdm is not None:
            it = tqdm(
                ground_stations,
                desc=f"### Simulating SaTor latency at {current_date_time_string}. Computing GS-SAT edges",
                position=(progress_position or 0), leave=False,
                dynamic_ncols=False, ncols=150, file=sys.stdout
            )
        for gs in it:
            cand_dists, cand_names = [], []
            g_name = "g_" + gs["name"]
            for sat in satellites:
                d = _distance_gs_sat_cached(gs["lat"], gs["lng"], current_date_time_string, sat)
                if d <= MAX_GSL_DISTANCE:
                    cand_dists.append(d)
                    cand_names.append("s_" + sat.name)
            if cand_dists:
                dists = np.asarray(cand_dists, dtype=float)
                speeds = sample_speeds_vec(sat_ecdf_compiled, dists.size)
                speeds = np.where(speeds <= 1e-12, 1e-12, speeds)
                lats = dists / speeds
                for dst, d, lat in zip(cand_names, dists, lats):
                    edges.append({"src": g_name, "dst": dst, "distance": float(d), "latency": float(lat)})
        if show_progress and tqdm is not None:
            it.close()

    return edges



def get_graph_edges_with_relay(s_relay: list,
                               d_relay: list,
                               satellites: list,
                               ground_stations: list,
                               point_of_presences: list,
                               current_date_time_string: str,
                               link_connectivity: dict,
                               sat_ecdf: dict,
                               ter_ecdfs: dict):
    """
    Build edges that involve source/destination relays.

    Returns:
        List of edge dicts with {src, dst, distance, latency}.
    """
    edges = []
    from CONSTANTS import MAX_GSL_DISTANCE

    sat_ecdf_compiled, ter_bounds, ter_buckets = compile_all_ecdfs(sat_ecdf, ter_ecdfs)

    if link_connectivity.get("SRC_DST_LINK", False):
        d = _distance_gs_gs_cached([s_relay[4], s_relay[5]], [d_relay[4], d_relay[5]])
        lat = float(sample_ter_latencies_vec(np.asarray([d], dtype=float),
                                             ter_bounds, ter_buckets)[0])
        edges.append({
            "src": "r_" + s_relay[0] + '(' + s_relay[1] + ')',
            "dst": "r_" + d_relay[0] + '(' + d_relay[1] + ')',
            "distance": d,
            "latency": lat,
        })

    if link_connectivity.get("SRC_SAT_LINK", False):
        cand_dists = []
        cand_names = []
        for sat in satellites:
            d = _distance_gs_sat_cached(s_relay[4], s_relay[5], current_date_time_string, sat)
            if d <= MAX_GSL_DISTANCE:
                cand_dists.append(d)
                cand_names.append(sat.name)
        if cand_dists:
            cand_dists = np.asarray(cand_dists, dtype=float)
            speeds = sample_speeds_vec(sat_ecdf_compiled, cand_dists.size)
            lats = cand_dists / speeds
            s_name = "r_" + s_relay[0] + '(' + s_relay[1] + ')'
            for dst_name, d, lat in zip(cand_names, cand_dists, lats):
                edges.append({
                    "src": s_name,
                    "dst": "s_" + dst_name,
                    "distance": float(d),
                    "latency": float(lat),
                })

    # 3) GS -> DST RELAY
    if link_connectivity.get("GS_DST_LINK", False):
        cand_dists = []
        cand_names = []
        for gs in ground_stations:
            d = _distance_gs_gs_cached([gs["lat"], gs["lng"]], [d_relay[4], d_relay[5]])
            cand_dists.append(d)
            cand_names.append(gs["name"])
        if cand_dists:
            cand_dists = np.asarray(cand_dists, dtype=float)
            lats = sample_ter_latencies_vec(cand_dists, ter_bounds, ter_buckets)
            dst_name = "r_" + d_relay[0] + '(' + d_relay[1] + ')'
            for src_name, d, lat in zip(cand_names, cand_dists, lats):
                edges.append({
                    "src": "g_" + src_name,
                    "dst": dst_name,
                    "distance": float(d),
                    "latency": float(lat),
                })

    # 4) PoP -> DST RELAY
    if link_connectivity.get("POP_DST_LINK", False):
        cand_dists = []
        cand_names = []
        for pop in point_of_presences:
            d = _distance_gs_gs_cached([pop["lat"], pop["lng"]], [d_relay[4], d_relay[5]])
            cand_dists.append(d)
            cand_names.append(pop["name"])
        if cand_dists:
            cand_dists = np.asarray(cand_dists, dtype=float)
            lats = sample_ter_latencies_vec(cand_dists, ter_bounds, ter_buckets)
            dst_name = "r_" + d_relay[0] + '(' + d_relay[1] + ')'
            for src_name, d, lat in zip(cand_names, cand_dists, lats):
                edges.append({
                    "src": "p_" + src_name,
                    "dst": dst_name,
                    "distance": float(d),
                    "latency": float(lat),
                })

    return edges



def generate_sat_graph(relay_nodes: dict,
                       sat_nodes: dict,
                       gs_nodes: dict,
                       pop_nodes: dict,
                       edges_no_relays: list,
                       edges_with_relays: list):
    """
    Build a directed graph with latency/distance edge attributes.

    Args:
        relay_nodes/sat_nodes/gs_nodes/pop_nodes: dicts of node attributes.
        edges_no_relays/edges_with_relays: edge dicts.

    Returns:
        networkx.DiGraph
    """
    G = nx.DiGraph()
    for node_name, node_info in relay_nodes.items():
        G.add_node(node_name, ip=node_info[0], port=node_info[1], lat=node_info[2], lon=node_info[3])
    for node_name, node_info in sat_nodes.items():
        G.add_node(node_name, lat=node_info[0], lon=node_info[1], alt=node_info[2])
    for node_name, node_info in gs_nodes.items():
        G.add_node(node_name, lat=node_info[0], lon=node_info[1], alt=node_info[2])
    for node_name, node_info in pop_nodes.items():
        G.add_node(node_name, lat=node_info[0], lon=node_info[1], alt=node_info[2])

    for edge in edges_no_relays:
        G.add_edge(edge["src"], edge["dst"], distance=edge["distance"], latency=edge["latency"])
    for edge in edges_with_relays:
        G.add_edge(edge["src"], edge["dst"], distance=edge["distance"], latency=edge["latency"])
    return G


def get_shortest_paths(sat_graph, s_relay: list, d_relay: list, max_path_limit: int = 10):
    """
    Get up to N shortest simple paths by sum(latency).

    Args:
        sat_graph: DiGraph with 'latency' edge attribute.
        s_relay, d_relay: relay tuples.
        max_path_limit: maximum number of paths to return (K in the paper).

    Returns:
        List of dicts with path, lats, lons, distances[], latencies[], path_distance, path_latency.
    """
    source = "r_" + s_relay[0] + '(' + s_relay[1] + ')'
    target = "r_" + d_relay[0] + '(' + d_relay[1] + ')'

    # If only need the single best path, prefer shortest_path for speed:
    # best_path = nx.shortest_path(sat_graph, source, target, weight="latency")
    # ...

    all_shortest_paths = nx.shortest_simple_paths(
        sat_graph, source=source, target=target, weight="latency"
    )

    def get_path_distance_latency(G, path):
        latencies, distances = [], []
        path_latency = 0.0
        path_distance = 0.0
        for i in range(len(path) - 1):
            e = G[path[i]][path[i + 1]]
            d, l = e['distance'], e['latency']
            distances.append(d)
            latencies.append(l)
            path_distance += d
            path_latency += l
        return distances, latencies, path_distance, path_latency

    def get_path_node_location(G, path):
        lats = [G.nodes[n]['lat'] for n in path]
        lons = [G.nodes[n]['lon'] for n in path]
        return lats, lons

    top_n = []
    try:
        for idx, path in enumerate(all_shortest_paths):
            distances, latencies, path_distance, path_latency = get_path_distance_latency(sat_graph, path)
            lats, lons = get_path_node_location(sat_graph, path)
            top_n.append({
                "path": path,
                "lats": lats,
                "lons": lons,
                "distances": distances,
                "latencies": latencies,
                "path_distance": path_distance,
                "path_latency": path_latency
            })
            if idx + 1 >= max_path_limit:
                break
    except nx.NetworkXNoPath:
        verbose_print(f"No path between {source} and {target}", level=1)
    except Exception as e:
        verbose_print(f"Shortest paths failed: {e}", level=1)

    return top_n


def path_simulate_one_time_many_hops(
    hops: dict,
    satellites: list,
    ground_stations: list,
    point_of_presences: list,
    current_date_time_string: str,
    link_connectivity: dict,
    sat_ecdf: dict,
    ter_ecdfs: dict,
    if_path_print: bool = False,
    max_path_limit: int = 10,
    show_progress: bool = True,
    progress_position: int | None = None,
    sat_sat_disable_threshold_m: float | None = None,  # threshold in meters
):
    """
    Simulate routing for multiple hops at a specific time.

    Args:
        hops: dict mapping hop_id -> [src_relay, dst_relay]
        satellites, ground_stations, point_of_presences: topology lists
        current_date_time_string: timestamp string for satellite positions
        link_connectivity: dict of link toggles
        sat_ecdf, ter_ecdfs: latency ECDF distributions
        if_path_print: whether to print paths verbosely
        max_path_limit: maximum number of shortest paths per hop
        show_progress: show tqdm progress bars
        progress_position: tqdm position
        sat_sat_disable_threshold_m: if not None, disable SAT-SAT for hops where src/dst relay distance <= threshold

    Returns:
        dict with { "time": str, "results": {hop_id: [paths...] } }
    """

    # Reset caches at each time step
    _dist_sat_sat_cache.clear()
    _dist_gs_sat_cache.clear()
    _dist_gs_gs_cache.clear()
    _sat_pos_cache.clear()

    # Build node sets
    sat_nodes, gs_nodes, pop_nodes = get_graph_sat_gs_nodes_at_time_t(
        satellites, ground_stations, point_of_presences, current_date_time_string
    )

    # Compile ECDFs once
    sat_ecdf_compiled, ter_bounds, ter_buckets = compile_all_ecdfs(sat_ecdf, ter_ecdfs)

    import copy
    _edges_cache = {"with_sat": None, "no_sat": None}

    def _edges_no_relays_with_sat():
        if _edges_cache["with_sat"] is None:
            lc = copy.deepcopy(link_connectivity)
            lc["SAT_SAT_LINK"] = True
            _edges_cache["with_sat"] = get_graph_edges_no_relays(
                satellites, ground_stations, point_of_presences,
                current_date_time_string, lc,
                sat_ecdf_compiled, ter_bounds, ter_buckets,
                show_progress, progress_position
            )
        return _edges_cache["with_sat"]

    def _edges_no_relays_no_sat():
        if _edges_cache["no_sat"] is None:
            lc = copy.deepcopy(link_connectivity)
            lc["SAT_SAT_LINK"] = False
            _edges_cache["no_sat"] = get_graph_edges_no_relays(
                satellites, ground_stations, point_of_presences,
                current_date_time_string, lc,
                sat_ecdf_compiled, ter_bounds, ter_buckets,
                show_progress, progress_position
            )
        return _edges_cache["no_sat"]

    results = {
        "time": current_date_time_string,
        "results": {}
    }
    no_path_count = 0
    hop_use_sat_cnt = 0
    hop_no_sat_cnt = 0

    iterator = hops.items()
    if show_progress:
        desc = f"### Simulating SaTor latency at {current_date_time_string}. Computing paths for hops"
        iterator = tqdm(
            iterator, total=len(hops), desc=desc,
            position=(progress_position or 0), leave=False,
            dynamic_ncols=False, ncols=150, file=sys.stdout
        )

    for hop_id, (s_relay, d_relay) in iterator:
        # Step 1: decide whether to enable SAT-SAT based on distance threshold
        use_sat_sat = link_connectivity.get("SAT_SAT_LINK", False)
        if use_sat_sat and sat_sat_disable_threshold_m is not None:
            d_sd = _distance_gs_gs_cached([s_relay[4], s_relay[5]], [d_relay[4], d_relay[5]])
            use_sat_sat = (d_sd > float(sat_sat_disable_threshold_m))

        # Step 2: pick pre-built edges_no_relays
        if use_sat_sat:
            edges_no_relays = _edges_no_relays_with_sat()
            hop_use_sat_cnt += 1
        else:
            edges_no_relays = _edges_no_relays_no_sat()
            hop_no_sat_cnt += 1

        # Step 3: add edges associated with src/dst relays
        relay_nodes = get_graph_relay_nodes(s_relay, d_relay)
        edges_with_relays = get_graph_edges_with_relay(
            s_relay, d_relay, satellites, ground_stations, point_of_presences,
            current_date_time_string, link_connectivity,
            sat_ecdf, ter_ecdfs
        )

        # Step 4: build graph and compute the shortest paths
        G = generate_sat_graph(
            relay_nodes, sat_nodes, gs_nodes, pop_nodes,
            edges_no_relays, edges_with_relays
        )
        paths = get_shortest_paths(G, s_relay, d_relay, max_path_limit=max_path_limit)

        if not paths:
            no_path_count += 1
        elif if_path_print:
            for p in paths:
                verbose_print(f"Path {p['path']}", level=0)

        results["results"][hop_id] = paths

    if show_progress and tqdm is not None:
        try:
            iterator.close()
        except Exception:
            pass

    verbose_print(
        f"AT {current_date_time_string}: {no_path_count}/{len(hops)} hops have no path; "
        f"SAT-SAT used in {hop_use_sat_cnt}, disabled in {hop_no_sat_cnt}",
        level = 2 if no_path_count > 0 else 1
    )
    return results






