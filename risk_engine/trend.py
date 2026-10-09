
from collections import OrderedDict, deque
from datetime import datetime, timezone
from .history import assess_with_history

TREND_DELTA = 5

# shortcut: process-local, in-memory log; lost on restart and not shared
# between workers. Bounded so arbitrary drain IDs cannot grow it forever.
# Upgrade to a database if trends must survive restarts.
MAX_READINGS_PER_DRAIN = 20
MAX_DRAINS = 500
_LOG = OrderedDict()


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

    drain_id = result["drain_id"]
    log = _LOG.setdefault(drain_id, deque(maxlen=MAX_READINGS_PER_DRAIN))
    _LOG.move_to_end(drain_id)
    if len(_LOG) > MAX_DRAINS:
        _LOG.popitem(last=False)

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
