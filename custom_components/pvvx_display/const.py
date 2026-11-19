"""Constants for the PVVX display integration."""

DOMAIN = "pvvx_display"
SERVICE_SHOW = "show"

# Option/field keys shared between the service, options flow and auto-update.
CONF_BIG_NUMBER = "big_number"
CONF_BIG_NUMBER_ENTITY = "big_number_entity"
CONF_SMALL_NUMBER = "small_number"
CONF_SMALL_NUMBER_ENTITY = "small_number_entity"
CONF_VALIDITY_PERIOD = "validity_period"
CONF_UNIT = "unit"
CONF_HAPPY = "happy"
CONF_SAD = "sad"
CONF_BRACKET = "bracket"
CONF_PERCENT = "percent"
CONF_BATTERY = "battery"
CONF_AUTO_UPDATE = "auto_update"
CONF_PERMANENT = "permanent"
CONF_KEEP_ALIVE = "keep_alive"
CONF_MIN_UPDATE_INTERVAL = "min_update_interval"

DEFAULT_VALIDITY_PERIOD = 300
# Minimum seconds between automatic pushes; rapid changes are coalesced.
DEFAULT_MIN_UPDATE_INTERVAL = 60
# Firmware v4.4+ shows only the external data, until reboot, for this validity
# value. Any other value alternates with the device's own readings every 2.5 s.
PERMANENT_VALIDITY_PERIOD = 65535
# Permanent mode holds the value on screen, so refresh only to recover after a
# device reboot.
PERMANENT_KEEPALIVE_SECONDS = 3600
# Non-permanent mode: refresh this many seconds before the value expires.
REFRESH_MARGIN_SECONDS = 30
MIN_REFRESH_SECONDS = 30

CHARACTERISTIC_UUID = "00001f1f-0000-1000-8000-00805f9b34fb"
# Hold the link briefly so a write without response is sent before closing.
DISCONNECT_DELAY_SECONDS = 2
# Every Bluetooth call is bounded so a stuck call cannot hold the device lock.
# Keep the disconnect timeout generous: a cancelled disconnect leaks a D-Bus
# connection (home-assistant/core#179152).
WRITE_TIMEOUT_SECONDS = 10
DISCONNECT_TIMEOUT_SECONDS = 15

UNIT_VALUES = {
    "none": 0,
    "degree_ghe": 1,
    "minus": 2,
    "fahrenheit": 3,
    "low_dash": 4,
    "celsius": 5,
    "lines": 6,
    "degree_e": 7,
}

# UI labels for the firmware unit codes, in display order. Keys match UNIT_VALUES.
UNIT_LABELS = {
    "none": "None",
    "celsius": "Celsius (°C)",
    "fahrenheit": "Fahrenheit (°F)",
    "degree_e": "Degree (°E)",
    "degree_ghe": "Degree (°Г)",
    "minus": "Minus (-)",
    "low_dash": "Underscore (_)",
    "lines": "Lines (=)",
}
