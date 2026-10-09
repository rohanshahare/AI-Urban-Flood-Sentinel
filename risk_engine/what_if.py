
from .history import assess_with_history

SCENARIOS = [
    ("NONE", 1),
    ("LIGHT", 10),
    ("MODERATE", 40),
    ("HEAVY", 90),
    ("VERY_HEAVY", 150),
    ("EXTREMELY_HEAVY", 250),
]


def what_if(drain: dict):
    rows = []

    for category, rainfall_mm in SCENARIOS:
        result = assess_with_history({
            **drain,
            "rainfall": rainfall_mm,
        })

        rows.append((
            category,
            rainfall_mm,
            result["flood_risk_score"],
            result["risk_level"],
        ))

    return rows


_COMPARED_INPUTS = ("blockage_percentage", "rainfall")


def simulate(baseline: dict, scenario: dict) -> dict:
    """Score a drain twice, as-is and with `scenario` inputs overridden.

    Uses the real scoring path (assess_with_history) and never touches the
    trend log, so a hypothetical run cannot change recorded history.
    """
    base = assess_with_history(baseline)
    hypo = assess_with_history({**baseline, **scenario})
    if base["status"] != "OK" or hypo["status"] != "OK":
        raise ValueError("; ".join(base["warnings"] + hypo["warnings"]))

    merged = {**baseline, **scenario}
    changed = [
        {"input": name, "from": baseline.get(name), "to": merged.get(name)}
        for name in _COMPARED_INPUTS
        if merged.get(name) != baseline.get(name)
    ]
    return {
        "baseline": base,
        "scenario": hypo,
        "change": {
            "score_delta": hypo["flood_risk_score"] - base["flood_risk_score"],
            "level_from": base["risk_level"],
            "level_to": hypo["risk_level"],
            "level_changed": base["risk_level"] != hypo["risk_level"],
            "changed_inputs": changed,
        },
    }


if __name__ == "__main__":
    drain = {
        "drain_id": "D-017",
        "location": "Ward 12",
        "blockage_percentage": 82,
        "confidence": 0.91,
    }

    print(
        f"Rainfall scenarios for {drain['drain_id']} "
        f"({drain['blockage_percentage']}% blockage)"
    )
    print(f"{'Category':<20}{'mm/day':>8}{'Score':>8}  Level")

    for category, mm, score, level in what_if(drain):
        print(f"{category:<20}{mm:>8}{score:>8}  {level}")
