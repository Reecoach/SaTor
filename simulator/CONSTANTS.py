# constant values used throughout the application.

# ------------------------- URLS ------------------------- #
URL_TLE = "https://celestrak.org/NORAD/elements/gp.php?GROUP=starlink&FORMAT=tle"

EARTH_RADIUS = 6_378_135  # meters
LEO_ALTITUDE = 550_000  # meters (550 km)

# ------------------- SIMULATION CONFIGS ------------------- #
MAX_GSL_DISTANCE = 1_123_000
MAX_ISL_DISTANCE = 5_016_591

LIGHT_SPEED = 299_792_458 # meters per second, theoretical maximum light speed in vacuum, but we don't use it directly
TERRESTRIAL_TRANS_SPEED = LIGHT_SPEED * 2 / 3

STEP_TERRESTRIAL_DISTANCE = 1_000_000
UP_TERRETRIAL_DISTANCE = 10_000_000

MAX_ISL_INTERFACE_NUM = 4