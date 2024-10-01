import networkx as nx
from utils import *
from dataget import *
from statsmodels.distributions.empirical_distribution import ECDF

## ------------------- SIMULATION CONFIGS ------------------- ##
# This is extracted from Hypatia's code
# in meters
MAX_GSL_DISTANCE = 1123000
MAX_ISL_DISTANCE = 5016591

# Theoretical best-case speed
LIGHT_SPEED = 299792458
TERRESTRIAL_TRANS_SPEED = LIGHT_SPEED * 2 / 3

# According to real-world measurement
# latency = scope * distance + intercept
# latency in **milliseconds**, distance in **meters**
TERRESTRIAL_LATENCY_SCOPE = 0.00001214
TERRESTRIAL_LATENCY_INTERCEPT = 5.58507
SATELLITE_LATENCY_SCOPE = 0.00001165
SATELLITE_LATENCY_INTERCEPT = 0

MAX_ISL_INTERFACE_NUM = 4
def calculate_latency_with_distance(distance: float, scope: float, intercept: float):
    # input: distance in meters, type: "terrestrial" or "space", mode: "theoretical" or "real-world"
    # output: latency
    # we shouldn't use this function anymore, use sampling instead
    return distance * scope + intercept

def sample_latency_with_distance(distance: float, ecdf: ECDF):
    # input: distance in meters, ecdf of speed
    # output: latency in milliseconds
    sampled_speed = sample_speed(ecdf) # in m/s
    return distance / sampled_speed # in seconds

def satellite_location(satellite, current_time_date_string: str):
    # Simulate the location (lat, lon, alt) of a satellite at a time point
    try:
        observer = ephem.Observer()
        observer.date = current_time_date_string
        satellite.compute(observer)
        lat = satellite.sublat
        lon = satellite.sublong
        alt = satellite.elevation
        return lat, lon, alt
    except:
        print("ERROR: In FUNC satellite_location, cannot compute the position of sat", satellite.name)
        return None, None, None

def ground_find_inrange_satellites(g_lat: float, g_lon: float, date_str: str, satellites: list, in_range: int):
    # For a ground location, find its accessible satellite at a time point
    results = list()
    for s in satellites:
        d = distance_between_ground_satellite(g_lat, g_lon, date_str, s)
        if d < in_range:
            results.append([s, d])
    return results

# ------------------------- Simulation Functions ------------------------- #

def parse_hops_in_circuits(circuits: list):
    # Parse all hops in circuits
    hops = dict()
    hops_count = dict()
    for circuit in circuits:
        for i in range(len(circuit) - 1):
            hop_src_id = circuit[i][0] + ':' + circuit[i][1]
            hop_dst_id = circuit[i + 1][0] + ':' + circuit[i + 1][1]
            hop_id = hop_src_id + '->' + hop_dst_id
            hops[hop_id] = [circuit[i], circuit[i + 1]]
            hops_count[hop_id] = hops_count.get(hop_id, 0) + 1
    return hops, hops_count

def get_graph_sat_gs_nodes_at_time_t(satellites: list,
                                    ground_stations: list,
                                    point_of_presences: list,
                                    current_date_time_string: str):
    # Get the [latitudes, longitudes, altitudes] of all satellites and ground stations at a time point
    satellite_nodes_at_time_t = dict()
    for satellite in satellites:
        sat_lat, sat_lon, sat_alt = satellite_location(satellite, current_date_time_string)
        sat_name = "s_" + satellite.name
        satellite_nodes_at_time_t[sat_name] = [sat_lat, sat_lon, sat_alt]

    gs_nodes_at_time_t = dict()
    for gs in ground_stations:
        gs_name = "g_" + gs["name"]
        gs_lat = gs["lat"]
        gs_lon = gs["lng"]
        gs_nodes_at_time_t[gs_name] = [gs_lat, gs_lon, 0]

    pop_nodes_at_time_t = dict()
    for pop in point_of_presences:
        pop_name = "p_" + pop["name"]
        pop_lat = pop["lat"]
        pop_lon = pop["lng"]
        pop_nodes_at_time_t[pop_name] = [pop_lat, pop_lon, 0]

    return satellite_nodes_at_time_t, gs_nodes_at_time_t, pop_nodes_at_time_t

