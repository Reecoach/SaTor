import os
import scipy.stats as st
from utils import *
from dataget import *
import numpy as np
import pandas as pd

# This is extracted from Hypatia's code
MAX_GSL_DISTANCE = 1123000
MAX_ISL_DISTANCE = 5016591

# Theoretical best-case speed
LIGHT_SPEED = 299792458
TERRESTRIAL_TRANS_SPEED = LIGHT_SPEED * 2 / 3

def get_available_satellite(g_lat: float, g_lon: float, current_date_time_string: str, satellites: list):
    # Find what satellites in the list are accessible to [g_lat, g_lon]
    # That is, within maximum connection range as MAX_GSL_DISTANCE
    available_sats = list()
    for satellite in satellites:
        dis_g_sat = distance_between_ground_satellite(g_lat, g_lon, current_date_time_string, satellite)

        if dis_g_sat <= MAX_GSL_DISTANCE:
            available_sats.append(satellite)
    return available_sats

def get_theoretical_optimal_satellite_latency_gain_varying_distance(relay_distance: int, sat_height: int, max_gsl_distance: int = None):
    # Calculate the theoretical transmission latency of satellite and terrestrial communication
    # Best-case, just distance / signal speed
    # And we only consider the one-hop scenario, i.e., only one satellite is in the path
    terrestrial_latency = relay_distance / TERRESTRIAL_TRANS_SPEED

    earth_perimeter = 2 * math.pi * EARTH_RADIUS
    satellite_distance = math.sqrt(EARTH_RADIUS ** 2 + (EARTH_RADIUS + sat_height) ** 2
                                   - 2 * EARTH_RADIUS * (EARTH_RADIUS + sat_height) * math.cos(math.pi * relay_distance / earth_perimeter))
    if max_gsl_distance != None and satellite_distance > max_gsl_distance:
        # satellite not reachable
        satellite_latency = math.inf
    else:
        satellite_latency = 2 * satellite_distance / LIGHT_SPEED
    return terrestrial_latency, satellite_latency

def get_time_point_number_in_simulation_record_files(sim_record_filenames: list):
    # Get the number of time points in the simulation record files
    time_point_number = 0
    for sim_record_filename in sim_record_filenames:
        with open(sim_record_filename, 'r') as sim_rf:
            _ = parse_simulation_record_metadata(sim_rf)
            for _ in sim_rf:
                time_point_number += 1
    return time_point_number

def parse_simulation_record_metadata(record_file_d):
    sim_start_time = record_file_d.readline()
    sim_end_time = record_file_d.readline()
    sim_time_step = record_file_d.readline()
    sim_sat_number = record_file_d.readline()
    sim_gs_number = record_file_d.readline()
    sim_pop_number = record_file_d.readline()
    sim_client_server_info = record_file_d.readline()
    sim_routing_strategy = record_file_d.readline()
    sim_gs_satellite_link_mode = record_file_d.readline()
    sim_latency_mode = record_file_d.readline()
    sim_dataset = record_file_d.readline()

    return [
        sim_start_time,
        sim_end_time,
        sim_time_step,
        sim_sat_number,
        sim_gs_number,
        sim_pop_number,
        sim_client_server_info,
        sim_routing_strategy,
        sim_gs_satellite_link_mode,
        sim_latency_mode,
        sim_dataset
    ]

def extract_one_time_point_from_simulation_record_file(sim_record_filename: str, time_point_index: int):
    # Extract one time point from the simulation record file
    with open(sim_record_filename, 'r') as sim_rf:
        settings = parse_simulation_record_metadata(sim_rf)
        for i in range(time_point_index):
            _ = sim_rf.readline()
        return settings, eval(sim_rf.readline())

# ------------------------ FOR EXP 1: SaTor feasibility ------------------------- #
# Feasibility, from two parts:
# 1. We want to show a large number of hops/circuits are lengthy
# 2. We want to show the alignment between satellite availability and tor relays
# 3. We want to show that satellite routing is accessible for a large number of relays within a reasonable time duration

