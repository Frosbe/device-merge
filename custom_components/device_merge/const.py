"""Constants for Device Merge."""

DOMAIN = "device_merge"

CONF_NAME = "name"
CONF_DEVICES = "devices"
CONF_MANUFACTURER = "manufacturer"
CONF_MODEL = "model"
CONF_PICTURE = "picture"
CONF_HIDE_SOURCES = "hide_sources"
CONF_TAKE_OVER_IDS = "take_over_ids"
CONF_ENTITIES = "entities"

# Per merged entity in CONF_ENTITIES
E_KEY = "key"
E_DOMAIN = "domain"
E_NAME = "name"
E_ENTITY_ID = "entity_id"
E_STRATEGY = "strategy"
E_SOURCES = "sources"  # list of [domain, platform, unique_id]

STRATEGY_FRESHEST = "freshest"
STRATEGY_PREFER = "prefer_first"
STRATEGY_MIN = "min"
STRATEGY_MAX = "max"
STRATEGY_MEAN = "mean"
STRATEGY_MEDIAN = "median"
STRATEGY_ANY = "any_on"
STRATEGY_ALL = "all_on"
STRATEGY_SEPARATE = "separate"
STRATEGY_SINGLE = "single"

STRATEGY_LABELS = {
    STRATEGY_FRESHEST: "Freshest (whoever reported last)",
    STRATEGY_PREFER: "Prefer first device, fall back to the next",
    STRATEGY_MIN: "Minimum",
    STRATEGY_MAX: "Maximum",
    STRATEGY_MEAN: "Mean",
    STRATEGY_MEDIAN: "Median",
    STRATEGY_ANY: "On if any is on",
    STRATEGY_ALL: "On only if all are on",
    STRATEGY_SEPARATE: "Keep separate (no merge)",
}

NUMERIC_STRATEGIES = [STRATEGY_FRESHEST, STRATEGY_PREFER, STRATEGY_MIN, STRATEGY_MAX, STRATEGY_MEAN, STRATEGY_MEDIAN, STRATEGY_SEPARATE]
ONOFF_STRATEGIES = [STRATEGY_FRESHEST, STRATEGY_PREFER, STRATEGY_ANY, STRATEGY_ALL, STRATEGY_SEPARATE]
OTHER_STRATEGIES = [STRATEGY_FRESHEST, STRATEGY_PREFER, STRATEGY_SEPARATE]

PLATFORMS = [
    "sensor",
    "binary_sensor",
    "switch",
    "button",
    "lock",
    "cover",
    "climate",
    "select",
    "number",
    "text",
    "update",
    "device_tracker",
]
