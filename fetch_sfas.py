"""Fetch every #org_alaner-sfa channel post by each person in names.json.

names.json is a list of {"SLACK_HANDLE": ..., "SLACK_ID": ...}; the ID is what
the search runs on, the handle only names the output file.

Thread replies are excluded - only thread starters and standalone posts.
Messages are cached raw in raw_sfas/<handle>.json exactly as Slack returned
them. A rerun skips handles that already have a file, so a rate-limit or a
dropped connection just means running it again; --force refetches.

Set YEAR to restrict to one calendar year, or None for the full history.

Needs search:read.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

SLACK_API = "https://slack.com/api/"
HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(HERE, ".env")

NAMES_PATH = "inputdata/names.json"
OUT_DIR = "raw_sfas"
CHANNEL = "org_alaner-sfa"

# Only keep messages from this calendar year (UTC); None fetches everything.
YEAR = 2024


def load_token(path=ENV_PATH, key="SLACK_TOKEN"):
    """Read the token from the environment, falling back to the .env file."""
    if os.environ.get(key):
        return os.environ[key]
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, _, value = line.partition("=")
            if name.strip() == key:
                return value.strip().strip("\"'")
    raise RuntimeError(f"{key} not found in {path}")


def slack_api(method, token, **params):
    """Call a Slack Web API method, retrying on rate limits and network blips."""
    query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    req = urllib.request.Request(
        SLACK_API + method + "?" + query,
        headers={"Authorization": f"Bearer {token}"},
    )
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.load(resp)
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < 4:
                time.sleep(int(exc.headers.get("Retry-After", "1")))
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            if attempt < 4:
                time.sleep(2 * (attempt + 1))
                continue
            raise
        if not payload.get("ok"):
            raise RuntimeError(f"{method} failed: {payload.get('error')}")
        return payload
    raise RuntimeError(f"{method} did not succeed after retries")


def is_thread_reply(match):
    """True if this match was posted inside a thread rather than in the channel.

    Search results carry no thread field, but a reply's permalink points back at
    its parent via thread_ts; for a thread starter that value equals its own ts,
    and a message with no thread at all has no such param.
    """
    query = urllib.parse.parse_qs(urllib.parse.urlparse(match.get("permalink", "")).query)
    thread_ts = query.get("thread_ts", [None])[0]
    return bool(thread_ts) and thread_ts != match["ts"]


def search_all(query, token):
    """Every match for one search query, paging until Slack runs out."""
    matches, page = [], 1
    while True:
        result = slack_api("search.messages", token, query=query, count=100, page=page)["messages"]
        matches.extend(result.get("matches", []))
        paging = result.get("paging", {})
        if page >= paging.get("pages", 1):
            break
        page += 1
    return matches


def year_bounds(year):
    """(start, end) epoch seconds spanning the whole calendar year in UTC."""
    start = datetime(year, 1, 1, tzinfo=timezone.utc).timestamp()
    end = datetime(year + 1, 1, 1, tzinfo=timezone.utc).timestamp()
    return start, end


def find_messages(user_id, token, year=YEAR):
    """Every channel-level #org_alaner-sfa post by one user ID, oldest first.

    With a year set, the search is widened by a day at each end and the exact
    cut is made on the timestamps below: Slack reads after:/before: as strictly
    outside the named day, so asking for after:2024-01-01 would silently drop
    January 1st itself.
    """
    # A user ID has to go in as "from:<@U123>"; bare "from:U123" is accepted
    # and then matches nothing.
    query = f"in:#{CHANNEL} from:<@{user_id}>"
    low, high = (None, None) if year is None else year_bounds(year)
    if year is not None:
        query += f" after:{year - 1}-12-30 before:{year + 1}-01-02"

    hits, seen = [], set()
    for match in search_all(query, token):
        key = (match.get("channel", {}).get("id"), match["ts"])
        if key in seen or is_thread_reply(match):
            continue
        if low is not None and not low <= float(match["ts"]) < high:
            continue
        seen.add(key)
        hits.append(
            {
                "ts": match["ts"],
                "date": datetime.fromtimestamp(
                    float(match["ts"]), timezone.utc).strftime("%d/%m/%Y"),
                "user": match.get("username") or match.get("user"),
                "text": match.get("text", ""),
                "permalink": match.get("permalink"),
            }
        )
    hits.sort(key=lambda hit: float(hit["ts"]))
    return hits


def fetch_raw(names_path=NAMES_PATH, out_dir=OUT_DIR, force=False, year=YEAR):
    """Write one JSON file per person. Returns (counts, failed handles)."""
    with open(names_path, encoding="utf-8") as fh:
        people = json.load(fh)
    os.makedirs(out_dir, exist_ok=True)
    token = load_token()

    counts, failed = {}, []
    for index, person in enumerate(people, 1):
        handle, user_id = person["SLACK_HANDLE"], person["SLACK_ID"]
        tag = f"[{index}/{len(people)}] {handle}"
        path = os.path.join(out_dir, f"{handle}.json")

        if os.path.exists(path) and not force:
            counts[handle] = len(load_raw(handle, out_dir))
            print(f"{tag}: already cached, skipping", flush=True)
            continue

        try:
            hits = find_messages(user_id, token, year)
        except Exception as exc:  # keep going; no file written, so a rerun retries
            print(f"{tag}: FAILED - {exc}", flush=True)
            failed.append(handle)
            continue

        # Written to a temp name first so an interrupt cannot leave a half file
        # that the next run would treat as cached.
        tmp = path + ".part"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"handle": handle, "slack_id": user_id, "year": year,
                       "messages": hits}, fh, indent=2, ensure_ascii=False)
        os.replace(tmp, path)

        counts[handle] = len(hits)
        print(f"{tag}: {len(hits)} SFA(s) -> {path}", flush=True)

    return counts, failed


def load_raw(handle, out_dir=OUT_DIR):
    """Read one cached person back; returns the list of raw messages."""
    with open(os.path.join(out_dir, f"{handle}.json"), encoding="utf-8") as fh:
        return json.load(fh)["messages"]


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--names", default=NAMES_PATH)
    parser.add_argument("--out", default=OUT_DIR)
    parser.add_argument("--force", action="store_true",
                        help="refetch handles that are already cached")
    parser.add_argument("--year", type=int, default=YEAR,
                        help=f"calendar year to keep (default {YEAR}); 0 for all years")
    args = parser.parse_args()

    year = args.year or None
    counts, failed = fetch_raw(args.names, args.out, args.force, year)
    empty = sorted(h for h, n in counts.items() if n == 0)

    window = f"in {year}" if year else "across all years"
    print(f"\n{sum(counts.values())} SFA(s) {window} across {len(counts)} handle(s) -> {args.out}/")

    print(f"\nNumber of Alaners with no SFAs: {len(empty)}")
    for handle in empty:
        print("  ", handle)
    if failed:
        print(f"\n{len(failed)} handle(s) errored - rerun to retry them:")
        for handle in failed:
            print("  ", handle)


if __name__ == "__main__":
    main()