# ---------------- FOR EXP 1-1: Circuit hop distance calculation ---------------- #
def get_hops_basic_info_in_circuits(geo_extended_circuits: list):
    hops_info = dict()
    for circuit in geo_extended_circuits:
        for i in range(len(circuit) - 1):
            s_relay = circuit[i]
            d_relay = circuit[i + 1]
            hop_id = generate_hop_id(s_relay, d_relay)
            dis = distance_between_ground_stations([s_relay[4], s_relay[5]],
                                                   [d_relay[4], d_relay[5]])
            hops_info[hop_id] = [s_relay[4], s_relay[5], d_relay[4], d_relay[5], dis]
    return hops_info

# ---------------- Satellite availability analysis ---------------- #
def get_relay_starlink_service_accessibility(tor_relays: dict, starlink_regions_info: list, filename_geoip_dataset: str):
    starlink_available_country_codes = [item["region"] for item in starlink_regions_info["prices"]] + ["US", "MT", "CY", "IS", "FI"]
    relay_accessibility_results = dict()
    for relay_fp, relay_info in tor_relays.items():
        relay_for_retrieve = [relay_fp, relay_info["nickname"], relay_info["ip"], relay_info["or_port"]]
        geo_extended_relay = retrieve_relay_geo_location(relay_for_retrieve, relay_info["ip"], filename_geoip_dataset)
        if geo_extended_relay[-1] in starlink_available_country_codes:
            relay_accessibility_results[relay_fp] = [relay_info["nickname"], relay_info["ip"], geo_extended_relay[-1], True]
        else:
            relay_accessibility_results[relay_fp] = [relay_info["nickname"], relay_info["ip"], geo_extended_relay[-1], False]
        verbose_print("Relay", relay_fp, "accessibility checked, we have checked", len(relay_accessibility_results), "relays", level = 0)
    return relay_accessibility_results

def get_relay_accessible_satellites_num(tor_relays: dict, satellites: list, filename_geoip_dataset: str, time_start: ephem.Date, time_end: ephem.Date, time_step: int):
    relay_accessible_satellites_num = dict()
    for relay_fp, relay_info in tor_relays.items():
        relay_for_retrieve = [relay_fp, relay_info["nickname"], relay_info["ip"], relay_info["or_port"]]
        geo_extended_relay = retrieve_relay_geo_location(relay_for_retrieve, relay_info["ip"], filename_geoip_dataset)
        time_cursor = time_start
        relay_accessible_satellites_num_time_range = dict()
        while time_cursor < time_end:
            available_sats = get_available_satellite(geo_extended_relay[4], geo_extended_relay[5], str(ephem.Date(time_cursor)), satellites)
            relay_accessible_satellites_num_time_range[str(ephem.Date(time_cursor))] = len(available_sats)
            time_cursor += time_step * ephem.second
        relay_accessible_satellites_num[relay_fp] = relay_accessible_satellites_num_time_range
        verbose_print("Relay", relay_fp, "satellite accessibility checked, we have checked", len(relay_accessible_satellites_num), "relays", level = 0)
    return relay_accessible_satellites_num

# ------------------------------- Extract some useful information from raw simulation txt files ------------------------------- #

def get_simulation_record_time_points(sim_record_filenames: list):
    simulation_record_time_points = list()
    for sim_record_filename in sim_record_filenames:
        with open(sim_record_filename, 'r', errors = "ignore") as sim_rf:
            _ = parse_simulation_record_metadata(sim_rf)
            for sim_record_at_time_t in sim_rf:
                try:
                    simulation_record_time_points.append(eval(sim_record_at_time_t))
                    verbose_print("Simulation record loaded of", len(simulation_record_time_points), "time points", level = 1)
                except:
                    verbose_print("Simulation record fails to load. Record content is", sim_record_at_time_t, level = 3)
    return simulation_record_time_points


