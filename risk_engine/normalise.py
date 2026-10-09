
from .config import RAIN_BANDS, RAIN_VALUE, HISTORY_VALUE


def is_number(value):
    """Check for a number, excluding booleans."""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
    )


def normalize_blockage(value):
    """Validate blockage and normalize it to 0-1."""
    if not is_number(value) or not 0 <= value <= 100:
        raise ValueError(
            "blockage_percentage must be a number from 0 to 100"
        )
    return value / 100.0


def normalize_rainfall(value):
    """Return rainfall category and normalized value."""
    if value is None:
        return None, None

    if is_number(value) and value >= 0:
        for upper_bound, category, normalized in RAIN_BANDS:
            if value < upper_bound:
                return category, normalized

        return None, None

    if isinstance(value, str):
        category = value.strip().upper().replace(" ", "_")
        if category in RAIN_VALUE:
            return category, RAIN_VALUE[category]

    return None, None


def normalize_history(value):
    """Normalize historical vulnerability."""
    if not isinstance(value, str):
        return None

    category = value.strip().upper()
    return HISTORY_VALUE.get(category)
