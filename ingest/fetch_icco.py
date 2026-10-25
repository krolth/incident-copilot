"""Download the icco/postmortems dataset (https://github.com/icco/postmortems).

The repo's data/ folder holds one Markdown file per postmortem: YAML front matter (url, title,
company, categories, keywords, sometimes summary) followed by cleaned body text. That makes it
a ready-made corpus; this script copies data/*.md locally.

Strategy: shallow `git clone` (needs git installed), falling back to downloading the repo
tarball if git isn't available or the clone fails.

Usage:
    python -m ingest.fetch_icco              # -> corpus/icco/<uuid>.md
    python -m ingest.fetch_icco --out corpus/icco

Note: the postmortem text belongs to its original authors. corpus/ is git-ignored on purpose.
"""
import argparse
import io
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

import requests

REPO_URL = "https://github.com/icco/postmortems"
ARCHIVE_URL = "https://codeload.github.com/icco/postmortems/tar.gz/refs/heads/main"
HEADERS = {"User-Agent": "incident-copilot-learning-project/0.1"}


def copy_via_git(out_dir: Path) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["git", "clone", "--depth", "1", "--quiet", REPO_URL, tmp],
                       check=True, timeout=300)
        files = sorted((Path(tmp) / "data").glob("*.md"))
        for f in files:
            shutil.copy2(f, out_dir / f.name)
        return len(files)


def copy_via_tarball(out_dir: Path) -> int:
    resp = requests.get(ARCHIVE_URL, headers=HEADERS, timeout=120)
    resp.raise_for_status()
    count = 0
    with tarfile.open(fileobj=io.BytesIO(resp.content), mode="r:gz") as tar:
        for member in tar.getmembers():
            parts = Path(member.name).parts  # <repo>-main/data/<file>.md
            if member.isfile() and len(parts) == 3 and parts[1] == "data" and parts[2].endswith(".md"):
                (out_dir / parts[2]).write_bytes(tar.extractfile(member).read())
                count += 1
    return count


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="corpus/icco", help="output directory")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        n = copy_via_git(out_dir)
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"git clone failed ({type(exc).__name__}); trying tarball download")
        n = copy_via_tarball(out_dir)

    print(f"saved {n} postmortems to {out_dir}/")
    print("heads-up: not every file has every front-matter field (e.g. some lack 'summary').")


if __name__ == "__main__":
    main()
