import traceback

from stem.descriptor.remote import DescriptorDownloader
import xml.etree.ElementTree as ET
from geopy.geocoders import Photon, Nominatim
import requests
import json
import time
from utils import read_tor_circuits, read_geoip_dataset, verbose_print, renew_geoip_dataset

## Some tools to retrieve data from the internet, or parse data from downloaded files ##

def try_request_api_for_coords(ip: str, sleep: int = 2):
    # input: ip address
    # output: latitude and longitude, if not found, return None, None
    query_url = "http://ip-api.com/json/" + ip
    geoip_response = requests.get(query_url)
    # don't too fast
    time.sleep(sleep)
    try:
        data = json.loads(geoip_response.text)
        return data["lat"], data["lon"]
    except:
        return None, None

def try_request_api_for_detail_address(lat: float, lon: float):
    # input: latitude and longitude
    # output: detail address and country code, if not found, return None
    try:
        # geolocator = Photon(user_agent = "measurements")
        geolocator = Nominatim(user_agent = "measurements")
        location = geolocator.reverse((lat, lon))
        address = location.address
        country_code = location.raw.get('address', {}).get('country_code').upper()
    except:
        traceback.print_exc()
        address = None
        country_code = None
    return address, country_code

def retrieve_relay_geo_location(relay: list, ip: str, filename_geoip_dataset: str):
    # input: relays' info, ip address, filename of geoip dataset
    # output: relay info with geo-location, save new info to dataset file
    geo_relay = relay.copy()
    # try to search whether the ip is in current dataset
    relay_geoip_dataset = read_geoip_dataset(filename_geoip_dataset)
    if ip in relay_geoip_dataset.keys():
        lat = relay_geoip_dataset[ip][0]
        lon = relay_geoip_dataset[ip][1]
        address = relay_geoip_dataset[ip][2]
        country_code = relay_geoip_dataset[ip][3]
        geo_relay += [lat, lon, address, country_code]
    # if not, request web api for geo
    else:
        verbose_print("Requesting api for geo of ip", ip, level = 1)
        maybe_lat, maybe_lon = try_request_api_for_coords(ip, sleep = 2)
        # request success
        if maybe_lat != None and maybe_lon != None:
            geo_relay += [maybe_lat, maybe_lon]
            # request more information and save to dataset
            address, country_code = try_request_api_for_detail_address(maybe_lat, maybe_lon)
            if address != None and country_code != None:
                geo_relay += [address, country_code]
                # save new relay info to file
                renew_geoip_dataset(filename_geoip_dataset, new_record = {
                    "ip": ip,
                    "lat": maybe_lat,
                    "lon": maybe_lon,
                    "address": address,
                    "country_code": country_code
                })
            else:
                verbose_print("Requesting api for detail address falied.", level = 3)
                geo_relay += ["unknown", "unknown"]
                renew_geoip_dataset(filename_geoip_dataset, new_record = {
                    "ip": ip,
                    "lat": maybe_lat,
                    "lon": maybe_lon,
                    "address": "unknown",
                    "country_code": "unknown"
                })
        # request failed
        else:
            verbose_print("Requesting api falied. Lat and Lon are set to -1", level = 3)
            geo_relay += [-1, -1, "unknown", "unknown"]
    return geo_relay

def retrieve_circuit_geo_location(circuit, filename_geoip_dataset: str):
    result = list()
    for relay_info in circuit:
        geo_relay_info = retrieve_relay_geo_location(relay_info, relay_info[2], filename_geoip_dataset)
        result.append(geo_relay_info)
    return result

def try_get_current_tor_consensus(filename_tor_consensus: str):
    # input: filename to save consensus data
    # just get the consensus data from tor network
    downloader = DescriptorDownloader()
    query = downloader.get_consensus()
    consensus = query.run()
    relays = dict()
    for router in consensus:
        relays[router.fingerprint] = {
            "ip": router.address,
            "nickname": router.nickname,
            "or_port": router.or_port,
            "dir_port": router.dir_port,
            "flags": router.flags,
            "bandwidth": router.bandwidth
        }
    with open(filename_tor_consensus, 'w') as tc_file:
        tc_file.write(json.dumps(relays))

def try_get_current_starlink_TLE(filename_starlink_TLE: str):
    # input: filename to save TLE data
    # just get the TLE data from celestrak url as provided
    TLE_data = requests.get("https://celestrak.org/NORAD/elements/gp.php?GROUP=starlink&FORMAT=tle")
    if TLE_data.status_code == 200:
        with open(filename_starlink_TLE, 'w') as st_file:
            st_file.write(TLE_data.text.replace('\r',''))
    else:
        verbose_print("failed to get TLE response.", level = 3)

