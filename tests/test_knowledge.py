from triage.knowledge.index import chunk_documents
from triage.knowledge.loader import load_danluu, load_icco, load_runbooks


def test_runbooks_load():
    docs = load_runbooks()
    assert [d.metadata["doc_id"] for d in docs] == [f"RB-0{i}" for i in range(1, 9)]


def test_chunk_ids_unique_and_prefixed():
    chunks = chunk_documents(load_runbooks())
    ids = [c.metadata["chunk_id"] for c in chunks]
    assert len(ids) == len(set(ids)) and all(i.startswith("K:RB-") for i in ids)


def test_retrieval_finds_obvious_runbook(retriever):
    assert retriever.search("expired certificate handshake failure", 3)[0].doc_id == "RB-06"


def test_icco_loader_and_dedupe(tmp_path):
    (tmp_path / "a.md").write_text("---\nuuid: abcdef123456\ncompany: Acme\ntitle: Outage\nurl: http://x/1\ncategories: [config-change]\n---\nBody text here.")
    (tmp_path / "b.md").write_text("no front matter and also no body? still text")
    docs = load_icco(tmp_path)
    assert docs[0].metadata["doc_id"] == "PM-abcdef12" and docs[0].metadata["url"] == "http://x/1"
    assert len(docs) == 2


def test_danluu_loader_skips_duplicates(tmp_path):
    p = tmp_path / "e.jsonl"
    p.write_text('{"company":"A","category":"cat","summary":"s1","url":"http://x/1"}\n{"company":"B","category":"cat","summary":"s2","url":"http://x/2"}\n')
    assert len(load_danluu(p)) == 2
    assert [d.metadata["url"] for d in load_danluu(p, skip_urls={"http://x/1"})] == ["http://x/2"]
    assert load_danluu(tmp_path / "missing.jsonl") == []
