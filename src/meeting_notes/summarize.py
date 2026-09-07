"""Local Ollama generation over loopback HTTP only."""
from dataclasses import dataclass
import json
from urllib import request, error
from .offline import enforce_offline_policy
@dataclass
class ActionItem:
    action: str
    owner: str = "Unassigned"
    due: str = "Not specified"
    source: str = ""
    def to_dict(self): return {"action": self.action, "owner": self.owner, "due": self.due, "source": self.source}
def _call_ollama(base_url: str, model: str, prompt: str, temperature: float) -> str:
    enforce_offline_policy(base_url)
    body = json.dumps({"model": model, "prompt": prompt, "stream": False, "options": {"temperature": temperature}}).encode()
    req = request.Request(base_url.rstrip("/") + "/api/generate", data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with request.urlopen(req, timeout=180) as response: payload = json.loads(response.read().decode())
    except (error.URLError, TimeoutError, json.JSONDecodeError) as exc: raise RuntimeError(f"Local Ollama request failed: {exc}") from exc
    return str(payload.get("response", "")).strip()
def _stamp(seconds: float) -> str:
    total = max(0, int(seconds)); return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"
def _transcript_text(segments) -> str:
    return "\n".join(f"[{_stamp(s.start)}-{_stamp(s.end)}] {s.speaker}: {s.text}" for s in segments)
def generate_notes(segments, config):
    text = _transcript_text(segments)
    common = f"You are a careful meeting-notes editor. Write in Canadian English ({config.language}). Never invent facts, dates, owners, or decisions. Distinguish stated decisions from suggestions.\n\nTRANSCRIPT:\n{text}"
    full = _call_ollama(config.ollama_url, config.ollama_model, common + "\n\nProduce a detailed summary with headings Overview, Decisions, Discussion by topic, Risks or open questions, and Next steps.", config.temperature)
    short = _call_ollama(config.ollama_url, config.ollama_model, common + "\n\nProduce at most 7 concise bullets including key decisions and unresolved questions.", config.temperature)
    raw = _call_ollama(config.ollama_url, config.ollama_model, common + "\n\nExtract only explicit or strongly implied action items. Return strict JSON array only with keys action, owner, due, source. Use Unassigned or Not specified when absent.", config.temperature)
    return full, short, parse_actions(raw)
def parse_actions(raw: str) -> list[ActionItem]:
    text = raw.strip()
    if "```" in text:
        parts = [p for p in text.split("```") if p.strip()]
        text = next((p.replace("json", "", 1).strip() for p in parts if "[" in p), text)
    try: data = json.loads(text)
    except json.JSONDecodeError: return []
    if not isinstance(data, list): return []
    result = []
    for item in data:
        if not isinstance(item, dict) or not str(item.get("action", "")).strip(): continue
        result.append(ActionItem(str(item["action"]).strip(), str(item.get("owner", "Unassigned")).strip() or "Unassigned", str(item.get("due", "Not specified")).strip() or "Not specified", str(item.get("source", "")).strip()))
    return result
