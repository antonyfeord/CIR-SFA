"""Group every cached SFA by its header - the text before the first ":sun".

An SFA post opens with a header line naming the crew or scope, then the
":sunny: Highlights" section. Everything up to that first ":sun" is taken as
the header - or the whole message if it has no ":sun" - so identical headers
collapse into one entry listing the ts of every message that used it.

Before headers are read, raw channel mentions (<#C020L0LCB5Y>) in each
message's "text" in raw_sfas are rewritten in place as #channel-name via
slack_channels.json, so two headers naming the same channel group together.

Writes headers.json: {"<header>": ["<ts>", ...], ...}, ordered by how often
each header occurs.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re

RAW_DIR = "raw_sfas"
CHANNELS_PATH = "inputdata/slack_channels.json"
OUT_PATH = "data/headers.json"
MARKER = ":sun"

# <#C123>, or <#C123|already-named> as Slack sometimes writes it.
CHANNEL_REF = re.compile(r"<#([A-Z0-9]+)(?:\|([^>]*))?>")

# :wave:, :man-shrugging::skin-tone-2: - a colon pair with no whitespace between.
EMOJI_REF = re.compile(r":[^:\s]+:")


def load_channels(path=CHANNELS_PATH):
    """Channel ID -> name from slack_channels.json; empty if the file is absent."""
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return {entry["ID"]: entry["NAME"] for entry in json.load(fh)}


def resolve_channels(text, channels):
    """Rewrite <#ID> / <#ID|name> mentions as #name.

    Falls back to the name Slack inlined, then to the bare ID, so an unknown
    channel still reads as something rather than disappearing.
    """
    def replace(match):
        channel_id, inline_name = match.group(1), match.group(2)
        return "#" + (channels.get(channel_id) or inline_name or channel_id)

    return CHANNEL_REF.sub(replace, text)


def rewrite_raw_files(raw_dir=RAW_DIR, channels=None):
    """Rewrite <#ID> mentions in each message's "text" as #name, in place.

    Only files where some text changes are written back. Returns the number
    of files rewritten.
    """
    channels = load_channels() if channels is None else channels
    rewritten = 0
    for path in sorted(glob.glob(os.path.join(raw_dir, "*.json"))):
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        changed = False
        for message in data.get("messages", []):
            text = message.get("text", "")
            resolved = resolve_channels(text, channels)
            if resolved != text:
                message["text"] = resolved
                changed = True
        if changed:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
            rewritten += 1
    return rewritten


def strip_emoji(text):
    """Drop :shortcode: emoji so headers differing only by emoji group together."""
    return re.sub(r"\s{2,}", " ", EMOJI_REF.sub("", text)).strip()


def extract_header(text, marker=MARKER):
    """The part of a message before the first marker, or the whole text if absent."""
    head, _, _ = text.partition(marker)
    return strip_emoji(head)


def collect_headers(raw_dir=RAW_DIR, marker=MARKER):
    """Map each unique header to the ts of every message that used it.

    Files are read in sorted order and messages in file order, so the ts lists
    are stable across runs. A message with no marker contributes its whole text.
    """
    headers = {}
    for path in sorted(glob.glob(os.path.join(raw_dir, "*.json"))):
        with open(path, encoding="utf-8") as fh:
            messages = json.load(fh).get("messages", [])
        for message in messages:
            header = extract_header(message.get("text", ""), marker)
            headers.setdefault(header, []).append(message["ts"])
    # Most-used headers first; ties keep the order they were first seen in.
    return dict(sorted(headers.items(), key=lambda item: -len(item[1])))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--raw", default=RAW_DIR)
    parser.add_argument("--out", default=OUT_PATH)
    parser.add_argument("--channels", default=CHANNELS_PATH,
                        help="channel ID -> name mapping used to resolve <#C...>")
    parser.add_argument("--marker", default=MARKER,
                        help=f"cut the header at this string (default {MARKER!r})")
    args = parser.parse_args()

    rewritten = rewrite_raw_files(args.raw, load_channels(args.channels))
    print(f"resolved channel mentions in {rewritten} raw file(s)")

    headers = collect_headers(args.raw, args.marker)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(headers, fh, indent=2, ensure_ascii=False)

    total = sum(len(tss) for tss in headers.values())
    print(f"{len(headers)} unique header(s) over {total} message(s) -> {args.out}")


if __name__ == "__main__":
    main()
