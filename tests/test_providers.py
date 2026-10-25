"""Provider wiring for local Ollama models. Constructing the clients needs no running server."""
from triage.knowledge.embeddings import get_embeddings
from triage.llm import get_llm


def test_ollama_chat_model_gets_explicit_context_window(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("LLM_MODEL", "some-local-model")
    monkeypatch.delenv("OLLAMA_NUM_CTX", raising=False)
    assert get_llm().num_ctx == 32768
    monkeypatch.setenv("OLLAMA_NUM_CTX", "16384")
    assert get_llm().num_ctx == 16384


def test_ollama_embeddings_use_configured_model(monkeypatch):
    monkeypatch.setenv("OLLAMA_EMBED_MODEL", "some-embedder")
    emb = get_embeddings("ollama")
    assert type(emb).__name__ == "OllamaEmbeddings" and emb.model == "some-embedder"


def test_reasoning_setting(monkeypatch):
    import pytest
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("LLM_MODEL", "some-local-model")
    monkeypatch.delenv("LLM_REASONING", raising=False)
    assert get_llm().reasoning is None  # unset: the model's own default
    monkeypatch.setenv("LLM_REASONING", "low")
    assert get_llm().reasoning == "low"
    monkeypatch.setenv("LLM_REASONING", "false")
    assert get_llm().reasoning is False
    monkeypatch.setenv("LLM_REASONING", "extreme")
    with pytest.raises(ValueError):
        get_llm()


def test_reasoning_refused_where_not_wired(monkeypatch):
    import pytest
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_MODEL", "x")
    monkeypatch.setenv("LLM_REASONING", "low")
    with pytest.raises(ValueError, match="only wired for ollama"):
        get_llm()