def extract_hops_raw_simulation_data(circuits: list, sim_record_filenames: list, latency_factor: list = None):
    # Input: lists of simulation files, and all circuits recorded in the simulation files
    # Output: csv ready dict for hops simulation info
    def get_modified_latency_by_latency_factor(path_record: dict, factor: float):
        # we want to modify the latency by a factor
        # to align with different real-world measurements on satellite transmission speed
        path_latency = 0
        segment_latencies = path_record["latencies"]
        route_nodes = path_record["path"]
        for i in range(len(route_nodes) - 1):
            if "s_" in route_nodes[i] or "s_" in route_nodes[i + 1]: # satellite involved
                path_latency += segment_latencies[i] * factor
            else:
                path_latency += segment_latencies[i]
        return path_latency

    simulation_record_time_points = get_simulation_record_time_points(sim_record_filenames)
    time_point_num = len(simulation_record_time_points)

    # we first do distance calculation for each hop
    # return format: {hop_id: [s_lat, s_lon, d_lat, d_lon, distance]}
    hops_basic_info = get_hops_basic_info_in_circuits(circuits)

    # Then we get the simulation record for each hop at each time point
    extracted_hops_info = {}
    verbose_print("Start processing hops latency info from simulation records.", level = 1)

    hop_index = 0
    for hop_id, hop_basic_info in hops_basic_info.items():
        extracted_hop_info = {
            "hop_distance": hop_basic_info[-1],
            "hop_coordinates": hop_basic_info[:4],
            "hop_latency_records_time_range": [],
            "hop_satellite_inaccessible_time_points": 0
        }
        # time point level
        for simulation_record_at_time_t in simulation_record_time_points:
            time_t = simulation_record_at_time_t["time"]
            results = simulation_record_at_time_t["results"]
            if hop_id in results.keys() and len(results[hop_id]) > 0:
                # here we use the average of all satellite path as SaTor's performance
                # we set a factor here to modify the latency
                # this is because in raw simulation TXT files, the latency is calculated based on one location of satellite measurement (edinburgh)
                # we use a factor: the radio between edinburgh speed and other places to modify the latency
                hop_mean_latency_at_time_t = []
                if latency_factor is None: # no modification
                    hop_mean_latency_at_time_t.append(np.mean([get_modified_latency_by_latency_factor(hop_record_path, factor = 1) for hop_record_path in results[hop_id]]))
                else:
                    for factor in latency_factor:
                        hop_mean_latency_at_time_t.append(np.mean([get_modified_latency_by_latency_factor(hop_record_path, factor = factor) for hop_record_path in results[hop_id]]))
            else:
                # verbose_print("Hop", hop_id, "at", time_t, "cannot get access to satellite.", level = 3)
                hop_mean_latency_at_time_t = [math.inf] * len(latency_factor) if latency_factor is not None else [math.inf]
                extracted_hop_info["hop_satellite_inaccessible_time_points"] += 1
            extracted_hop_info["hop_latency_records_time_range"].append(hop_mean_latency_at_time_t)

        extracted_hops_info[hop_id] = extracted_hop_info
        hop_index += 1

    csv_hops_info = {
        "hop_id": list(extracted_hops_info.keys()),
        "hop_distance (m)": [hop_info["hop_distance"] for hop_info in extracted_hops_info.values()],
        "hop_coordinates": [hop_info["hop_coordinates"] for hop_info in extracted_hops_info.values()],
        "hop_satellite_inaccessible_time_points": [hop_info["hop_satellite_inaccessible_time_points"] for hop_info in extracted_hops_info.values()]
    }
    for i in range(time_point_num):
        csv_hops_info["time_point_" + str(i)] = [hop_info["hop_latency_records_time_range"][i] for hop_info in extracted_hops_info.values()]

    return csv_hops_info

