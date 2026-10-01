"""Match each header in headers.json against the crew names in crews.json.

Three independent passes per header, all case-insensitive; a crew found by
more than one pass is reported in each of them:
  perfect_matches     - the crew name appears as-is in the header.
  camel_case_matches  - same, but with "_" read as a space on both sides, so
                        "#crew_Fraud_Fighting" matches the crew "fraud
                        fighting".
  close_naming        - the header uses one of the known aliases in
                        close_naming.json ("fraud woodchuck" -> "fraud
                        fighting"); reports the crew the alias resolves to.

Within each list, a match contained in a longer one - "fraud fighting" inside
"fraud fighting crew" - is dropped in favour of the longest.

crew_allocation only fires when the three passes agree: every non-empty list
holds the same single crew, and at least one of them is non-empty. Anything
else is left unallocated - the header goes to conflicting_matching.json when
the passes disagree, and to empty_matching.json when they all came up empty.

Writes header_crews.json: {"<header>": {"perfect_matches": [...],
"camel_case_matches": [...], "close_naming": [...], "crew_allocation": ...}}
plus conflicting_matching.json, {"<header>": ["<crew>", ...]} for the headers
several crews are in the running for, and empty_matching.json, holding the
full entries for the headers nothing matched.
"""

from __future__ import annotations

import argparse
import json
import os
import re

import fetch_headers

HEADERS_PATH = "data/headers.json"
CREWS_PATH = "inputdata/crews.json"
ALIASES_PATH = "data/close_naming.json"
OUT_PATH = "data/header_crews.json"
CONFLICTS_PATH = "data/conflicting_matching.json"
EMPTY_PATH = "data/empty_matching.json"

MATCH_FIELDS = ("perfect_matches", "camel_case_matches", "close_naming")


def drop_subsets(names):
    """Keep only the names that are not contained in another name in the list."""
    lowered = [name.lower() for name in names]
    return [name for name, low in zip(names, lowered)
            if not any(other != low and low in other for other in lowered)]


def fold(text):
    """Lowercased, with underscores read as spaces, for comparing slugs to names."""
    return text.lower().replace("_", " ")


def contains(haystack, needle):
    """True if needle occurs in haystack without letters butting up against it.

    Guards the short crew names: "mo" is a hit in "#mo" or "mo crew" but not
    inside "mohr". Only letters block a match - punctuation, digits and spaces
    around the name are all fine.
    """
    if not needle:
        return False
    pattern = r"(?<![^\W\d_])" + re.escape(needle) + r"(?![^\W\d_])"
    return re.search(pattern, haystack) is not None


def match_header(header, crews, aliases):
    """The crews this header names, by exact, underscore-tolerant and alias."""
    low_header = header.lower()
    perfect = {crew for crew in crews if contains(low_header, crew.lower())}
    loose = {crew for crew in crews if contains(fold(header), fold(crew))}
    # Aliases are matched the same loose way; the crew they point at is what
    # gets reported.
    close = {crew for alias, crew in aliases.items()
             if contains(fold(header), fold(alias))}
    order = lambda names: drop_subsets(sorted(names, key=len, reverse=True))
    matches = {"perfect_matches": order(perfect),
               "camel_case_matches": order(loose),
               "close_naming": order(close)}
    matches["crew_allocation"] = allocate(matches)
    return matches


def candidates(matches):
    """The distinct crews the three passes found, least precise names dropped.

    "platform" and "clinic" alongside "clinic platform" are not three crews,
    just the same one named less precisely, so the contained names go.
    """
    pool = {crew for field in MATCH_FIELDS for crew in matches[field]}
    return drop_subsets(sorted(pool, key=len, reverse=True))


def allocate(matches):
    """The one crew every pass agrees on, or None when they do not.

    A single candidate is the allocation; several genuinely different crews
    are a conflict, and nothing at all leaves the header empty.
    """
    crews = candidates(matches)
    return crews[0] if len(crews) == 1 else None


def load_aliases(path=ALIASES_PATH):
    """Alias -> crew name; empty if the file is absent."""
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_headers(path=HEADERS_PATH):
    """The headers from path, building it from the cached SFAs if it is absent."""
    if not os.path.exists(path):
        headers = fetch_headers.collect_headers()
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(headers, fh, indent=2, ensure_ascii=False)
        print(f"{path} was missing; built {len(headers)} header(s) from "
              f"{fetch_headers.RAW_DIR}/")
        return headers
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def match_headers(headers_path=HEADERS_PATH, crews_path=CREWS_PATH,
                  aliases_path=ALIASES_PATH):
    """Map every header to the crews it names."""
    headers = load_headers(headers_path)
    with open(crews_path, encoding="utf-8") as fh:
        crews = json.load(fh)
    aliases = load_aliases(aliases_path)
    return {header: match_header(header, crews, aliases) for header in headers}


def split_unallocated(matches):
    """The unallocated headers, split into the conflicting ones and the empty ones.

    Conflicts are reported as header -> the crews in the running, the same
    subset-dropped pool allocate weighed up; the empty ones keep the full
    entry, there being no crews to list.
    """
    conflicting, empty = {}, {}
    for header, entry in matches.items():
        if entry["crew_allocation"]:
            continue
        crews = candidates(entry)
        if crews:
            conflicting[header] = crews
        else:
            empty[header] = entry
    return conflicting, empty


def dump(path, payload):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--headers", default=HEADERS_PATH)
    parser.add_argument("--crews", default=CREWS_PATH)
    parser.add_argument("--aliases", default=ALIASES_PATH)
    parser.add_argument("--out", default=OUT_PATH)
    parser.add_argument("--conflicts", default=CONFLICTS_PATH)
    parser.add_argument("--empty", default=EMPTY_PATH)
    args = parser.parse_args()

    matches = match_headers(args.headers, args.crews, args.aliases)
    conflicting, empty = split_unallocated(matches)
    dump(args.out, matches)
    dump(args.conflicts, conflicting)
    dump(args.empty, empty)

    counts = {field: sum(1 for m in matches.values() if m[field])
              for field in MATCH_FIELDS}
    allocated = sum(1 for m in matches.values() if m["crew_allocation"])
    print(f"{len(matches)} header(s) -> {args.out}")
    for field, count in counts.items():
        print(f"  {count} with a {field} hit")
    print(f"  {allocated} allocated to a single crew")
    print(f"  {len(conflicting)} with conflicting matches -> {args.conflicts}")
    print(f"  {len(empty)} with no match at all -> {args.empty}")


if __name__ == "__main__":
    main()
