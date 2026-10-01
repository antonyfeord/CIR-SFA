"""Label each cached SFA with the ISO week it was posted in.

Weeks are numbered chronologically within their own ISO year, so the last week
of a year is W52 or W53 rather than rolling over into W1 of the next.

The ISO year is not always the calendar year: a week belongs to whichever year
holds most of its days, so 31/12/2024 is week 1 of 2025 and 01/01/2021 is week
53 of 2020. week_of returns the bare "W01" label; week_key pairs it with the
ISO year, which is what you want for sorting or grouping across years.

Running this file rewrites every raw_sfas/<handle>.json in place, adding the
week fields to each message. It is safe to run twice - relabelling an already
labelled file changes nothing.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone

OUT_DIR = "raw_sfas"


def week_of(entry):
    """The ISO week label for one cached message, e.g. "W13"."""
    iso = _isocalendar(entry)
    return f"W{iso.week:02d}"


def week_key(entry):
    """(iso_year, iso_week) for one message - sortable and unique across years."""
    iso = _isocalendar(entry)
    return iso.year, iso.week


def _isocalendar(entry):
    """ISO calendar tuple for a message, from its ts (authoritative) or date."""
    ts = entry.get("ts")
    if ts is not None:
        moment = datetime.fromtimestamp(float(ts), timezone.utc)
    else:
        moment = datetime.strptime(entry["date"], "%d/%m/%Y").replace(tzinfo=timezone.utc)
    return moment.isocalendar()


def add_weeks(messages):
    """Return the messages with a "week" field added, oldest first.

    The input is left untouched; each message is copied.
    """
    labelled = []
    for entry in messages:
        iso = _isocalendar(entry)
        labelled.append({**entry, "week": f"W{iso.week:02d}", "iso_year": iso.year})
    labelled.sort(key=lambda entry: (entry["iso_year"], entry["week"]))
    return labelled


def label_file(path):
    """Add the week fields to one cached file, in place. Returns the count."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)

    data["messages"] = add_weeks(data["messages"])

    # Written to a temp name first so an interrupt cannot leave a half file
    # in place of the cache it was rewriting.
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, path)
    return len(data["messages"])


def duplicate_weeks(messages):
    """Weeks holding more than one message: {(iso_year, week): [messages]}.

    Grouped on the ISO year as well as the week, since two messages a year
    apart share a week label without falling in the same week.
    """
    by_week = {}
    for entry in messages:
        by_week.setdefault((entry["iso_year"], entry["week"]), []).append(entry)
    return {week: found for week, found in by_week.items() if len(found) > 1}


def label_all(out_dir=OUT_DIR):
    """Add the week fields to every cached file. Returns {handle: count}."""
    counts, clashes = {}, {}
    names = sorted(n for n in os.listdir(out_dir) if n.endswith(".json"))
    for name in names:
        handle = name[: -len(".json")]
        path = os.path.join(out_dir, name)
        counts[handle] = label_file(path)
        with open(path, encoding="utf-8") as fh:
            found = duplicate_weeks(json.load(fh)["messages"])
        if found:
            clashes[handle] = found
    return counts, clashes


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=OUT_DIR, help=f"cache directory (default {OUT_DIR})")
    args = parser.parse_args()

    counts, clashes = label_all(args.out)
    print(f"{sum(counts.values())} message(s) labelled across {len(counts)} handle(s) "
          f"-> {args.out}/")

    if not clashes:
        print("\nNo handle has two SFAs in the same week.")
        return

    total = sum(len(weeks) for weeks in clashes.values())
    print(f"\n{total} week(s) with more than one SFA, across {len(clashes)} handle(s):")
    for handle in sorted(clashes):
        print(f"\n{handle}")
        for (iso_year, week) in sorted(clashes[handle]):
            entries = clashes[handle][(iso_year, week)]
            print(f"  {week} {iso_year}: {len(entries)} SFAs")
            for entry in entries:
                print(f"    {entry.get('date', entry['ts'])}  {entry.get('permalink', '')}")


if __name__ == "__main__":
    main()