def merge_hops_csv_for_origin(hops_group_csv_filedir: str, hops_group_csv_filenames: list, terrestrial_csv_filedir: str, factors_define: dict):
    # what we need for origin figure:
    # 1. satellite inaccessible time points percentage
    # 2. pure terrestrial latency
    # 3. then different factors for satellite speed
    # 3.1. satellite latency using optimal dual-homing, min, max, average, average-improvement, satellite faster time percentage
    # 3.2. satellite latency fixing at satellite, min, max, average, improvement

    revised_merged_dataframe = {
        "hop_id": [],
        "hop_distance (m)": [],
        "hop_satellite_inaccessible_time_points_percentage": [],
        "terrestrial_latency (ms)": []
    }
    for loc, factor_num in factors_define.items():
        for i in range(factor_num):
            revised_merged_dataframe[loc + "_" + str(i)] = []

    terrestrial_hops_csv_filenames = [terrestrial_csv_filedir + "hops_" + str(i) + "-" + str(i + 2500) + ".csv" for i in range(0, 20000, 2500)]
    terrestrial_merged_dataframe = merge_csv(terrestrial_hops_csv_filenames)

    for hops_group_csv_filename in hops_group_csv_filenames:
        hops_group_csv_filepath = hops_group_csv_filedir + hops_group_csv_filename
        hops_group_dataframe = pd.read_csv(hops_group_csv_filepath)
        # hop groups
        for index, row in hops_group_dataframe.iterrows():
            # each hop
            hop_id = row["hop_id"]
            hop_distance = row["hop_distance (m)"]
            hop_satellite_inaccessible_time_points = row["hop_satellite_inaccessible_time_points"]
            terrestrial_hop_latency = terrestrial_merged_dataframe[terrestrial_merged_dataframe["hop_id"] == hop_id]["terrestrial_latency (ms)"].values[0]
            revised_merged_dataframe["hop_id"].append(hop_id)
            revised_merged_dataframe["hop_distance (m)"].append(hop_distance)
            revised_merged_dataframe["terrestrial_latency (ms)"].append(terrestrial_hop_latency)
            revised_merged_dataframe["hop_satellite_inaccessible_time_points_percentage"].append(
                hop_satellite_inaccessible_time_points / 121)  # we have 121 time points in total
            hop_latencies_time_points = np.array(
                [eval(row["time_point_" + str(i)], {"inf": np.inf}) for i in range(121)])
            assert hop_latencies_time_points.shape == (121, sum(factors_define.values()))
            # optimal dual-homing satellite latency
            optimal_dual_homing_latencies = np.minimum(hop_latencies_time_points, terrestrial_hop_latency)
            optimal_dual_homing_latencies_average_across_time = np.mean(optimal_dual_homing_latencies, axis=0)
            optimal_dual_homing_latencies_min_across_time = np.min(optimal_dual_homing_latencies, axis=0)
            optimal_dual_homing_latencies_max_across_time = np.max(optimal_dual_homing_latencies, axis=0)
            optimal_dual_homing_latencies_average_improvement = np.mean(
                terrestrial_hop_latency - optimal_dual_homing_latencies, axis=0)
            # fix at satellite
            fixed_satellite_dual_homing_average_across_time = np.mean(hop_latencies_time_points, axis=0)
            fixed_satellite_dual_homing_min_across_time = np.min(hop_latencies_time_points, axis=0)
            fixed_satellite_dual_homing_max_across_time = np.max(hop_latencies_time_points, axis=0)
            fixed_satellite_dual_homing_average_improvement = np.mean(
                terrestrial_hop_latency - hop_latencies_time_points, axis=0)
            # satellite faster time percentage
            latencies_satellite_faster_matrix = np.where(hop_latencies_time_points < terrestrial_hop_latency, 1, 0)
            satellite_faster_time_percentage = np.sum(latencies_satellite_faster_matrix, axis=0) / 121
            assert (optimal_dual_homing_latencies_average_across_time.shape ==
                    optimal_dual_homing_latencies_min_across_time.shape ==
                    optimal_dual_homing_latencies_max_across_time.shape ==
                    optimal_dual_homing_latencies_average_improvement.shape ==
                    fixed_satellite_dual_homing_average_across_time.shape ==
                    fixed_satellite_dual_homing_min_across_time.shape ==
                    fixed_satellite_dual_homing_max_across_time.shape ==
                    fixed_satellite_dual_homing_average_improvement.shape ==
                    satellite_faster_time_percentage.shape ==
                    (sum(factors_define.values()),))

            index = 0
            for loc, factor_num in factors_define.items():
                for i in range(factor_num):
                    revised_merged_dataframe[loc + "_" + str(i)].append([
                        optimal_dual_homing_latencies_average_across_time[index],
                        optimal_dual_homing_latencies_min_across_time[index],
                        optimal_dual_homing_latencies_max_across_time[index],
                        optimal_dual_homing_latencies_average_improvement[index],
                        fixed_satellite_dual_homing_average_across_time[index],
                        fixed_satellite_dual_homing_min_across_time[index],
                        fixed_satellite_dual_homing_max_across_time[index],
                        fixed_satellite_dual_homing_average_improvement[index],
                        satellite_faster_time_percentage[index]
                    ])
                    index += 1
    # to file
    revised_merged_dataframe = pd.DataFrame(revised_merged_dataframe)
    return revised_merged_dataframe


