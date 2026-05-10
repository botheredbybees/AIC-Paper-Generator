import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ai_scientist.llm import create_client


def test_create_client_ollama_respects_base_url_env(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://192.168.1.20:11434")
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    client, model = create_client("ollama/qwen3.5:9b-q8_0")
    assert "192.168.1.20" in str(client.base_url)
    assert model == "ollama/qwen3.5:9b-q8_0"


def test_create_client_ollama_defaults_to_localhost(monkeypatch):
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    client, model = create_client("ollama/qwen3.5:9b-q8_0")
    assert "localhost:11434" in str(client.base_url)
