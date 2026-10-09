
from .config import (
    WEIGHTS,
    RAIN_VALUE,
    RAIN_ORDER,
    HISTORY_VALUE,
    LEVELS,
    LEVEL_ORDER,
    RECOMMENDATIONS,
    OVERRIDE_BLOCKAGE,
    OVERRIDE_MIN_RAIN,
    OVERRIDE_MIN_LEVEL,
    LOW_CONFIDENCE,
    DEFAULT_RAIN_IF_MISSING,
)

from .normalise import (
    is_number,
    normalize_blockage,
    normalize_rainfall,
    normalize_history,
)


def blockage_label(value):
    if value <= 30:
        return "LOW"
    if value <= 60:
        return "MODERATE"
    if value <= 80:
        return "HIGH"
    return "SEVERE"


def assess_flood_risk(data: dict) -> dict:
    """Assess flood risk from blockage, rainfall and history."""

    warnings = []

    result = {
        "drain_id": data.get("drain_id"),
        "location": data.get("location"),
        "flood_risk_score": None,
        "risk_level": None,
        "risk_factors": [],
        "recommendation": None,
        "warnings": warnings,
        "status": "OK",
    }

    # 1. Blockage is mandatory
    try:
        blockage = normalize_blockage(
            data.get("blockage_percentage")
        )
    except ValueError as error:
        result["status"] = "ERROR"
        result["recommendation"] = (
            "Manual inspection required due to invalid input"
        )
        warnings.append(str(error))
        return result

    raw_blockage = data["blockage_percentage"]

    # 2. Normalize rainfall
    raw_rainfall = data.get("rainfall")
    rain_category, rain_value = normalize_rainfall(raw_rainfall)

    if rain_category is None:
        rain_category = DEFAULT_RAIN_IF_MISSING
        rain_value = RAIN_VALUE[rain_category]
        warnings.append(
            f"Rainfall unavailable or invalid - assumed "
            f"{rain_category} (cautious default)."
        )
        rainfall_text = f"Rainfall: {rain_category} (ASSUMED)"
    else:
        if is_number(raw_rainfall):
            rainfall_text = (
                f"Rainfall: {rain_category} "
                f"({raw_rainfall:g} mm/day)"
            )
        else:
            rainfall_text = f"Rainfall: {rain_category}"

    # 3. Normalize historical vulnerability
    raw_history = data.get("history")
    history_value = normalize_history(raw_history)

    history_category = (
        raw_history.strip().upper()
        if isinstance(raw_history, str)
        else None
    )

    if history_category not in HISTORY_VALUE:
        if raw_history is not None:
            warnings.append(
                f"Invalid history value {raw_history!r} ignored."
            )

        history_category = None
        history_value = None
        warnings.append(
            "Historical data unavailable - score based on "
            "blockage and rainfall."
        )

    # 4. Weighted score using available factors
    parts = [
        (blockage, WEIGHTS["blockage"]),
        (rain_value, WEIGHTS["rainfall"]),
    ]

    if history_value is not None:
        parts.append((history_value, WEIGHTS["history"]))

    total_weight = sum(weight for _, weight in parts)

    score = 100 * sum(
        value * weight for value, weight in parts
    ) / total_weight

    score = max(0, min(100, int(round(score))))

    # 5. Determine risk level
    risk_level = next(
        name for limit, name in LEVELS
        if score <= limit
    )

    # Safety override: high blockage plus heavy rainfall
    if (
        raw_blockage >= OVERRIDE_BLOCKAGE
        and RAIN_ORDER.index(rain_category)
        >= RAIN_ORDER.index(OVERRIDE_MIN_RAIN)
        and LEVEL_ORDER.index(risk_level)
        < LEVEL_ORDER.index(OVERRIDE_MIN_LEVEL)
    ):
        risk_level = OVERRIDE_MIN_LEVEL
        warnings.append(
            "Level raised by safety rule: "
            "severe blockage plus heavy rain."
        )

    # 6. Explain contributing factors
    result["risk_factors"] = [
        f"Blockage severity: "
        f"{blockage_label(raw_blockage)} ({raw_blockage:g}%)",
        rainfall_text,
        (
            f"Historical vulnerability: {history_category}"
            if history_category
            else "Historical vulnerability: UNAVAILABLE"
        ),
    ]

    # 7. Check detection confidence
    confidence = data.get("confidence")

    if confidence is not None:
        if not is_number(confidence) or not 0 <= confidence <= 1:
            warnings.append(
                f"Invalid confidence {confidence!r} ignored."
            )
        elif confidence < LOW_CONFIDENCE:
            warnings.append(
                "Low detection confidence - "
                "manual verification recommended."
            )

    # 8. Label synthetic data honestly
    if str(data.get("data_source", "")).upper() == "SYNTHETIC":
        warnings.append(
            "Contains SYNTHETIC data - "
            "not real city measurements."
        )

    # 9. Return the result
    result.update({
        "flood_risk_score": score,
        "risk_level": risk_level,
        "recommendation": RECOMMENDATIONS[risk_level],
    })

    return result

