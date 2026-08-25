
import pytest

from services.agent.orchestrator import build_llm


def test_raises_clearly_when_no_api_key_is_set(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GROQ_API_KEY|OPENAI_API_KEY"):
        build_llm()


def test_selects_groq_when_only_groq_key_is_set(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key-not-real")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    llm = build_llm()
    assert type(llm).__name__ == "ChatGroq"


def test_falls_back_to_openai_when_only_openai_key_is_set(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    llm = build_llm()
    assert type(llm).__name__ == "ChatOpenAI"


def test_prefers_groq_when_both_keys_are_set(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key-not-real")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    llm = build_llm()
    assert type(llm).__name__ == "ChatGroq"