def extract_ground_stations_from_kml_file(filename_kml: str):
    # input: filename of kml file
    # output: list of ground stations, and PoPs
    # use the map get in https://starlinkinsider.com/ to get the info of ground stations
    tree = ET.parse(filename_kml)
    root = tree.getroot()
    namespace = {'kml': 'http://www.opengis.net/kml/2.2'}
    gs_info_results = list()
    PoP_info_results = list()
    for folder in root.findall('.//kml:Folder', namespace):
        folder_name = folder.find('.//kml:name', namespace).text
        if folder_name == "PoPs & Backbone":
            for pop in folder.findall('.//kml:Placemark', namespace):
                pop_name = pop.find('.//kml:name', namespace).text
                pop_point = pop.find('.//kml:Point', namespace)
                if pop_point is not None and pop_name is not None:
                    pop_coord = pop_point.find('.//kml:coordinates', namespace).text
                    if pop_coord is not None:
                        parsed_pop_coords = [float(num) for num in pop_coord.strip().split(',')]
                        pop_info = {
                            "name": pop_name.strip(),
                            "lat": parsed_pop_coords[1],
                            "lng": parsed_pop_coords[0],
                            "alt": parsed_pop_coords[2]
                        }
                        PoP_info_results.append(pop_info)
        else:
            for gs in folder.findall('.//kml:Placemark', namespace):
                gs_name = gs.find('.//kml:name', namespace).text
                gs_point = gs.find('.//kml:Point', namespace)
                if gs_point is not None and gs_name is not None:
                    gs_coord = gs_point.find('.//kml:coordinates', namespace).text
                    if gs_coord is not None:
                        parsed_gs_coords = [float(num) for num in gs_coord.strip().split(',')]
                        gs_info = {
                            "continent": folder_name,
                            "name": gs_name.strip(),
                            "lat": parsed_gs_coords[1],
                            "lng": parsed_gs_coords[0],
                            "alt": parsed_gs_coords[2]
                        }
                        gs_info_results.append(gs_info)
    verbose_print("Get", len(PoP_info_results), "PoPs.", level = 1)
    verbose_print("Get", len(gs_info_results), "ground stations.", level = 1)
    return PoP_info_results, gs_info_results
def get_ting_pairs(filename_tor_circuits: list, num_limit: int = -1):
    # input: filename of tor circuits, number of pairs to get
    # output: the most frequent pairs of relays
    # extract the pairs (actually hops) of relays (src, dst) in circuits
    # exclusively for Ting measurement input
    pairs = dict()
    def insert_pair(pair: list, pairs: dict):
        for p in pairs.keys():
            if pair[0] in p and pair[1] in p:
                pairs[p] += 1
                return
        pairs[' '.join(pair)] = 1
    for filename in filename_tor_circuits:
        circuits = read_tor_circuits(filename)
        for circuit in circuits:
            for i in range(len(circuit) - 1):
                pair = [circuit[i][0], circuit[i + 1][0]]
                insert_pair(pair, pairs)
    sorted_pairs = sorted(pairs.items(), key = lambda x: x[1], reverse = True)
    return sorted_pairs[:num_limit if num_limit != -1 else len(sorted_pairs)]


def get_add_client_or_server_info(add_info: list):
    geolocator = Photon(user_agent = "measurements")
    results = list()
    for info in add_info:
        # fingerprint, nickname, ip, port, lat, lon
        res = ["unknown", "unknown", "unknown", -1, -1, -1, -1, -1]
        if "ip" in info.keys():
            res[2] = info["ip"]
            maybe_lat, maybe_lon = try_request_api_for_coords(info["ip"])
            if maybe_lat != None and maybe_lon != None:
                res[-2] = maybe_lat
                res[-1] = maybe_lon
                if "city" not in info.keys():
                    # reversely get city name using lat, lon
                    location = geolocator.reverse((lat, lon), exactly_one = True)
                    if location:
                        address = location.raw.get('address', {})
                        city = address.get('city', None)
                        res[1] = city
                    else:
                        raise RuntimeError("Location not found on coords", maybe_lat, maybe_lon)
                else:
                    res[1] = info["city"]
            else:
                raise RuntimeError("Cannot find the coordination of ip", info["ip"])

        elif "city" in info.keys():
            res[1] = info["city"]
            location = geolocator.geocode(info["city"])
            if location:
                lat = location.latitude
                lon = location.longitude
                res[-2] = lat
                res[-1] = lon
            else:
                raise RuntimeError("Cannot find the coordination of city", info["city"])
        else:
            raise RuntimeError("Cannot determine machine info", info)
        results.append(res)
    return results

def circuit_add_client_or_server(circuits: list, add_info: list):
    # Add a client or server in the circuit
    extended_circuits = list()
    # add_info_extended = get_add_client_or_server_info(add_info)
    for circuit in circuits:
        client_added = False
        server_added = False
        extended_circuit = circuit.copy()
        for i in range(len(add_info)):
            info = add_info[i]
            formated_info = [
                "unknown", # fingerprint
                info["city"], # name
                "unknown", # ip
                "unknown", # port
                info["lat"], # lat
                info["lon"], # lon
                "unknown", # address
                info["country_code"] # country_code
            ]
            if info["role"] == "client" and client_added == False:
                extended_circuit.insert(0, formated_info)
                client_added = True
            elif info["role"] == "server" and server_added == False:
                extended_circuit.append(formated_info)
                server_added = True
            else:
                raise ValueError("Unknown role to add.")
        extended_circuits.append(extended_circuit)
    return extended_circuits

def get_extend_circuits_with_geo_client_server(filename_tor_circuits: str, filename_geoip_dataset: str, add_info: list, circuits_range: list):
    raw_circuits = read_tor_circuits(filename_tor_circuits)
    geo_circuits = [retrieve_circuit_geo_location(circuit, filename_geoip_dataset) for circuit in raw_circuits[circuits_range[0]: circuits_range[1]]]
    extended_geo_circuits = circuit_add_client_or_server(geo_circuits, add_info)
    return extended_geo_circuits

