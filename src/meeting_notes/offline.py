"""Fail-closed checks that keep all runtime services local."""
from urllib.parse import urlparse
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
class OfflinePolicyError(RuntimeError):
    """Raised when a configuration would leave the laptop."""
def assert_local_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in LOOPBACK_HOSTS:
        raise OfflinePolicyError(f"Offline guarantee: Ollama URL must be loopback, got {url!r}")
def enforce_offline_policy(ollama_url: str) -> None:
    assert_local_url(ollama_url)
def offline_status() -> str:
    return "OFFLINE GUARANTEE: local models only; summaries use loopback Ollama only."
