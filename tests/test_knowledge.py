from triage.knowledge.index import chunk_documents
from triage.knowledge.loader import load_danluu, load_icco, load_knowledge, load_runbooks, load_system_card


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


def test_diagnosis_queries_cover_every_runbook():
    from triage.evals.retrieval_eval import load_diagnosis_queries
    from triage.schema import RUNBOOK_IDS
    qs = load_diagnosis_queries()
    assert len({q["id"] for q in qs}) == len(qs)
    assert {q["runbook"] for q in qs} == set(RUNBOOK_IDS)


def test_diagnosis_eval_scores_labeled_queries(retriever):
    from triage.evals.retrieval_eval import diagnosis_eval
    r = diagnosis_eval(retriever, k=3, queries=[
        {"id": "a", "query": "expired certificate handshake failure", "runbook": "RB-06"},
        {"id": "b", "query": "expired certificate handshake failure", "runbook": "RB-08"}])
    assert r["n"] == 2 and r["rows"][0]["rank"] == 1 and r["hit_at_k"] <= 0.5


def test_system_card_indexed_without_meta_sections():
    [card] = load_system_card()
    text = card.page_content
    assert card.metadata["kind"] == "system" and "## 1. Product" in text and "## 12." in text
    assert "## 13." not in text and "```" not in text and "Status:" not in text
    assert "SYS" in {d.metadata["doc_id"] for d in load_knowledge(include_corpus=False)}


def test_answer_key_never_indexed():
    texts = " ".join(d.page_content for d in load_knowledge(include_corpus=False))
    assert "Distractor or trap" not in texts and "scenario-plan" not in texts
