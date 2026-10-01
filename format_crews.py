import json
from pathlib import Path

CREWS_PATH = Path("inputdata/crews.json")


def format_crews(path=CREWS_PATH):
    """Rewrite crews.json in place: [{"CREW_NAME": "Service Hub"}, ...] -> ["service hub", ...]."""
    with open(path, encoding="utf-8") as f:
        crews = json.load(f)

    names = [crew["CREW_NAME"].strip().lower() for crew in crews]

    with open(path, "w", encoding="utf-8") as f:
        json.dump(names, f, indent=2, ensure_ascii=False)
        f.write("\n")

    return names


if __name__ == "__main__":
    format_crews()
