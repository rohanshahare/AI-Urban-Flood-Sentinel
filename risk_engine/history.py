
import csv
from pathlib import Path

from .engine import assess_flood_risk

CSV_PATH = (
    Path(__file__).parent
    / "data"
    / "synthetic_history.csv"
)


def vulnerability_label(floods, blockages, low_lying):
    """Convert historical facts into a vulnerability category."""

    points = (
        min(floods, 2)
        + (1 if low_lying else 0)
        + (1 if blockages >= 4 else 0)
    )

    if points >= 3:
        return "HIGH"
    if points == 2:
        return "MEDIUM"
    return "LOW"


def load_history(path=CSV_PATH):
    """Load synthetic history and index it by drain ID."""

    table = {}

    with open(path, newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)

        for row in reader:
            floods = int(row["previous_floods"])
            blockages = int(row["past_blockages"])
            low_lying = (
                row["low_lying"].strip().upper() == "Y"
            )

            table[row["drain_id"]] = {
                "vulnerability": vulnerability_label(
                    floods, blockages, low_lying
                ),
                "data_source": row["data_source"],
            }

    return table


_HISTORY = load_history()


def assess_with_history(data: dict) -> dict:
    """Use historical data when the caller has not supplied history."""

    data = dict(data)

    if data.get("history") is None:
        drain_id = data.get("drain_id")
        record = _HISTORY.get(drain_id) if isinstance(drain_id, str) else None

        if record:
            data["history"] = record["vulnerability"]
            data["data_source"] = record["data_source"]

    return assess_flood_risk(data)
