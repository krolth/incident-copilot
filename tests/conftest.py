import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from triage.knowledge.index import build_index  # noqa: E402


@pytest.fixture(scope="session")
def retriever(tmp_path_factory):
    d = tmp_path_factory.mktemp("chroma") / "c"
    return build_index(str(d), include_corpus=False, embeddings_kind="hash")


@pytest.fixture(autouse=True)
def no_backoff_sleep(monkeypatch):
    """Retries back off with real sleeps; tests record the waits instead of sleeping."""
    import triage.approaches.common as common
    waits: list[float] = []
    monkeypatch.setattr(common.time, "sleep", waits.append)
    return waits


@pytest.fixture(autouse=True)
def ignore_local_dotenv(monkeypatch):
    """Tests must not depend on the developer's .env (e.g. LLM_REASONING=low there broke a test)."""
    import triage.knowledge.embeddings as embeddings
    import triage.llm as llm
    monkeypatch.setattr(llm, "load_dotenv", lambda *a, **k: False)
    monkeypatch.setattr(embeddings, "load_dotenv", lambda *a, **k: False)
