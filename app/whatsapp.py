"""
WhatsApp Business Cloud API istemcisi.
Meta Graph API v19 kullanır.

Desteklenen mesaj tipleri:
  - text  : Düz metin
  - template : Template mesajı (opsiyonel)

Gelen webhook payload'larından mesaj bilgisi çıkarma yardımcıları da burada.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)

GRAPH_API_BASE = "https://graph.facebook.com/v19.0"


class WhatsAppClient:
    def __init__(self):
        self._settings = get_settings()

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._settings.WHATSAPP_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        }

    @property
    def _url(self) -> str:
        return f"{GRAPH_API_BASE}/{self._settings.WHATSAPP_PHONE_NUMBER_ID}/messages"

    # ── Mesaj gönderme ─────────────────────────────────────────────────────

    async def send_text(self, to: str, text: str) -> dict:
        """Düz metin mesajı gönderir. to → E.164 format (örn: 905551234567)."""
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"preview_url": False, "body": text},
        }
        return await self._post(payload)

    async def send_typing(self, to: str) -> None:
        """'Yazıyor...' durumu gösterir (best-effort, hata sessizce yutulur)."""
        try:
            await self.send_text(to, "⏳")  # gerçek typing indicator API'de farklı endpoint
        except Exception:
            pass

    async def mark_as_read(self, message_id: str) -> None:
        """Mesajı okundu olarak işaretler."""
        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
        }
        try:
            await self._post(payload)
        except Exception as exc:
            log.warning("mark_as_read başarısız: %s", exc)

    # ── Dahili ────────────────────────────────────────────────────────────

    async def _post(self, payload: dict) -> dict:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(self._url, json=payload, headers=self._headers)
            if resp.status_code not in (200, 201):
                log.error("WhatsApp API hatası %s: %s", resp.status_code, resp.text)
                resp.raise_for_status()
            return resp.json()


# ── Webhook payload yardımcıları ───────────────────────────────────────────

def extract_message(payload: dict) -> dict | None:
    """
    Meta webhook payload'ından mesaj bilgisini çıkarır.

    Dönen dict:
      phone       : gönderenin numarası (E.164)
      message_id  : mesaj kimliği
      text        : mesaj metni (sadece text tipinde)
      type        : mesaj tipi ("text", "image", vb.)
      timestamp   : Unix timestamp (str)
    """
    try:
        entry = payload["entry"][0]
        changes = entry["changes"][0]["value"]
        msg = changes["messages"][0]
        phone = msg["from"]
        message_id = msg["id"]
        msg_type = msg.get("type", "unknown")
        text = ""
        if msg_type == "text":
            text = msg["text"]["body"]
        return {
            "phone": phone,
            "message_id": message_id,
            "text": text,
            "type": msg_type,
            "timestamp": msg.get("timestamp", ""),
        }
    except (KeyError, IndexError, TypeError):
        return None


def is_status_update(payload: dict) -> bool:
    """Payload bir mesaj durum güncellemesiyse True döner (ignore edilebilir)."""
    try:
        changes = payload["entry"][0]["changes"][0]["value"]
        return "statuses" in changes and "messages" not in changes
    except (KeyError, IndexError, TypeError):
        return False