def get_graph_relay_nodes(s_relay: list, d_relay: list):
    # Get all the attributes of the relays for routing graph
    relay_nodes = dict()
    s_relay_name = "r_" + s_relay[0] + '(' + s_relay[1] + ')'
    d_relay_name = "r_" + d_relay[0] + '(' + d_relay[1] + ')'
    relay_nodes[s_relay_name] = [s_relay[2], s_relay[3], s_relay[4], s_relay[5]]
    relay_nodes[d_relay_name] = [d_relay[2], d_relay[3], d_relay[4], d_relay[5]]
    return relay_nodes

def get_ISL_edges(src_sat, satellites: list, current_date_time_string: str, isl_interface_number: int, mode: str, sat_ecdf: ECDF):
    # add ISL in this way:
    # 1. connect to the 1-st nearest satellite in the same orbit
    # 2. connect to the 1-st nearest satellite in the different orbit
    # 3. connect to the 2-nd nearest satellite in the same orbit
    # 4. ... until run out of ISL interfaces
    isl_edges = list()
    satellites_in_range_same_orbit = list()
    satellites_in_range_different_orbit = list()
    for dst_sat in satellites:
        d = distance_between_satellites(src_sat, dst_sat, current_date_time_string)
        if d <= MAX_ISL_DISTANCE:
            if get_if_satellite_same_orbit(src_sat, dst_sat):
                satellites_in_range_same_orbit.append(dst_sat)
            else:
                satellites_in_range_different_orbit.append(dst_sat)
        if len(satellites_in_range_same_orbit) >= isl_interface_number / 2 and len(satellites_in_range_different_orbit) >= isl_interface_number / 2:
            break

    if isl_interface_number == None or isl_interface_number > len(satellites_in_range_same_orbit) + len(satellites_in_range_different_orbit):
        isl_interface_number = len(satellites_in_range_same_orbit) + len(satellites_in_range_different_orbit)

    flag = 1
    same_orbit_sat_index = 0
    different_orbit_sat_index = 0
    for i in range(isl_interface_number):
        if flag == 1:
            dst_sat = satellites_in_range_same_orbit[same_orbit_sat_index if same_orbit_sat_index < len(satellites_in_range_same_orbit) else -1]
            same_orbit_sat_index += 1
        else:
            dst_sat = satellites_in_range_different_orbit[different_orbit_sat_index if different_orbit_sat_index < len(satellites_in_range_different_orbit) else -1]
            different_orbit_sat_index += 1
        d = distance_between_satellites(src_sat, dst_sat, current_date_time_string)
        isl_edge = {
            "src": "s_" + src_sat.name,
            "dst": "s_" + dst_sat.name,
            "distance": d,
            "latency": sample_latency_with_distance(d, sat_ecdf) # in seconds
        }
        isl_edges.append(isl_edge)
        flag = -flag
    return isl_edges

