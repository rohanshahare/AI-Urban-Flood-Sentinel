
from history import assess_with_history

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
