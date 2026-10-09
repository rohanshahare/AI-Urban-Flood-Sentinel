
from datetime import datetime, timezone
from history import assess_with_history

TREND_DELTA = 5
_LOG = {}


def reset_log():
    _LOG.clear()


def assess_with_trend(data: dict) -> dict:
    result = assess_with_history(data)
    result["trend"] = {
        "direction": "UNKNOWN",
        "change": None,
        "previous_score": None,
    }

    if result["status"] != "OK" or result["drain_id"] is None:
        return result

    score = result["flood_risk_score"]
    if not isinstance(score, (int, float)) or isinstance(score, bool):
        return result

    log = _LOG.setdefault(result["drain_id"], [])

    if not log:
        result["trend"]["direction"] = "NEW"
    else:
        previous = log[-1]["score"]
        change = score - previous

        if change >= TREND_DELTA:
            direction = "RISING"
        elif change <= -TREND_DELTA:
            direction = "FALLING"
        else:
            direction = "STABLE"

        result["trend"] = {
            "direction": direction,
            "change": change,
            "previous_score": previous,
        }

    log.append({
        "time": datetime.now(timezone.utc).isoformat(),
        "score": score,
    })
    return result
