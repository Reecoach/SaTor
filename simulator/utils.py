import json
import ephem
import math
from geopy.distance import great_circle
from statsmodels.distributions.empirical_distribution import ECDF
import numpy as np

EARTH_RADIUS = 6378135

GLOBAL_VERBOSE_LEVEL = 1
VERBOSE = ["DEBUG", "INFO", "WARNING", "ERROR", "FATAL"]



def verbose_print(*args, level: int = 1):
    if level >= GLOBAL_VERBOSE_LEVEL:
        msg = ' '.join([str(arg) for arg in args])
        print('[' + str(ephem.now()) + ']', VERBOSE[level] + ":", msg)


# -------------------- FILE IO METHODS ----------------------#
def read_tor_circuits(filename_tor_circuits: str):
    with open(filename_tor_circuits, 'r') as tc_file:
        circuits = json.loads(tc_file.read())
    verbose_print("Read", len(circuits), "circuits.", level = 1)
    return circuits

def read_tor_relays(filename_tor_relays: str):
    with open(filename_tor_relays, 'r') as tr_file:
        relays = json.loads(tr_file.read())
    verbose_print("Read", len(relays), "relays.", level = 1)
    return relays

def read_geoip_dataset(filename_geoip_dataset: str):
    with open(filename_geoip_dataset, 'r') as geo_dataset_file:
        geoips = json.loads(geo_dataset_file.read())
    return geoips

def renew_geoip_dataset(filename_geoip_dataset: str, new_record: dict):
    # new record is like: { "ip": xxx, "lat": xxx, "lon": xxx, "address": xxx, "country_code":xxx }
    with open(filename_geoip_dataset, 'r') as geo_dataset_file:
        geoips = json.loads(geo_dataset_file.read())
    geoips[new_record["ip"]] = [
        new_record["lat"],
        new_record["lon"],
        new_record["address"],
        new_record["country_code"]
    ]
    with open(filename_geoip_dataset, 'w') as geo_dataset_file:
        geo_dataset_file.write(json.dumps(geoips))

def read_satellite_tles(filename_tles: str):
    satellites = []
    with open(filename_tles, 'r') as f:
        for tles_line_1 in f:
            tles_line_2 = f.readline()
            tles_line_3 = f.readline()

            # Finally, store the satellite information
            satellites.append(ephem.readtle(tles_line_1, tles_line_2, tles_line_3))
    verbose_print("Read", len(satellites), "satellites.", level = 1)
    return satellites

def read_ground_stations(filename_gs: str):
    with open(filename_gs, 'r') as f_gs:
        gs_info = json.loads(f_gs.read())
    verbose_print("Read", len(gs_info), "ground stations.", level = 1)
    return gs_info

def read_point_of_presences(filename_pops: str):
    with open(filename_pops, 'r') as f_pops:
        pops_info = json.loads(f_pops.read())
    verbose_print("Read", len(pops_info), "PoPs.", level = 1)
    return pops_info

def read_starlink_region_prices(filename_starlink_rp: str):
    with open(filename_starlink_rp, 'r') as file_starlink_rp:
        starlink_region_prices = json.loads(file_starlink_rp.read())
    return starlink_region_prices

def read_starlink_region_performance(filename_starlink_rpf: str):
    with open(filename_starlink_rpf, 'r') as file_starlink_rpf:
        starlink_region_performance = json.loads(file_starlink_rpf.read())
    return starlink_region_performance

# -------------------- DISTANCE METHODS ----------------------#
# All in meters
def distance_between_ground_satellite(g_lat:float, g_lon: float, current_time_date_string: str, satellite):
    # Get the distance between a ground point to a satellite at a time point
    observer = ephem.Observer()
    observer.date = current_time_date_string
    observer.lat = g_lat
    observer.lon = g_lon
    # ignore elevation
    observer.elevation = 0

    satellite.compute(observer)
    return satellite.range

def distance_between_satellites(sat_1, sat_2, current_date_time_string: str):
    # Get the distance between two satellites at time point
    observer = ephem.Observer()
    observer.date = current_date_time_string

    sat_1.compute(observer)
    sat_2.compute(observer)

    angle_radians = float(repr(ephem.separation(sat_1, sat_2)))

    return math.sqrt(sat_1.range ** 2 + sat_2.range ** 2 - (2 * sat_1.range * sat_2.range * math.cos(angle_radians)))

def distance_between_ground_stations(g1_loc: list, g2_loc: list):
    # Get the distance between two ground points
    # Input: g1_loc: [lat, lon], g2_loc: [lat, lon]
    return great_circle(
        (float(g1_loc[0]), float(g1_loc[1])),
        (float(g2_loc[0]), float(g2_loc[1])),
        radius = EARTH_RADIUS / 1000 # in km
    ).m

def get_if_satellite_same_orbit(sat_1,
                                sat_2,
                                tolerance: dict = {"inc": 0.1, 'raan': 2},
                                orbit_elements: list = ['inc', 'raan']):
    # Judge whether two satellites are in the same orbits
    # Mainly use two parameters `Inclination (°)` and `Right Ascension of ascending node (°)`
    # Tolerance are empirical
    for element in orbit_elements:
        val_1 = getattr(sat_1, element)
        val_2 = getattr(sat_2, element)
        if abs(val_1 - val_2) > tolerance[element]:
            return False
    return True

def get_satellite_orbital_parameters(sat, elements: list = ["inc", "raan"]):
    return [getattr(sat, element) for element in elements]

def generate_circuit_id(circuit: list):
    cicuit_id = ""
    for relay in circuit:
        cicuit_id += relay[0] + ':' + relay[1] + '->'
    return cicuit_id[:-2]

def generate_hop_id(s_relay: list, d_relay: list):
    hop_id = s_relay[0] + ':' + s_relay[1] + '->' + d_relay[0] + ':' + d_relay[1]
    return hop_id

# -------------------- SAMPLING METHODS ----------------------#
LEO_ALTITUDE = 550 * 1000  # 550 km
def calculate_transmission_speed_satellite(coordinate_src: tuple, coordinate_dst: tuple, latency: float):
    # input: coordinate_src, coordinate_dst: (lat, lon), latency: in seconds
    # output: speed of transmission in m/s
    signal_journey_length = 2 * (((distance_between_ground_stations(coordinate_src, coordinate_dst) / 2) ** 2 + LEO_ALTITUDE ** 2) ** 0.5) # in meters
    return signal_journey_length / latency

def get_speed_ECDF(speeds: list):
    # speed in m/s
    ecdf = ECDF(speeds)
    return ecdf

def sample_speed(ecdf, range_limit: tuple = (-np.inf, np.inf)):
    # Sample a speed from the ECDF
    # in m/s
    u = np.random.uniform(0, 1)
    sampled_value = np.interp(u, ecdf.y, ecdf.x)
    while sampled_value < range_limit[0] or sampled_value > range_limit[1]:
        u = np.random.uniform(0, 1)
        sampled_value = np.interp(u, ecdf.y, ecdf.x)
    return sampled_value