def extract_and_merge_circuit_simulation_result(circuits: list,
                                                hop_satellite_latency_csv_filedir: str,
                                                hop_satellite_latency_csv_filenames: list,
                                                hop_terrestrial_latency_csv_filedir: str,
                                                hop_terrestrial_latency_csv_filenames: list,
                                                defined_factors: dict,
                                                circuit_hop_group_size: int):

    # get all hops' terrestrial latency info
    hop_terrestrial_latencies = dict()
    for hop_terrestrial_latency_csv_filename in hop_terrestrial_latency_csv_filenames:
        if not os.path.exists(hop_terrestrial_latency_csv_filedir + hop_terrestrial_latency_csv_filename):
            verbose_print("File", hop_terrestrial_latency_csv_filedir + hop_terrestrial_latency_csv_filename, "not found.", level = 3)
            continue
        else:
            hop_terrestrial_latency = pd.read_csv(hop_terrestrial_latency_csv_filedir + hop_terrestrial_latency_csv_filename)
            for index, hop in hop_terrestrial_latency.iterrows():
                hop_id = hop["hop_id"]
                hop_terrestrial_latency_info = hop.to_dict()
                hop_terrestrial_latency_info.pop("hop_id")
                hop_terrestrial_latencies[hop_id] = hop_terrestrial_latency_info

    circuits_csv_info = {
        "circuit_id": [],
        "circuit_hops_distance (m)": [], # distance of each hop
        "circuit_distance (m)": [], # total distance summing all hops
        "circuit_hops_terrestrial_latency (ms)": [], # terrestrial latency of each hop, constant throughout the simulation period
        "circuit_terrestrial_latency (ms)": [], # total terrestrial latency summing all hops, constant throughout the simulation period
    }
    for loc, factor_num in defined_factors.items():
        for i in range(factor_num):
            circuits_csv_info[loc + "_" + str(i)] = []
    # in each factor, we have the following info:
    # [shortest, average, longest, average improvement (optimal dual_homing),
    # fixed satellite shortest, fixed satellite average, fixed satellite longest, fixed satellite average improvement,
    # no/one/two/three hops satellite time points num for optimal routing method,
    # satellite hop number for fixed routing method]
    for i in range(0, len(circuits), circuit_hop_group_size):
        circuits_group = circuits[i: i + circuit_hop_group_size]
        # get all related hop info for this group of circuits
        hop_satellite_latencies = dict()
        hop_satellite_latency_csv_filename = hop_satellite_latency_csv_filenames[i // circuit_hop_group_size]
        if not os.path.exists(hop_satellite_latency_csv_filedir + hop_satellite_latency_csv_filename):
            verbose_print("File", hop_satellite_latency_csv_filedir + hop_satellite_latency_csv_filename, "not found.", level = 3)
            continue
        else:
            hop_satellite_latencies_csv_data = pd.read_csv(hop_satellite_latency_csv_filedir + hop_satellite_latency_csv_filename)
            for index, hop in hop_satellite_latencies_csv_data.iterrows():
                hop_id = hop["hop_id"]
                hop_satellite_latency_info = hop.to_dict()
                hop_satellite_latency_info.pop("hop_id")
                hop_satellite_latency_info.pop("hop_satellite_inaccessible_time_points")
                hop_satellite_latencies[hop_id] = hop_satellite_latency_info # {"time_point_0": "[factor_1, factor_2, ...]", ...}

        for circuit in circuits_group:
            # each circuit
            circuit_id = generate_circuit_id(circuit)
            circuits_csv_info["circuit_id"].append(circuit_id)

            all_three_hops_distances = []
            all_three_hops_terrstrial_latencies = []
            all_three_hops_satellite_latencies = []
            for i in range(len(circuit) - 1):
                # each hop
                hop_id = generate_hop_id(circuit[i], circuit[i + 1])
                hop_terrestrial_info = hop_terrestrial_latencies[hop_id]
                hop_satellite_info = hop_satellite_latencies[hop_id]
                # hop distance
                all_three_hops_distances.append(hop_terrestrial_info["hop_distance (m)"])
                all_three_hops_terrstrial_latencies.append(hop_terrestrial_info["terrestrial_latency (ms)"])
                # hop satellite latency
                this_hop_satellite_latencies = [eval(hop_satellite_info["time_point_" + str(i)], {"inf": np.inf}) for i in range(121)] # shape = (time points, factors)
                all_three_hops_satellite_latencies.append(this_hop_satellite_latencies)
            all_three_hops_satellite_latencies = np.array(all_three_hops_satellite_latencies) # shape = (a, b, c). a = 3 hops, b = 121 time points, c = factors
            all_three_hops_terrstrial_latencies = np.array(all_three_hops_terrstrial_latencies) # shape = (a,). a = 3 hops
            all_three_hops_optimal_dual_homing_latencies = np.minimum(all_three_hops_satellite_latencies, all_three_hops_terrstrial_latencies[:, np.newaxis, np.newaxis])
            all_three_hops_optimal_routing_methods = np.where(all_three_hops_satellite_latencies < all_three_hops_terrstrial_latencies[:, np.newaxis, np.newaxis], 1, 0) # 1 means satellite, 0 means terrestrial
            # distance, circuit level
            circuit_distance = sum(all_three_hops_distances)
            circuits_csv_info["circuit_hops_distance (m)"].append(all_three_hops_distances)
            circuits_csv_info["circuit_distance (m)"].append(circuit_distance)
            # terrestrial latency, circuit level
            circuit_terrestrial_latency = np.sum(all_three_hops_terrstrial_latencies)
            circuits_csv_info["circuit_hops_terrestrial_latency (ms)"].append(list(all_three_hops_terrstrial_latencies))
            circuits_csv_info["circuit_terrestrial_latency (ms)"].append(circuit_terrestrial_latency)
            # factor by factor
            index = 0
            for loc, factor_num in defined_factors.items():
                for i in range(factor_num):
                    # optimal dual-homing satellite latency
                    circuit_optimal_dual_homing_latency_shortest_over_time = np.min(np.sum(all_three_hops_optimal_dual_homing_latencies, axis = 0), axis = 0)
                    circuit_optimal_dual_homing_latency_average_over_time = np.mean(np.sum(all_three_hops_optimal_dual_homing_latencies, axis = 0), axis = 0)
                    circuit_optimal_dual_homing_latency_longest_over_time = np.max(np.sum(all_three_hops_optimal_dual_homing_latencies, axis = 0), axis = 0)
                    circuit_optiaml_dual_homing_latency_average_improvement_over_time = np.mean(np.sum(all_three_hops_terrstrial_latencies) - np.sum(all_three_hops_optimal_dual_homing_latencies, axis = 0), axis = 0)

                    # fixed dual-homing latency
                    # 1. determine the average latency of satellite routing and terrestrial routing
                    # 2. for each hop, if satellite routing is faster, we use satellite routing, otherwise, we use terrestrial routing at each time point
                    circuit_fixed_satellite_latencies_average_over_time = np.mean(all_three_hops_satellite_latencies, axis = 1)
                    circuit_fixed_dual_homing_routing_methods = np.where(circuit_fixed_satellite_latencies_average_over_time < all_three_hops_terrstrial_latencies[:, np.newaxis], 1, 0)
                    circuit_fixed_dual_homing_satellite_hop_num = np.sum(circuit_fixed_dual_homing_routing_methods, axis = 0)
                    expanded_circuit_fixed_dual_homing_routing_methods = np.tile(circuit_fixed_dual_homing_routing_methods[:, np.newaxis, :], (1, all_three_hops_satellite_latencies.shape[1], 1))
                    circuit_fixed_dual_homing_latencies = np.where(expanded_circuit_fixed_dual_homing_routing_methods == 1, all_three_hops_satellite_latencies, all_three_hops_terrstrial_latencies[:, np.newaxis, np.newaxis])
                    circuit_fixed_dual_homing_latency_shortest_over_time = np.min(np.sum(circuit_fixed_dual_homing_latencies, axis = 0), axis = 0)
                    circuit_fixed_dual_homing_latency_average_over_time = np.mean(np.sum(circuit_fixed_dual_homing_latencies, axis = 0), axis = 0)
                    circuit_fixed_dual_homing_latency_longest_over_time = np.max(np.sum(circuit_fixed_dual_homing_latencies, axis = 0), axis = 0)
                    circuit_fixed_dual_homing_latency_average_improvement_over_time = np.mean(np.sum(all_three_hops_terrstrial_latencies) - np.sum(circuit_fixed_dual_homing_latencies, axis = 0), axis = 0)

                    # routing method
                    circuit_optimal_routing_method = np.sum(all_three_hops_optimal_routing_methods, axis = 0)
                    circuit_optimal_dual_homing_no_hop_satellite_time_points_num = np.sum(circuit_optimal_routing_method == 0, axis = 0)
                    circuit_optimal_dual_homing_one_hop_satellite_time_points_num = np.sum(circuit_optimal_routing_method == 1, axis = 0)
                    circuit_optimal_dual_homing_two_hops_satellite_time_points_num = np.sum(circuit_optimal_routing_method == 2, axis = 0)
                    circuit_optimal_dual_homing_three_hops_satellite_time_points_num = np.sum(circuit_optimal_routing_method == 3, axis = 0)


                    circuits_csv_info[loc + "_" + str(i)].append([
                        circuit_optimal_dual_homing_latency_shortest_over_time[index],
                        circuit_optimal_dual_homing_latency_average_over_time[index],
                        circuit_optimal_dual_homing_latency_longest_over_time[index],
                        circuit_optiaml_dual_homing_latency_average_improvement_over_time[index],
                        circuit_fixed_dual_homing_latency_shortest_over_time[index],
                        circuit_fixed_dual_homing_latency_average_over_time[index],
                        circuit_fixed_dual_homing_latency_longest_over_time[index],
                        circuit_fixed_dual_homing_latency_average_improvement_over_time[index],
                        circuit_optimal_dual_homing_no_hop_satellite_time_points_num[index],
                        circuit_optimal_dual_homing_one_hop_satellite_time_points_num[index],
                        circuit_optimal_dual_homing_two_hops_satellite_time_points_num[index],
                        circuit_optimal_dual_homing_three_hops_satellite_time_points_num[index],
                        circuit_fixed_dual_homing_satellite_hop_num[index]
                    ])
                    index += 1


    return circuits_csv_info


def compare_two_dataset(filename_dataset_1: str, filename_dataset_2: str):
    with open(filename_dataset_1, 'r') as f_dataset_1:
        dataset_1 = json.loads(f_dataset_1.read())
    with open(filename_dataset_2, 'r') as f_dataset_2:
        dataset_2 = json.loads(f_dataset_2.read())

    relays_in_dataset_1 = list()
    for circuit in dataset_1:
        for relay in circuit:
            if relay[0] not in relays_in_dataset_1:
                relays_in_dataset_1.append(relay[0])

    relays_in_dataset_2 = list()
    for circuit in dataset_2:
        for relay in circuit:
            if relay[0] not in relays_in_dataset_2:
                relays_in_dataset_2.append(relay[0])

    print(len(relays_in_dataset_1), len(relays_in_dataset_2))
    duplicate_relays = list()
    for relay in relays_in_dataset_1:
        if relay in relays_in_dataset_2:
            duplicate_relays.append(relay)
    for relay in relays_in_dataset_2:
        if relay in relays_in_dataset_1 and relay not in duplicate_relays:
            duplicate_relays.append(relay)
    print("number of duplicate relays", len(duplicate_relays))

    hops_in_dataset_1 = list()
    for circuit in dataset_1:
        for i in range(2):
            hop = [circuit[i][0], circuit[i + 1][0]]
            if hop not in hops_in_dataset_1:
                hops_in_dataset_1.append(hop)

    hops_in_dataset_2 = list()
    for circuit in dataset_2:
        for i in range(2):
            hop = [circuit[i][0], circuit[i + 1][0]]
            if hop not in hops_in_dataset_2:
                hops_in_dataset_2.append(hop)

    duplicate_hops_count = 0
    for hop_1 in hops_in_dataset_1:
        for hop_2 in hops_in_dataset_2:
            if hop_1[0] in hop_2 and hop_1[1] in hop_2:
                duplicate_hops_count += 1
    print("number of duplicate hops", duplicate_hops_count)


# ------------------------------- Practical Measurement ------------------------------- #
def hops_circuits_get_ting_result(ting_results_dir: str):
    ting_results_files = os.listdir(ting_results_dir)
    ting_hop_results = dict()
    for ting_results_file in ting_results_files:
        with open(ting_results_dir + ting_results_file, 'r') as f:
            for line in f:
                raw = eval(line)
                try:
                    rtt = sum([item["rtt"] for item in raw["trials"]]) / len(raw["trials"])
                    latency = rtt / 2
                    if latency > 0:
                        ting_hop_results[raw["x"]["fp"] + '->' + raw["y"]["fp"]] = latency
                except:
                    pass
                    # verbose_print("Error in parsing line", raw["x"]["fp"] + '->' + raw["y"]["fp"], level = 3)
    return ting_hop_results

def ting_terrestrial_latency_regression(distance: list, latency: list):
    # Linear regression of terrestrial latency
    slope, intercept, r_value, p_value, std_err = st.linregress(distance, latency)
    return slope, intercept, r_value, p_value, std_err

def Starlink_measurement_data_processing(starlink_data_filepath: str):
    with open(starlink_data_filepath, 'r') as starlink_file:
        data = json.loads(starlink_file.read())
    send_delay = list()
    recv_delay = list()
    rtts = list()
    error_count = 0
    for record in data["round_trips"]:
        # in milliseconds
        try:
            send_delay.append(record["delay"]["send"] / (1000 * 1000))
            recv_delay.append(record["delay"]["receive"] / (1000 * 1000))
            rtts.append(record["delay"]["rtt"] / (1000 * 1000))
        except:
            error_count += 1
    return send_delay, recv_delay, rtts

# ------------------------------- CSV processing ------------------------------- #
def merge_csv(filename_csv_list: list, filename_output_csv: str = None):
    # Merge several csv files into one
    df_list = [pd.read_csv(filename_csv) for filename_csv in filename_csv_list]
    merged_df = pd.concat(df_list, ignore_index = True)  # Concatenate DataFrames vertically
    # Save the merged DataFrame to a CSV file
    if filename_output_csv is not None:
        merged_df.to_csv(filename_output_csv, index = False)
    return merged_df



