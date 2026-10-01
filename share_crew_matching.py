"""Export the crew-matching data as CSV/JSON files.

Writes into data/:
- close_matchings.csv: "raw text", "mapped crew" (from close_naming.json)
- empty_matches.csv: "SFA headers", unique case-insensitive (from empty_matching.json)
- unique_crews.json / unique_crews.csv: distinct crew_allocation values in
  header_crews.json, most-used first
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"


def export_matching_csvs(data_dir: Path = DATA_DIR, output_dir: Path = DATA_DIR) -> None:
    """Write close_matchings.csv and empty_matches.csv from the matching JSON files."""
    close_naming = json.loads((data_dir / "close_naming.json").read_text(encoding="utf-8"))
    empty_matching = json.loads((data_dir / "empty_matching.json").read_text(encoding="utf-8"))

    with open(output_dir / "close_matchings.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["raw text", "mapped crew"])
        writer.writerows(close_naming.items())

    # Unique headers, case-insensitive (first spelling wins, order preserved)
    unique_headers = {}
    for header in empty_matching:
        unique_headers.setdefault(header.casefold(), header)

    with open(output_dir / "empty_matches.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["SFA headers"])
        writer.writerows([h] for h in unique_headers.values())


def collect_crews(path: Path = DATA_DIR / "header_crews.json") -> list[str]:
    """List the distinct crew_allocation values, most-used first.

    Headers with no allocation (null) are skipped, as are blank strings.
    """
    with open(path, encoding="utf-8") as fh:
        header_crews = json.load(fh)

    counts = {}
    for entry in header_crews.values():
        crew = (entry.get("crew_allocation") or "").strip()
        if not crew:
            continue
        counts[crew] = counts.get(crew, 0) + 1
    # Most-used crews first; ties keep the order they were first seen in.
    return [crew for crew, _ in sorted(counts.items(), key=lambda item: -item[1])]


def export_unique_crews(data_dir: Path = DATA_DIR, output_dir: Path = DATA_DIR) -> list[str]:
    """Write unique_crews.json and unique_crews.csv; return the crews."""
    crews = collect_crews(data_dir / "header_crews.json")

    with open(output_dir / "unique_crews.json", "w", encoding="utf-8") as fh:
        json.dump(crews, fh, indent=2, ensure_ascii=False)

    with open(output_dir / "unique_crews.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["crew"])
        writer.writerows([c] for c in crews)

    return crews


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--out-dir", type=Path, default=DATA_DIR)
    args = parser.parse_args()

    export_matching_csvs(args.data_dir, args.out_dir)
    crews = export_unique_crews(args.data_dir, args.out_dir)
    print(f"Wrote CSVs and {len(crews)} unique crew(s) -> {args.out_dir}")


if __name__ == "__main__":
    main()
