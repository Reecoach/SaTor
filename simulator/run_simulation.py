from simulation import *
from analyses import *
import argparse

CITIES = ["Berlin", "Moscow", "Los Angeles", "Sydney", "Tehran", "Jakarta", "Tokyo", "Rio de Janeiro"]
CITIES_LATS = [52.5200, 55.7558, 34.0522, -33.8688, 35.6895, -6.2088, 35.6895, -22.9068]
CITIES_LONS = [13.4050, 37.6176, -118.2437, 151.2093, 51.3890, 106.8456, 139.6917, -43.1729]
CITIES_COUNTRY_CODES = ["DE", "RU", "US", "AU", "IR", "ID", "JP", "BR"]

if __name__ == "__main__":
    #### Do simulation ####
    parser = argparse.ArgumentParser(description = "SaTor simulator parameters.")
    parser.add_argument(
        '-rs',
        '--routing_strategy',
        type = str,
        help = "Choose between single-bent-pipe and ISL-enabled",
        choices = ["single-bent-pipe", "ISL-enabled"],
        required = True
    )
    parser.add_argument(
        '-lm',
        '--gs_satellite_link_mode',
        type = str,
        choices = ["all-visible", "closest-only"],
        help = "Choose between all-visible and closest-only",
        default = "all-visible",
        required = False
    )
    parser.add_argument(
        '-ss',
        '--satellite_speed_samples',
        type = str,
        help = "Satellite speed samples file path",
        required = False,
        default = "lightspeed"
    )
    parser.add_argument(
        '-ts',
        '--terrestrial_speed_samples',
        type = str,
        help = "Terrestrial speed samples file path",
        required = False,
        default = "fiberspeed"
    )
    parser.add_argument(
        '-ds',
        '--dataset',
        type = str,
        help = "Choose between snapshot and timespanning",
        choices = ["snapshot", "timespanning"],
        default = "snapshot",
        required = False
    )
    args = parser.parse_args()
    routing_strategy = args.routing_strategy
    gs_satellite_link_mode = args.gs_satellite_link_mode
    if args.satellite_speed_samples != "lightspeed":
        with open(args.satellite_speed_samples, 'r') as f:
            satellite_speed_samples = json.load(f)
    else:
        satellite_speed_samples = [LIGHT_SPEED]
    if args.terrestrial_speed_samples != "fiberspeed":
        with open(args.terrestrial_speed_samples, 'r') as f:
            terrestrial_speed_samples = json.load(f)
    else:
        terrestrial_speed_samples = [TERRESTRIAL_TRANS_SPEED]
    satellite_speed_ecdf = get_speed_ECDF(satellite_speed_samples)
    terrestrial_speed_ecdf = get_speed_ECDF(terrestrial_speed_samples)
    dataset = args.dataset
    if_record_sim_result = True
    sim_result_filedir = "data/simulation/"

    # Read necessary data
    filename_geoip_dataset = "data/tor/tor_relays_geoip_dataset.json"
    filename_tles = "data/constellation/starlink_satellite_TLEs_06-09-2024.txt"
    filename_tor_circuits = "data/tor/tor_circuits_snapshot-13-04-2024.txt" if dataset == "snapshot" else "data/tor/tor_circuits_timespanning.txt"
    filename_ground_stations = "data/constellation/starlink_ground_stations.json"
    filename_point_of_presences = "data/constellation/starlink_pops.json"
    satellites = read_satellite_tles(filename_tles)
    ground_stations = read_ground_stations(filename_ground_stations)
    point_of_presences = read_point_of_presences(filename_point_of_presences)

    # Simulation time settings
    time_start = ephem.Date("2024/08/12 20:00:00")
    verbose_print("simulation starts at", time_start, level = 1)
    time_end = ephem.Date(time_start + 4 * ephem.hour)
    verbose_print("simulation ends at", time_end, level = 1)
    time_step = 120
    verbose_print("simulation time step is", time_step, "seconds", level = 1)
    circuit_range = (0, 20000)
    verbose_print("simulation circuit number is", circuit_range, level = 1)
    circuit_group_size = 2500

    # Link availability settings
    if routing_strategy == "single-bent-pipe":
        link_connectivity = {
            "SRC_DST_LINK": False,
            "SRC_SAT_LINK": True,
            "SAT_SAT_LINK": False,
            "SAT_GS_LINK": True,
            "GS_POP_LINK": True,
            "GS_SAT_LINK": False,
            "GS_DST_LINK": False,
            "POP_DST_LINK": True
        }
    elif routing_strategy == "ISL-enabled":
        link_connectivity = {
            "SRC_DST_LINK": False,
            "SRC_SAT_LINK": True,
            "SAT_SAT_LINK": True,
            "SAT_GS_LINK": True,
            "GS_POP_LINK": True,
            "GS_SAT_LINK": False,
            "GS_DST_LINK": False,
            "POP_DST_LINK": True
        }
    else:
        raise ValueError("Unknown routing strategy")

    # Start simulation
    for i in range(circuit_range[0], circuit_range[1], circuit_group_size):
        circuit_group_range = (i, i + circuit_group_size)
        record_file_name = ("sim_" + str(time.time()) +
                            "_" + gs_satellite_link_mode +
                            "_" + routing_strategy +
                            "_" + dataset +
                            "_" + str(circuit_group_range[0]) + "-" + str(circuit_group_range[1]) +
                            ".txt")
        tor_client_server_info = [
            {
                "role": "client",
                "city": CITIES[i // circuit_group_size],
                "lat": CITIES_LATS[i // circuit_group_size],
                "lon": CITIES_LONS[i // circuit_group_size],
                "country_code": CITIES_COUNTRY_CODES[i // circuit_group_size]
            }
        ]

        if if_record_sim_result:
            with open(sim_result_filedir + record_file_name, 'a') as sim_record_file:
                sim_record_file.write("simulation starts at " + str(time_start) + "\n")
                sim_record_file.write("simulation ends at " + str(time_end) + "\n")
                sim_record_file.write("simulation time step is " + str(time_step) + " seconds \n")
                sim_record_file.write("simulation satellite number is " + str(len(satellites)) + "\n")
                sim_record_file.write("simulation ground station number is " + str(len(ground_stations)) + "\n")
                sim_record_file.write("simulation PoP number is " + str(len(point_of_presences)) + "\n")
                sim_record_file.write("Simulation client/server information is " + str(tor_client_server_info) + "\n")
                sim_record_file.write("Simulation routing strategy is " + routing_strategy + "\n")
                sim_record_file.write("Simulation gs-satellite link mode is " + gs_satellite_link_mode + "\n")
                sim_record_file.write("Simulation dataset is " + dataset + "\n")

        extended_geo_circuits = get_extend_circuits_with_geo_client_server(filename_tor_circuits,
                                                                           filename_geoip_dataset,
                                                                           tor_client_server_info,
                                                                           circuit_group_range)
        hops, hops_count = parse_hops_in_circuits(extended_geo_circuits)

        time_cursor = time_start
        t_index = 0
        while time_cursor < time_end:
            verbose_print("Simulating the", t_index, "th time point, time is", str(ephem.Date(time_cursor)), level = 1)
            time_point_start = time.time()
            simulation_results_time_t = path_simulate_one_time_many_hops(hops = hops,
                                                                         satellites = satellites,
                                                                         ground_stations = ground_stations,
                                                                         point_of_presences = point_of_presences,
                                                                         current_date_time_string = str(ephem.Date(time_cursor)),
                                                                         link_connectivity = link_connectivity,
                                                                         gs_satellite_link_mode = gs_satellite_link_mode,
                                                                         sat_ecdf = satellite_speed_ecdf,
                                                                         ter_ecdf = terrestrial_speed_ecdf)
            if if_record_sim_result:
                with open(sim_result_filedir + record_file_name, 'a') as sim_record_file:
                    sim_record_file.write(json.dumps(simulation_results_time_t) + '\n')
            time_point_end = time.time()
            verbose_print("Simulation time point", t_index, "takes", time_point_end - time_point_start, "seconds", level = 1)

            time_cursor += time_step * ephem.second
            t_index += 1