def get_graph_edges_no_relay(satellites: list,
                             ground_stations: list,
                             point_of_presences: list,
                             current_date_time_string: str,
                             link_connectivity: dict,
                             gs_satellite_link_mode: str,
                             sat_ecdf: ECDF,
                             ter_ecdf: ECDF):
    edges = []
    if link_connectivity["SAT_SAT_LINK"]:
        for src_sat in satellites:
            edges += get_ISL_edges(src_sat, satellites, current_date_time_string, MAX_ISL_INTERFACE_NUM)
    if link_connectivity["SAT_GS_LINK"]:
        for sat in satellites:
            all_visible_edges = list()
            for gs in ground_stations:
                dis_sat_gs = distance_between_ground_satellite(gs["lat"], gs["lng"], current_date_time_string, sat)
                if dis_sat_gs <= MAX_GSL_DISTANCE:
                    all_visible_edges.append({
                        "src": "s_" + sat.name,
                        "dst": "g_" + gs["name"],
                        "distance": dis_sat_gs,
                        "latency": sample_latency_with_distance(dis_sat_gs, sat_ecdf)
                    })
            if gs_satellite_link_mode == "all-visible":
                edges += all_visible_edges
            elif gs_satellite_link_mode == "closest-only":
                if len(all_visible_edges) > 0:
                    edges.append(min(all_visible_edges, key = lambda x: x["distance"]))
            else:
                verbose_print("gs_satellite_link_mode should be either 'all-visible' or 'closest-only'", level = 3)

    if link_connectivity["GS_POP_LINK"]:
        for gs in ground_stations:
            for pop in point_of_presences:
                dis_gs_pop = distance_between_ground_stations([gs["lat"], gs["lng"]],
                                                              [pop["lat"], pop["lng"]])
                edges.append({
                    "src": "g_" + gs["name"],
                    "dst": "p_" + pop["name"],
                    "distance": dis_gs_pop,
                    "latency": sample_latency_with_distance(dis_gs_pop, ter_ecdf)
                })
    if link_connectivity["GS_SAT_LINK"]:
        for gs in ground_stations:
            all_visible_edges = list()
            for sat in satellites:
                dis_gs_sat = distance_between_ground_satellite(gs["lat"], gs["lng"], current_date_time_string, sat)
                if dis_gs_sat <= MAX_GSL_DISTANCE:
                    all_visible_edges.append({
                        "src": "g_" + gs["name"],
                        "dst": "s_" + sat.name,
                        "distance": dis_gs_sat,
                        "latency": sample_latency_with_distance(dis_gs_sat, sat_ecdf)
                    })
            if gs_satellite_link_mode == "all-visible":
                edges += all_visible_edges
            elif gs_satellite_link_mode == "closest-only":
                if len(all_visible_edges) > 0:
                    edges.append(min(all_visible_edges, key = lambda x: x["distance"]))
            else:
                verbose_print("gs_satellite_link_mode should be either 'all-visible' or 'closest-only'", level = 3)
    return edges

def get_graph_edges_with_relay(s_relay: list,
                               d_relay: list,
                               satellites: list,
                               ground_stations: list,
                               point_of_presences: list,
                               current_date_time_string: str,
                               link_connectivity: dict,
                               gs_satellite_link_mode: str,
                               sat_ecdf: ECDF,
                               ter_ecdf: ECDF):
    edges = []
    if link_connectivity["SRC_DST_LINK"]:
        dis_src_dst = distance_between_ground_stations([s_relay[4], s_relay[5]],
                                                       [d_relay[4], d_relay[5]])
        edges.append({
            "src": "r_" + s_relay[0] + '(' + s_relay[1] + ')',
            "dst": "r_" + d_relay[0] + '(' + d_relay[1] + ')',
            "distance": dis_src_dst,
            "latency": sample_latency_with_distance(dis_src_dst, ter_ecdf)
        })

    if link_connectivity["SRC_SAT_LINK"]:
        all_visible_edges = list()
        for sat in satellites:
            dis_src_sat = distance_between_ground_satellite(s_relay[4], s_relay[5], current_date_time_string, sat)
            if dis_src_sat <= MAX_GSL_DISTANCE:
                all_visible_edges.append({
                    "src": "r_" + s_relay[0] + '(' + s_relay[1] + ')',
                    "dst": "s_" + sat.name,
                    "distance": dis_src_sat,
                    "latency": sample_latency_with_distance(dis_src_sat, sat_ecdf)
                })
        if len(all_visible_edges) == 0:
            verbose_print("No satellite is in range of", s_relay[1], "at time", current_date_time_string, level = 2)
        if gs_satellite_link_mode == "all-visible":
            edges += all_visible_edges
        elif gs_satellite_link_mode == "closest-only":
            if len(all_visible_edges) > 0:
                edges.append(min(all_visible_edges, key = lambda x: x["distance"]))
        else:
            verbose_print("gs_satellite_link_mode should be either 'all-visible' or 'closest-only'", level = 3)

    if link_connectivity["GS_DST_LINK"]:
        for gs in ground_stations:
            dis_gs_dst = distance_between_ground_stations([gs["lat"], gs["lng"]],
                                                          [d_relay[4], d_relay[5]])
            edges.append({
                "src": "g_" + gs["name"],
                "dst": "r_" + d_relay[0] + '(' + d_relay[1] + ')',
                "distance": dis_gs_dst,
                "latency": sample_latency_with_distance(dis_gs_dst, ter_ecdf)
            })
    if link_connectivity["POP_DST_LINK"]:
        for pop in point_of_presences:
            dis_pop_dst = distance_between_ground_stations([pop["lat"], pop["lng"]],
                                                           [d_relay[4], d_relay[5]])
            edges.append({
                "src": "p_" + pop["name"],
                "dst": "r_" + d_relay[0] + '(' + d_relay[1] + ')',
                "distance": dis_pop_dst,
                "latency": sample_latency_with_distance(dis_pop_dst, ter_ecdf)
            })
    return edges

