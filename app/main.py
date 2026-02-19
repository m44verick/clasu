"""
FastAPI uygulaması — WhatsApp webhook endpoint'i.

Endpoints:
  GET  /health          → sağlık kontrolü
  GET  /webhook         → Meta webhook doğrulama
  POST /webhook         → Gelen WhatsApp mesajları
  POST /admin/reset     → Konuşma sıfırlama (dahili kullanım)
  POST /admin/handoff/clear → Handoff'u kaldırma (dahili kullanım)
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import PlainTextResponse

from app.agent import SalesAgent
from app.catalog import ProductCatalog
from app.config import get_settings
from app.conversation_store import ConversationStore
from app.whatsapp import WhatsAppClient, extract_message, is_status_update

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

# ── Uygulama durumu (singleton'lar) ────────────────────────────────────────

settings = get_settings()
catalog: ProductCatalog
store: ConversationStore
wa: WhatsAppClient
agent: SalesAgent


@asynccontextmanager
async def lifespan(app: FastAPI):
    global catalog, store, wa, agent
    catalog = ProductCatalog()
    store = ConversationStore()
    wa = WhatsAppClient()
    agent = SalesAgent(catalog=catalog, store=store)
    if not catalog.is_loaded:
        log.warning(
            "Ürün kataloğu yüklenemedi: %s — katalog dosyasını kontrol edin.",
            settings.PRODUCT_CATALOG_FILE,
        )
    else:
        log.info("Ürün kataloğu yüklendi, %d ürün.", len(catalog.all_products()))
    yield


app = FastAPI(title="WhatsApp Sales Agent", lifespan=lifespan)


# ── Sağlık ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "catalog_loaded": catalog.is_loaded,
        "product_count": len(catalog.all_products()) if catalog.is_loaded else 0,
    }


# ── Webhook doğrulama (GET) ────────────────────────────────────────────────

@app.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
):
    if hub_mode == "subscribe" and hub_verify_token == settings.WHATSAPP_VERIFY_TOKEN:
        log.info("Webhook doğrulandı.")
        return PlainTextResponse(hub_challenge)
    raise HTTPException(status_code=403, detail="Geçersiz doğrulama token'ı")


# ── Gelen mesajlar (POST) ──────────────────────────────────────────────────

@app.post("/webhook")
async def receive_webhook(request: Request):
    payload = await request.json()

    # Durum güncellemelerini yoksay
    if is_status_update(payload):
        return Response(status_code=200)

    msg = extract_message(payload)
    if not msg:
        return Response(status_code=200)

    phone = msg["phone"]
    text = msg["text"]
    message_id = msg["message_id"]
    msg_type = msg["type"]

    log.info("Mesaj alındı [%s] tip=%s: %r", phone, msg_type, text[:80] if text else "")

    # Sadece metin mesajlarını işle
    if msg_type != "text" or not text.strip():
        await wa.send_text(phone, "Üzgünüm, şu an yalnızca metin mesajlarını anlayabiliyorum.")
        return Response(status_code=200)

    # Okundu işareti
    asyncio.create_task(wa.mark_as_read(message_id))

    # İnsan devreye almışsa mesajı yoksay
    if store.is_handoff(phone):
        log.info("Handoff aktif, mesaj atlanıyor [%s]", phone)
        return Response(status_code=200)

    # AI yanıtı üret
    try:
        reply_text, handoff = await agent.reply(phone, text)
    except Exception as exc:
        log.exception("Agent hatası [%s]: %s", phone, exc)
        await wa.send_text(
            phone,
            "Bir sorun yaşandı, lütfen birkaç dakika sonra tekrar deneyin.",
        )
        return Response(status_code=200)

    if reply_text:
        await wa.send_text(phone, reply_text)

    if handoff and settings.ADMIN_PHONE:
        # Admini bilgilendir
        summary = store._load(phone).get("handoff_summary", "")
        await wa.send_text(
            settings.ADMIN_PHONE,
            f"📋 Yeni devir talebi!\nNumara: {phone}\nÖzet: {summary}",
        )

    return Response(status_code=200)


# ── Admin endpoint'leri ────────────────────────────────────────────────────

@app.post("/admin/reset")
async def reset_conversation(phone: str, secret: str):
    if secret != settings.APP_SECRET:
        raise HTTPException(status_code=403, detail="Yetkisiz")
    store.reset(phone)
    return {"detail": f"{phone} konuşması sıfırlandı."}


@app.post("/admin/handoff/clear")
async def clear_handoff(phone: str, secret: str):
    if secret != settings.APP_SECRET:
        raise HTTPException(status_code=403, detail="Yetkisiz")
    store.clear_handoff(phone)
    return {"detail": f"{phone} handoff kaldırıldı, AI devreye alındı."}


@app.post("/admin/catalog/reload")
async def reload_catalog(secret: str):
    if secret != settings.APP_SECRET:
        raise HTTPException(status_code=403, detail="Yetkisiz")
    catalog.reload()
    return {"detail": "Katalog yeniden yüklendi.", "product_count": len(catalog.all_products())}
