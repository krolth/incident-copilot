"""Provider-switchable chat models, configured by environment variables.

  LLM_PROVIDER   openai (default) | anthropic | ollama (local models; needs a tool-calling model)
  LLM_MODEL      REQUIRED model name for the agents (no default on purpose: model names change, check your provider)
  LLM_TEMPERATURE optional float; omit it to use the provider default (some models reject a temperature)
  JUDGE_MODEL    model for the LLM-as-judge; use a DIFFERENT model than LLM_MODEL when you can
  JUDGE_PROVIDER optional; defaults to LLM_PROVIDER
  OLLAMA_NUM_CTX context window for Ollama models (default 32768). Ollama silently drops the start of a
                 prompt that overflows its window, so a ReAct history full of log output must fit.

Values are read from the process environment, then from .env in the working directory (real env wins).

Not exercised against real providers in the build sandbox (no keys, no network). First real call is where this is verified.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv
from langchain_core.language_models.chat_models import BaseChatModel


def _build(provider: str, model: str, temperature: float | None) -> BaseChatModel:
    kwargs = {} if temperature is None else {"temperature": temperature}
    if provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=model, **kwargs)
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=model, **kwargs)
    if provider == "ollama":
        from langchain_ollama import ChatOllama
        # base_url defaults to http://localhost:11434; set OLLAMA_BASE_URL if the model runs on another machine
        return ChatOllama(model=model, base_url=os.getenv("OLLAMA_BASE_URL") or None,
                          num_ctx=int(os.getenv("OLLAMA_NUM_CTX") or 32768), **kwargs)
    raise ValueError(f"unknown provider {provider!r} (use openai, anthropic or ollama)")


def _temperature() -> float | None:
    raw = os.getenv("LLM_TEMPERATURE", "").strip()
    return float(raw) if raw else None


def get_llm() -> BaseChatModel:
    load_dotenv()
    model = os.getenv("LLM_MODEL", "").strip()
    if not model:
        raise RuntimeError("Set LLM_MODEL (and LLM_PROVIDER, plus the provider API key). See .env.example.")
    return _build(os.getenv("LLM_PROVIDER", "openai").lower(), model, _temperature())


def get_judge_llm() -> BaseChatModel:
    load_dotenv()
    model = os.getenv("JUDGE_MODEL", "").strip()
    if not model:
        raise RuntimeError("Set JUDGE_MODEL (ideally a different model than LLM_MODEL).")
    provider = os.getenv("JUDGE_PROVIDER", os.getenv("LLM_PROVIDER", "openai")).lower()
    return _build(provider, model, _temperature())


def describe() -> dict:
    load_dotenv()
    return {"provider": os.getenv("LLM_PROVIDER", "openai"), "model": os.getenv("LLM_MODEL", ""),
            "judge_model": os.getenv("JUDGE_MODEL", ""), "embeddings": os.getenv("EMBEDDINGS", "local")}
