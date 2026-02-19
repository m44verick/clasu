"""
Konuşma geçmişini JSON dosyaları olarak saklar.
Her telefon numarası için ayrı bir dosya: data/conversations/<phone>.json

Mesajlar Claude API'nin beklediği formatta tutulur:
  {"role": "user"|"assistant", "content": str | list[dict]}

Tool use içeren assistant mesajları list[dict] formatındadır.
"""
import json
from pathlib import Path
from datetime import datetime

from app.config import get_settings

STORE_DIR = Path("data/conversations")


class ConversationStore:
    def __init__(self):
        STORE_DIR.mkdir(parents=True, exist_ok=True)

    def _path(self, phone: str) -> Path:
        # Güvenli dosya adı: sadece rakam ve +
        safe = "".join(c for c in phone if c.isdigit() or c == "+")
        return STORE_DIR / f"{safe}.json"

    def _load(self, phone: str) -> dict:
        p = self._path(phone)
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {"messages": [], "handoff": False, "handoff_reason": None}

    def _save(self, phone: str, data: dict) -> None:
        p = self._path(phone)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── Mesaj işlemleri ────────────────────────────────────────────────────

    def get_messages(self, phone: str) -> list:
        """Claude'a gönderilecek mesaj listesini döner."""
        return self._load(phone)["messages"]

    def set_messages(self, phone: str, messages: list) -> None:
        """Mesaj listesini kaydeder (son MAX_CONVERSATION_TURNS tutulur)."""
        settings = get_settings()
        data = self._load(phone)
        data["messages"] = messages[-settings.MAX_CONVERSATION_TURNS :]
        data["last_activity"] = datetime.now().isoformat()
        self._save(phone, data)

    # ── İnsan devreye alma ─────────────────────────────────────────────────

    def is_handoff(self, phone: str) -> bool:
        return self._load(phone).get("handoff", False)

    def set_handoff(self, phone: str, reason: str, summary: str = "") -> None:
        data = self._load(phone)
        data["handoff"] = True
        data["handoff_reason"] = reason
        data["handoff_summary"] = summary
        data["handoff_at"] = datetime.now().isoformat()
        self._save(phone, data)
        # Merkezi handoff log'u
        _append_handoff_log(phone, reason, summary)

    def clear_handoff(self, phone: str) -> None:
        """İnsan temsilci görüşmeyi kapatınca AI'ı tekrar devreye alır."""
        data = self._load(phone)
        data["handoff"] = False
        data["handoff_reason"] = None
        self._save(phone, data)

    def reset(self, phone: str) -> None:
        """Konuşmayı sıfırlar."""
        p = self._path(phone)
        if p.exists():
            p.unlink()


# ── Yardımcı ───────────────────────────────────────────────────────────────

def _append_handoff_log(phone: str, reason: str, summary: str) -> None:
    log_path = Path("data/handoffs.jsonl")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now().isoformat(),
        "phone": phone,
        "reason": reason,
        "summary": summary,
    }
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
