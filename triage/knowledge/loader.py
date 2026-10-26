"""Load the knowledge base: invented runbooks plus public postmortems.

Sources, all optional except the runbooks and the system card:
  triage/knowledge/runbooks/*.md      invented runbooks (shipped with the repo)
  docs/system.md                      system card of the fictional platform (sections 1-12 only)
  corpus/icco/*.md                    icco/postmortems: YAML front matter + cleaned full text
  corpus/danluu/entries.jsonl         danluu/post-mortems: one short summary + link per postmortem

The two public sources overlap. Documents are deduplicated by URL (icco wins, since it has full text).
Postmortem text belongs to its authors; corpus/ is git-ignored.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import yaml
from langchain_core.documents import Document

RUNBOOK_DIR = Path(__file__).parent / "runbooks"
SYSTEM_CARD = Path(__file__).resolve().parents[2] / "docs" / "system.md"
# docs/scenario-plan.md is the answer key and must never be loaded here.
_FRONT = re.compile(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", re.S)


def _split_front_matter(text: str) -> tuple[dict, str]:
    m = _FRONT.match(text)
    if not m:
        return {}, text
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        meta = {}
    return (meta if isinstance(meta, dict) else {}), m.group(2).strip()


def load_runbooks(directory: Path = RUNBOOK_DIR) -> list[Document]:
    docs = []
    for path in sorted(directory.glob("RB-*.md")):
        meta, body = _split_front_matter(path.read_text(encoding="utf-8"))
        doc_id = str(meta.get("id", path.stem))
        docs.append(Document(page_content=f"{meta.get('title', doc_id)}\n\n{body}",
                             metadata={"doc_id": doc_id, "title": str(meta.get("title", doc_id)),
                                       "kind": "runbook", "source": str(path.name), "url": ""}))
    return docs


def load_system_card(path: Path = SYSTEM_CARD) -> list[Document]:
    """What an on-call engineer would know about the platform. Keeps sections 1-12: drops the draft-status
    preamble and section 13 (design decisions taken with the owner), and the mermaid diagram (the prose says
    the same, and diagram syntax embeds poorly)."""
    text = Path(path).read_text(encoding="utf-8")
    body = text[text.index("\n## 1."):]
    body = body[:body.index("\n## 13.")] if "\n## 13." in body else body
    body = re.sub(r"```mermaid.*?```\n?", "", body, flags=re.S).strip()
    return [Document(page_content=f"Fianchetto system card\n\n{body}",
                     metadata={"doc_id": "SYS", "title": "Fianchetto system card", "kind": "system",
                               "source": "docs/system.md", "url": ""})]


def load_icco(directory: Path) -> list[Document]:
    docs = []
    for path in sorted(Path(directory).glob("*.md")):
        meta, body = _split_front_matter(path.read_text(encoding="utf-8"))
        if not body:
            continue
        url = str(meta.get("url", ""))
        title = str(meta.get("title") or meta.get("company") or path.stem)
        summary = str(meta.get("summary", "")).strip()
        text = f"{title}\n\n{summary}\n\n{body}" if summary else f"{title}\n\n{body}"
        docs.append(Document(page_content=text,
                             metadata={"doc_id": f"PM-{str(meta.get('uuid', path.stem))[:8]}", "title": title,
                                       "kind": "postmortem", "source": url or path.name, "url": url,
                                       "company": str(meta.get("company", "")),
                                       "categories": ",".join(map(str, meta.get("categories", []) or []))}))
    return docs


def load_danluu(entries_path: Path, skip_urls: set[str] | None = None) -> list[Document]:
    skip_urls = skip_urls or set()
    path = Path(entries_path)
    if not path.exists():
        return []
    docs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        e = json.loads(line)
        if e["url"] in skip_urls or not e.get("summary"):
            continue
        key = hashlib.sha1(e["url"].encode()).hexdigest()[:8]
        docs.append(Document(page_content=f"{e['company']} ({e['category']})\n\n{e['summary']}",
                             metadata={"doc_id": f"PM-D{key}", "title": f"{e['company']} postmortem (summary)",
                                       "kind": "postmortem", "source": e["url"], "url": e["url"],
                                       "company": e["company"], "categories": e["category"]}))
    return docs


def load_knowledge(corpus_dir: str | Path = "corpus", include_corpus: bool = True) -> list[Document]:
    docs = load_runbooks() + load_system_card()
    if include_corpus:
        corpus = Path(corpus_dir)
        icco = load_icco(corpus / "icco") if (corpus / "icco").exists() else []
        seen = {d.metadata["url"] for d in icco if d.metadata["url"]}
        docs += icco + load_danluu(corpus / "danluu" / "entries.jsonl", skip_urls=seen)
    return docs
