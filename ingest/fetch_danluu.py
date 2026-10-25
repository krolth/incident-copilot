"""Download the danluu/post-mortems list (https://github.com/danluu/post-mortems).

The README is a categorized list of public postmortems: each entry is a link plus a short
summary. Step 1 (always) parses those entries into corpus/danluu/entries.jsonl, so you get
~hundreds of short, category-labelled summaries with no scraping.
Step 2 (optional, --fetch-pages) downloads each linked page and extracts its text, so you can
also work with long-form documents. Pages are best-effort: many sites block bots or have moved.

Usage:
    python -m ingest.fetch_danluu                          # entries only
    python -m ingest.fetch_danluu --fetch-pages --limit 40 # also fetch up to 40 pages
"""
import argparse
import hashlib
import json
import re
import time
from pathlib import Path

import requests

README_URL = "https://raw.githubusercontent.com/danluu/post-mortems/master/README.md"
HEADERS = {"User-Agent": "incident-copilot-learning-project/0.1"}
ENTRY_RE = re.compile(r"^\[([^\]]+)\]\((https?://[^)\s]+)\)\.?\s*(.*)$")
NON_INCIDENT_SECTIONS = {"Table of Contents", "Other lists of postmortems", "Analysis", "Contributors"}
MIN_PAGE_CHARS = 1500


def parse_readme(markdown: str) -> list[dict]:
    entries, category = [], None
    for line in markdown.splitlines():
        if line.startswith("## "):
            category = line[3:].strip()
            continue
        if category is None or category in NON_INCIDENT_SECTIONS:
            continue
        m = ENTRY_RE.match(line.strip())
        if m:
            company, url, summary = m.groups()
            entries.append({"company": company, "url": url, "summary": summary.strip(),
                            "category": category, "source": "danluu"})
    return entries


def fetch_pages(entries: list[dict], pages_dir: Path, limit: int, delay: float) -> int:
    import trafilatura  # only needed for --fetch-pages

    pages_dir.mkdir(parents=True, exist_ok=True)
    saved = 0
    for e in entries:
        if saved >= limit:
            break
        path = pages_dir / f"{hashlib.sha1(e['url'].encode()).hexdigest()[:12]}.txt"
        if path.exists():
            saved += 1
            continue
        try:
            html = requests.get(e["url"], headers=HEADERS, timeout=20).text
            text = trafilatura.extract(html, include_comments=False, include_tables=False)
        except Exception as exc:
            print(f"skip {e['url']} ({type(exc).__name__})")
            continue
        if not text or len(text) < MIN_PAGE_CHARS:
            print(f"skip {e['url']} (little or no text)")
            continue
        path.write_text(text, encoding="utf-8")
        saved += 1
        print(f"[{saved}/{limit}] {e['company']}")
        time.sleep(delay)
    return saved


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="corpus/danluu")
    ap.add_argument("--fetch-pages", action="store_true", help="also download and extract linked pages")
    ap.add_argument("--limit", type=int, default=40, help="max pages to save with --fetch-pages")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between page requests")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    resp = requests.get(README_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    entries = parse_readme(resp.text)

    with (out / "entries.jsonl").open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    print(f"saved {len(entries)} entries to {out}/entries.jsonl")

    if args.fetch_pages:
        n = fetch_pages(entries, out / "pages", args.limit, args.delay)
        print(f"saved {n} pages to {out}/pages/ (filenames are a hash of the URL)")


if __name__ == "__main__":
    main()
