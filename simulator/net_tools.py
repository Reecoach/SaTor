# net_tools.py
# Online retrieval of network-related data

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from typing import Dict, Tuple, List

import requests
from requests.adapters import HTTPAdapter, Retry
from stem.descriptor.remote import DescriptorDownloader

from utils import verbose_print


# ----------------------------- HTTP Session with Retries ----------------------------- #

def _make_session(total_retries: int = 3, backoff_factor: float = 0.5, timeout: int = 10) -> requests.Session:
    """
    Build a requests Session with retry and sane defaults.

    Returns:
        Configured requests.Session
    """
    sess = requests.Session()
    retries = Retry(
        total=total_retries,
        connect=total_retries,
        read=total_retries,
        backoff_factor=backoff_factor,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retries, pool_connections=20, pool_maxsize=50)
    sess.mount("http://", adapter)
    sess.mount("https://", adapter)
    sess.request = _with_timeout(sess.request, default_timeout=timeout)
    return sess

def _with_timeout(request_func, default_timeout: int):
    def wrapped(method, url, **kwargs):
        if "timeout" not in kwargs:
            kwargs["timeout"] = default_timeout
        return request_func(method, url, **kwargs)
    return wrapped


_HTTP = _make_session()

# ----------------------------- External APIs ----------------------------- #


def try_get_current_tor_consensus(filename_tor_consensus: str) -> None:
    """
    Fetch current Tor consensus and dump essential fields to JSON.

    Args:
        filename_tor_consensus: output file path

    Side Effects:
        Writes a compact JSON mapping fingerprint -> fields.
    """
    downloader = DescriptorDownloader()
    query = downloader.get_consensus()
    consensus = query.run()
    relays = {}
    for router in consensus:
        relays[router.fingerprint] = {
            "ip": router.address,
            "nickname": router.nickname,
            "or_port": router.or_port,
            "dir_port": router.dir_port,
            "flags": list(router.flags) if hasattr(router, "flags") else [],
            "bandwidth": getattr(router, "bandwidth", None),
        }
    with open(filename_tor_consensus, "w", encoding="utf-8") as tc_file:
        json.dump(relays, tc_file, ensure_ascii=False)


def try_get_current_starlink_TLE(filename_starlink_TLE: str) -> None:
    """
    Download Starlink TLE file from CelesTrak and write it to disk.

    Args:
        filename_starlink_TLE: output file path
    """
    from CONSTANTS import URL_TLE
    url = URL_TLE
    resp = _HTTP.get(url, timeout=15)
    if resp.status_code == 200 and resp.text:
        # normalize CRLF to LF
        text = resp.text.replace("\r", "")
        with open(filename_starlink_TLE, "w", encoding="utf-8") as st_file:
            st_file.write(text)
    else:
        verbose_print("failed to get TLE response.", level=3)


def extract_ground_stations_from_kml_file(filename_kml: str) -> Tuple[List[Dict], List[Dict]]:
    """
    Parse a KML file to extract ground stations and PoPs.
    You can get KML file from https://pan.uvic.ca/~clarkzjw/starlink/
    Args:
        filename_kml: KML path (exported from starlinkinsider map)

    Returns:
        (pops, ground_stations) lists of dicts
    """
    tree = ET.parse(filename_kml)
    root = tree.getroot()
    ns = {'kml': 'http://www.opengis.net/kml/2.2'}

    gs_info_results: List[Dict] = []
    pop_info_results: List[Dict] = []

    for folder in root.findall('.//kml:Folder', ns):
        folder_name_el = folder.find('./kml:name', ns)
        folder_name = folder_name_el.text if folder_name_el is not None else ""
        # PoPs & Backbone
        if folder_name.strip() == "PoPs & Backbone":
            for pop in folder.findall('./kml:Placemark', ns):
                name_el = pop.find('./kml:name', ns)
                point_el = pop.find('./kml:Point', ns)
                coord_el = point_el.find('./kml:coordinates', ns) if point_el is not None else None
                if name_el is None or coord_el is None:
                    continue
                try:
                    lng, lat, alt = [float(num) for num in coord_el.text.strip().split(',')]
                except Exception:
                    continue
                pop_info_results.append({"name": name_el.text.strip(), "lat": lat, "lng": lng, "alt": alt})
        else:
            for gs in folder.findall('./kml:Placemark', ns):
                name_el = gs.find('./kml:name', ns)
                point_el = gs.find('./kml:Point', ns)
                coord_el = point_el.find('./kml:coordinates', ns) if point_el is not None else None
                if name_el is None or coord_el is None:
                    continue
                try:
                    lng, lat, alt = [float(num) for num in coord_el.text.strip().split(',')]
                except Exception:
                    continue
                gs_info_results.append({
                    "continent": folder_name.strip(),
                    "name": name_el.text.strip(),
                    "lat": lat, "lng": lng, "alt": alt
                })

    verbose_print("Get", len(pop_info_results), "PoPs.", level=1)
    verbose_print("Get", len(gs_info_results), "ground stations.", level=1)
    return pop_info_results, gs_info_results


