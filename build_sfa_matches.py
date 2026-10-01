import json
from pathlib import Path

RAW_DIR = Path("raw_sfas")
OUT_DIR = Path("sfa_matches")
HEADERS = Path("data/headers.json")
HEADER_CREWS = Path("data/header_crews.json")
CLASSIFIED = Path("data/conflicting_matching_classified.json")
CREW_PROJECTS = Path("inputdata/crew_project_mapping.json")


def build_sfa_matches(raw_dir=RAW_DIR, out_dir=OUT_DIR):
    out_dir.mkdir(exist_ok=True)

    for path in sorted(raw_dir.glob("*.json")):
        data = json.loads(path.read_text())
        messages = [
            {
                "text": m.get("text"),
                "ts": m.get("ts"),
                "week": m.get("week"),
                "crew": "",
                "project": "",
            }
            for m in data.get("messages", [])
        ]
        (out_dir / path.name).write_text(
            json.dumps(messages, indent=2, ensure_ascii=False)
        )

    print(f"Wrote {len(list(out_dir.glob('*.json')))} files to {out_dir}")


def fill_crews(out_dir=OUT_DIR, headers_path=HEADERS, header_crews_path=HEADER_CREWS):
    headers = json.loads(Path(headers_path).read_text())
    header_crews = json.loads(Path(header_crews_path).read_text())

    # ts -> crew_allocation, via the header each ts belongs to
    ts_to_crew = {}
    for header, ts_list in headers.items():
        crew = (header_crews.get(header) or {}).get("crew_allocation")
        if not crew:
            continue
        for ts in ts_list:
            ts_to_crew[ts] = crew

    filled = total = 0
    for path in sorted(Path(out_dir).glob("*.json")):
        entries = json.loads(path.read_text())
        for entry in entries:
            total += 1
            crew = ts_to_crew.get(entry.get("ts"))
            if crew:
                entry["crew"] = crew
                filled += 1
        path.write_text(json.dumps(entries, indent=2, ensure_ascii=False))

    print(f"Filled {filled}/{total} entries")


def fill_transitions(out_dir=OUT_DIR, headers_path=HEADERS, classified_path=CLASSIFIED):
    headers = json.loads(Path(headers_path).read_text())
    classified = json.loads(Path(classified_path).read_text())

    ts_to_crew = {}
    for item in classified.get("transition", []):
        crew = f'{item["from_crew"]} -> {item["to_crew"]}'
        for ts in headers.get(item["header"], []):
            ts_to_crew[ts] = crew
    for item in classified.get("single_crew_mismatch", []):
        for ts in headers.get(item["header"], []):
            ts_to_crew[ts] = item["crew"]
    for item in classified.get("multiple_crews", []):
        primary = item["primary_crew"]
        crews = [primary] + [c for c in item["crews"] if c != primary]
        for ts in headers.get(item["header"], []):
            ts_to_crew[ts] = " | ".join(crews)

    filled = 0
    for path in sorted(Path(out_dir).glob("*.json")):
        entries = json.loads(path.read_text())
        for entry in entries:
            crew = ts_to_crew.get(entry.get("ts"))
            if crew:
                entry["crew"] = crew
                filled += 1
        path.write_text(json.dumps(entries, indent=2, ensure_ascii=False))

    print(f"Filled {filled} conflicting-header entries")


def fill_projects(out_dir=OUT_DIR, mapping_path=CREW_PROJECTS):
    mapping = json.loads(Path(mapping_path).read_text())

    crew_to_project = {}
    for project, crews in mapping.items():
        for crew in crews:
            crew_to_project[crew.strip().lower()] = project

    filled = 0
    for path in sorted(Path(out_dir).glob("*.json")):
        entries = json.loads(path.read_text())
        for entry in entries:
            crew = entry.get("crew", "")
            # only single-crew entries, not "a -> b" transitions or "a | b" lists
            if not crew or "->" in crew or "|" in crew:
                continue
            project = crew_to_project.get(crew.strip().lower())
            if project:
                entry["project"] = project
                filled += 1
        path.write_text(json.dumps(entries, indent=2, ensure_ascii=False))

    print(f"Filled {filled} project entries")


if __name__ == "__main__":
    build_sfa_matches()
    fill_crews()
    fill_transitions()
    fill_projects()
