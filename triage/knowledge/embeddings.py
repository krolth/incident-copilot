"""Embedding models, selected by the EMBEDDINGS environment variable (or an explicit argument).

  hash    deterministic bag-of-words hashing. Offline, free, instant. FOR TESTS ONLY: it matches
          shared words, not meaning, so never report retrieval results measured with it.
  openai  OpenAI text-embedding-3-small (needs OPENAI_API_KEY and langchain-openai).
  local   BAAI/bge-small-en-v1.5 via sentence-transformers (downloads the model once; free).

The openai and local adapters are written but were not exercised in the build sandbox (no
network to those services). First real run is where they get verified.
"""
from __future__ import annotations

import math
import os
import re
import zlib

from langchain_core.embeddings import Embeddings


class HashEmbeddings(Embeddings):
    def __init__(self, dim: int = 512) -> None:
        self.dim = dim

    def _embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for tok in re.findall(r"[a-z0-9]+", text.lower()):
            vec[zlib.crc32(tok.encode()) % self.dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


def get_embeddings(kind: str | None = None) -> Embeddings:
    kind = (kind or os.getenv("EMBEDDINGS", "local")).lower()
    if kind == "hash":
        return HashEmbeddings()
    if kind == "openai":
        from langchain_openai import OpenAIEmbeddings
        return OpenAIEmbeddings(model="text-embedding-3-small")
    if kind == "local":
        from langchain_huggingface import HuggingFaceEmbeddings
        return HuggingFaceEmbeddings(model_name="BAAI/bge-small-en-v1.5")
    raise ValueError(f"unknown EMBEDDINGS value {kind!r} (use hash, openai, or local)")
