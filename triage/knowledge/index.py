"""Chunk the knowledge base, index it in ChromaDB, and search it.

Chunking is a design decision to MEASURE, not guess: chunk size and overlap are parameters, and
triage/evals/retrieval_eval.py reports runbook hit rate so you can compare settings.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from triage.knowledge.embeddings import get_embeddings
from triage.knowledge.loader import load_knowledge

COLLECTION = "knowledge"


@dataclass
class Hit:
    chunk_id: str  # e.g. "K:RB-01#0" (what agents cite)
    doc_id: str
    title: str
    kind: str  # runbook | postmortem
    source: str
    text: str
    score: float  # distance: lower is closer


def chunk_documents(docs: list[Document], chunk_size: int = 900, overlap: int = 120) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=overlap,
                                              separators=["\n\n", "\n", ". ", " ", ""])
    chunks: list[Document] = []
    for doc in docs:
        for i, piece in enumerate(splitter.split_text(doc.page_content)):
            meta = dict(doc.metadata)
            meta["chunk_id"] = f"K:{meta['doc_id']}#{i}"
            chunks.append(Document(page_content=piece, metadata=meta))
    return chunks


def build_index(persist_dir: str = "chroma_db", corpus_dir: str = "corpus", include_corpus: bool = True,
                chunk_size: int = 900, overlap: int = 120, embeddings_kind: str | None = None) -> "Retriever":
    """Rebuild the index from scratch (so re-runs never duplicate chunks)."""
    path = Path(persist_dir)
    if path.exists():
        shutil.rmtree(path)
    docs = load_knowledge(corpus_dir, include_corpus)
    chunks = chunk_documents(docs, chunk_size, overlap)
    store = Chroma(collection_name=COLLECTION, embedding_function=get_embeddings(embeddings_kind),
                   persist_directory=str(path))
    # Chroma limits batch size; add in slices.
    for i in range(0, len(chunks), 128):
        batch = chunks[i:i + 128]
        store.add_documents(batch, ids=[c.metadata["chunk_id"] for c in batch])
    print(f"indexed {len(docs)} documents -> {len(chunks)} chunks in {persist_dir}/")
    return Retriever(store)


def load_index(persist_dir: str = "chroma_db", embeddings_kind: str | None = None) -> "Retriever":
    store = Chroma(collection_name=COLLECTION, embedding_function=get_embeddings(embeddings_kind),
                   persist_directory=persist_dir)
    return Retriever(store)


class Retriever:
    def __init__(self, store: Chroma) -> None:
        self.store = store

    def search(self, query: str, k: int = 4) -> list[Hit]:
        hits = []
        for doc, score in self.store.similarity_search_with_score(query, k=k):
            m = doc.metadata
            hits.append(Hit(m["chunk_id"], m["doc_id"], m["title"], m["kind"], m.get("source", ""), doc.page_content, float(score)))
        return hits


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Build the knowledge index (runbooks + downloaded postmortems).")
    ap.add_argument("--persist-dir", default="chroma_db")
    ap.add_argument("--corpus-dir", default="corpus")
    ap.add_argument("--no-corpus", action="store_true", help="index only the runbooks")
    ap.add_argument("--chunk-size", type=int, default=900)
    ap.add_argument("--overlap", type=int, default=120)
    args = ap.parse_args()
    build_index(args.persist_dir, args.corpus_dir, not args.no_corpus, args.chunk_size, args.overlap)
