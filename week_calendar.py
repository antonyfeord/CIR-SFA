"""Build a calendar CSV from sfa_matches: one row per alaner, one column per week.

Cell value = project if set, else crew if set, else "no-match:{text}".
"""

import csv
import json
import re
from pathlib import Path

MATCHES_DIR = Path(__file__).parent / "sfa_matches"
OUTPUT = Path(__file__).parent / "week_calendar.csv"


def cell_value(entry):
    project = (entry.get("project") or "").strip()
    if project:
        return project
    crew = (entry.get("crew") or "").strip()
    if crew:
        return crew
    text = re.sub(r"\s+", " ", (entry.get("text") or "")).strip()
    return f"no-match:{text}"


def main():
    rows = {}
    weeks = set()

    for path in sorted(MATCHES_DIR.glob("*.json")):
        alaner = path.stem
        cells = {}
        for entry in json.loads(path.read_text()):
            week = entry.get("week")
            if not week:
                continue
            weeks.add(week)
            value = cell_value(entry)
            # A few alaners posted twice in the same week: keep both.
            if week in cells and value != cells[week]:
                cells[week] = f"{cells[week]} | {value}"
            else:
                cells[week] = value
        rows[alaner] = cells

    # Sort numerically where the week looks like "W<n>", so unpadded or
    # 3-digit labels still order correctly; anything else goes last, by name.
    def week_key(week):
        match = re.fullmatch(r"[Ww](\d+)", week)
        return (0, int(match.group(1)), "") if match else (1, 0, week)

    week_cols = sorted(weeks, key=week_key)
    with OUTPUT.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["alaner"] + week_cols)
        for alaner, cells in sorted(rows.items()):
            writer.writerow([alaner] + [cells.get(w, "") for w in week_cols])

    print(f"Wrote {OUTPUT} — {len(rows)} rows x {len(week_cols)} weeks")


if __name__ == "__main__":
    main()
