
# Flood Risk Engine configuration

WEIGHTS = {
    "blockage": 0.45,
    "rainfall": 0.35,
    "history": 0.20,
}

# (exclusive upper rainfall bound in mm/day, category, normalized value)
RAIN_BANDS = [
    (2.5, "NONE", 0.0),
    (15.6, "LIGHT", 0.2),
    (64.5, "MODERATE", 0.5),
    (115.6, "HEAVY", 0.8),
    (204.5, "VERY_HEAVY", 1.0),
    (float("inf"), "EXTREMELY_HEAVY", 1.0),
]

RAIN_VALUE = {
    name: value for _, name, value in RAIN_BANDS
}

RAIN_ORDER = [
    name for _, name, _ in RAIN_BANDS
]

HISTORY_VALUE = {
    "LOW": 0.3,
    "MEDIUM": 0.6,
    "HIGH": 0.9,
}

LEVELS = [
    (25, "LOW"),
    (50, "MODERATE"),
    (75, "HIGH"),
    (100, "CRITICAL"),
]

LEVEL_ORDER = [
    name for _, name in LEVELS
]

RECOMMENDATIONS = {
    "LOW": "Routine inspection",
    "MODERATE": "Schedule inspection within a few days",
    "HIGH": "Priority cleaning within 24 hours",
    "CRITICAL": "Urgent intervention immediately",
}

OVERRIDE_BLOCKAGE = 70
OVERRIDE_MIN_RAIN = "HEAVY"
OVERRIDE_MIN_LEVEL = "HIGH"

LOW_CONFIDENCE = 0.5
DEFAULT_RAIN_IF_MISSING = "MODERATE"