def generate_sat_graph(relay_nodes: dict,
                       sat_nodes: dict,
                       gs_nodes: dict,
                       pop_nodes: dict,
                       edges_no_relays: list,
                       edges_with_relays: list):
    # input:
    # relay nodes: { relay_name: [ip, port, lat, lon] }
    # sat nodes: { sat_name: [lat, lon, alt] }
    # gs nodes: { gs_name: [lat, lon, alt] }
    # pop nodes: { pop_name: [lat, lon, alt] }

    G = nx.DiGraph()
    for node_name, node_info in relay_nodes.items():
        G.add_node(node_name, ip = node_info[0], port = node_info[1], lat = node_info[2], lon = node_info[3])
    for node_name, node_info in sat_nodes.items():
        G.add_node(node_name, lat = node_info[0], lon = node_info[1], alt = node_info[2])
    for node_name, node_info in gs_nodes.items():
        G.add_node(node_name, lat = node_info[0], lon = node_info[1], alt = node_info[2])
    for node_name, node_info in pop_nodes.items():
        G.add_node(node_name, lat = node_info[0], lon = node_info[1], alt = node_info[2])

    # add no-relay edges
    for edge in edges_no_relays:
        G.add_edge(edge["src"], edge["dst"], distance = edge["distance"], latency = edge["latency"])
    # add relay edges
    for edge in edges_with_relays:
        G.add_edge(edge["src"], edge["dst"], distance = edge["distance"], latency = edge["latency"])
    return G

def get_shortest_paths(sat_graph, s_relay: list, d_relay: list, max_path_limit: int = 10):
    # Get the shortest paths from src_relay to dst_relay
    # According to the provided routing graph
    source = "r_" + s_relay[0] + '(' + s_relay[1] + ')'
    target = "r_" + d_relay[0] + '(' + d_relay[1] + ')'
    all_shortest_paths = nx.shortest_simple_paths(sat_graph,
                                                  source = source,
                                                  target = target,
                                                  weight = "latency")

    # `all_shortest_paths` is a generator
    top_n_shortest_paths = list()

    def get_path_distance_latency(G, path):
        latencies = list()
        distances = list()
        path_latency = 0
        path_distance = 0
        for i in range(len(path) - 1):
            distances.append(G[path[i]][path[i + 1]]['distance'])
            latencies.append(G[path[i]][path[i + 1]]['latency'])
            path_distance += G[path[i]][path[i + 1]]['distance']
            path_latency += G[path[i]][path[i + 1]]['latency']
        return distances, latencies, path_distance, path_latency

    def get_path_node_location(G, path):
        lats = [G.nodes[node]['lat'] for node in path]
        lons = [G.nodes[node]['lon'] for node in path]
        return lats, lons
    try:
        for path in all_shortest_paths:
            distances, latencies, path_distance, path_latency = get_path_distance_latency(sat_graph, path)
            lats, lons = get_path_node_location(sat_graph, path)
            top_n_shortest_paths.append({
                "path": path,
                "lats": lats,
                "lons": lons,
                "distances": distances,
                "latencies": latencies,
                "path_distance": path_distance,
                "path_latency": path_latency
            })
            if len(top_n_shortest_paths) >= max_path_limit:
                break
    except:
        verbose_print("It seems that there are not enough paths between", source, "and", target, level = 0)


    return top_n_shortest_paths

