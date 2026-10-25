import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from triage.knowledge.index import build_index  # noqa: E402


@pytest.fixture(scope="session")
def retriever(tmp_path_factory):
    d = tmp_path_factory.mktemp("chroma") / "c"
    return build_index(str(d), include_corpus=False, embeddings_kind="hash")