def path_simulate_one_time_many_hops(hops: dict,
                                     satellites: list,
                                     ground_stations: list,
                                     point_of_presences: list,
                                     current_date_time_string: str,
                                     link_connectivity: dict,
                                     gs_satellite_link_mode: str,
                                     sat_ecdf: ECDF,
                                     ter_ecdf: ECDF,
                                     if_path_print: bool = False):

    sat_nodes_in_graph, gs_nodes_in_graph, pop_nodes_in_graph = get_graph_sat_gs_nodes_at_time_t(satellites, ground_stations, point_of_presences, current_date_time_string)
    edges_no_relays = get_graph_edges_no_relay(satellites, ground_stations, point_of_presences, current_date_time_string, link_connectivity, gs_satellite_link_mode, sat_ecdf, ter_ecdf)
    hops_simulation_results_at_time_t = {
        "time": current_date_time_string,
        "results": dict()
    }
    no_path_count = 0
    for hop_id, hop in hops.items():
        verbose_print("Simulation result for hop", hop_id, level = 0)
        s_relay = hop[0]
        d_relay = hop[1]
        verbose_print("THIS HOP FROM", s_relay[1], s_relay[2], '(' + str(s_relay[4]) + ',' + str(s_relay[5]) + ')',
              "TO", d_relay[1], d_relay[2], '(' + str(d_relay[4]) + ',' + str(d_relay[5]) + ')', level = 0)

        relay_nodes = get_graph_relay_nodes(s_relay, d_relay)
        edges_with_relays = get_graph_edges_with_relay(s_relay,
                                                       d_relay,
                                                       satellites,
                                                       ground_stations,
                                                       point_of_presences,
                                                       current_date_time_string,
                                                       link_connectivity,
                                                       gs_satellite_link_mode,
                                                       sat_ecdf,
                                                       ter_ecdf)
        graph_path_time_start = time.time()
        sat_graph_this_time_hop = generate_sat_graph(relay_nodes, sat_nodes_in_graph, gs_nodes_in_graph, pop_nodes_in_graph, edges_no_relays, edges_with_relays)
        top_n_shortest_paths = get_shortest_paths(sat_graph_this_time_hop, s_relay, d_relay)
        graph_path_time_end = time.time()
        verbose_print("Graph generation and path finding time", graph_path_time_end - graph_path_time_start, "seconds.", level = 0)

        if len(top_n_shortest_paths) == 0:
            no_path_count += 1
            verbose_print("No path this hop. From", s_relay[1], s_relay[2], '(' + str(s_relay[4]) + ',' + str(s_relay[5]) + ')',
              "TO", d_relay[1], d_relay[2], '(' + str(d_relay[4]) + ',' + str(d_relay[5]) + ')', "AT", current_date_time_string, level = 2)
        else:
            verbose_print("Find", len(top_n_shortest_paths), "paths from", s_relay[1], "to", d_relay[1], "AT", current_date_time_string, level = 0)

        if if_path_print:
            for path in top_n_shortest_paths:
                verbose_print("  Path", path["path"], level = 0)
                verbose_print("  Latitude", path["lats"], level = 0)
                verbose_print("  Longitude", path["lons"], level = 0)
                verbose_print("  Latencies", path["latencies"], level = 0)
                verbose_print("  Distances", path["distances"], level = 0)
                verbose_print("  Path latency", path["path_latency"], level = 0)
                verbose_print("  Path distance", path["path_distance"], level = 0)

        hops_simulation_results_at_time_t["results"][hop_id] = top_n_shortest_paths
    verbose_print("### AT", current_date_time_string, no_path_count, "IN", len(hops), "hops do not have path", level = 2)

    return hops_simulation_results_at_time_t

def get_hops_distance_in_circuits(geo_extended_circuits: list):
    hops_info = dict()
    for circuit in geo_extended_circuits:
        for i in range(len(circuit) - 1):
            s_relay = circuit[i]
            d_relay = circuit[i + 1]
            hop_id = generate_hop_id(s_relay, d_relay)
            dis = distance_between_ground_stations([s_relay[4], s_relay[5]],
                                                   [d_relay[4], d_relay[5]])
            hops_info[hop_id] = dis
    return hops_info

def calculate_hops_terrestrial_latency(circuits: list, latency_mode: str):
    # break circuits into hops, and calculate the terrestrial latency of each hop
    # return a csv ready dict
    hops_distances = get_hops_distance_in_circuits(circuits)
    csv_hops_terrestrial_distance_info = {
        "hop_id": list(hops_distances.keys()),
        "hop_distance (m)": list(hops_distances.values()),
        "terrestrial_latency (ms)": [hop_dis / TERRESTRIAL_TRANS_SPEED if latency_mode == "theoretical" else
                                hop_dis * TERRESTRIAL_LATENCY_SCOPE + TERRESTRIAL_LATENCY_INTERCEPT for hop_dis in hops_distances.values()]
    }
    return csv_hops_terrestrial_distance_info
