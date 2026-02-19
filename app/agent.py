"""
Claude AI satış ajanı.

Tool use ile ürün kataloğunu sorgular, gerektiğinde insan temsilciye devreder.

Araçlar (tools):
  search_products   – ürün arama
  get_product       – ID ile ürün getirme
  list_categories   – kategori listesi
  products_by_category – kategoriye göre ürün listeleme
  handoff_to_human  – insan temsilciye devretme
"""
from __future__ import annotations

import json
import logging
from typing import Any

import anthropic

from app.catalog import ProductCatalog
from app.config import get_settings
from app.conversation_store import ConversationStore

log = logging.getLogger(__name__)

# ── Araç tanımları ─────────────────────────────────────────────────────────

TOOLS: list[dict] = [
    {
        "name": "search_products",
        "description": (
            "Ürün kataloğunda anahtar kelimeyle arama yapar. "
            "Müşteri belirli bir ürün sorduğunda kullan."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Arama terimi (ürün adı, özellik, vb.)",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Döndürülecek maksimum sonuç sayısı (varsayılan: 5)",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_product",
        "description": "Ürün ID/kodu ile tek bir ürünün tam detayını getirir.",
        "input_schema": {
            "type": "object",
            "properties": {
                "product_id": {
                    "type": "string",
                    "description": "Ürün ID veya SKU kodu",
                }
            },
            "required": ["product_id"],
        },
    },
    {
        "name": "list_categories",
        "description": "Katalogdaki tüm ürün kategorilerini listeler.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "products_by_category",
        "description": "Belirli bir kategorideki ürünleri listeler.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Kategori adı (list_categories ile öğrenilebilir)",
                }
            },
            "required": ["category"],
        },
    },
    {
        "name": "handoff_to_human",
        "description": (
            "Konuşmayı insan temsilciye devreder. "
            "Müşteri insan istemesi, iade/şikayet/özel teklif talep etmesi "
            "veya sorunun çözülemediği durumlarda kullan."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Devir nedeni (kısa, İngilizce veya Türkçe)",
                },
                "summary": {
                    "type": "string",
                    "description": "Konuşma özeti (temsilci için)",
                },
            },
            "required": ["reason", "summary"],
        },
    },
]


# ── Ajan ───────────────────────────────────────────────────────────────────

class SalesAgent:
    def __init__(self, catalog: ProductCatalog, store: ConversationStore):
        self._catalog = catalog
        self._store = store
        self._settings = get_settings()
        self._client = anthropic.AsyncAnthropic(api_key=self._settings.ANTHROPIC_API_KEY)

    def _system_prompt(self) -> str:
        return (
            f"Sen {self._settings.COMPANY_NAME} adına çalışan {self._settings.AGENT_NAME} adlı "
            "bir satış asistanısın. WhatsApp üzerinden müşterilere yardım ediyorsun.\n\n"
            "Görevlerin:\n"
            "• Ürün kataloğunu kullanarak müşterilerin sorularını yanıtla.\n"
            "• Fiyat, stok, özellik bilgilerini doğru aktar.\n"
            "• Satın alma sürecinde yardımcı ol.\n"
            "• Kataloğda olmayan, iade/şikayet veya insan gerektiren durumlarda "
            "handoff_to_human aracını kullan.\n\n"
            "Kurallar:\n"
            "• Türkçe yaz, samimi ve yardımsever ol.\n"
            "• Kısa mesajlar gönder (WhatsApp formatına uygun).\n"
            "• Bilmediğin bir şeyi uydurma; araçları kullan veya insana devret.\n"
            "• Fiyatları veya stok durumunu tahmin etme, her zaman katalogdan kontrol et."
        )

    async def reply(self, phone: str, user_text: str) -> tuple[str, bool]:
        """
        Kullanıcı mesajına yanıt üretir.

        Döner: (yanıt_metni, handoff_oldu_mu)
        """
        messages = self._store.get_messages(phone)
        messages.append({"role": "user", "content": user_text})

        handoff = False
        reply_text = ""

        # Agentic döngü: araç kullanımı bitene kadar devam et
        while True:
            response = await self._client.messages.create(
                model="claude-opus-4-6",
                max_tokens=1024,
                system=self._system_prompt(),
                tools=TOOLS,
                messages=messages,
            )

            # Assistant mesajını geçmişe ekle
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn":
                # Metin yanıtı al
                for block in response.content:
                    if hasattr(block, "text"):
                        reply_text = block.text
                break

            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue
                    result, should_handoff = self._run_tool(phone, block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })
                    if should_handoff:
                        handoff = True

                messages.append({"role": "user", "content": tool_results})

                if handoff:
                    # Handoff sonrası son bir yanıt al ve döngüyü kır
                    final = await self._client.messages.create(
                        model="claude-opus-4-6",
                        max_tokens=512,
                        system=self._system_prompt(),
                        tools=TOOLS,
                        messages=messages,
                    )
                    for block in final.content:
                        if hasattr(block, "text"):
                            reply_text = block.text
                    break
            else:
                # Bilinmeyen stop_reason
                break

        self._store.set_messages(phone, messages)
        return reply_text, handoff

    # ── Araç çalıştırıcı ──────────────────────────────────────────────────

    def _run_tool(self, phone: str, name: str, inputs: dict) -> tuple[str, bool]:
        """Aracı çalıştırır, (sonuç_metni, handoff_mu) döner."""
        try:
            if name == "search_products":
                return self._tool_search(inputs), False

            if name == "get_product":
                return self._tool_get_product(inputs), False

            if name == "list_categories":
                return self._tool_list_categories(), False

            if name == "products_by_category":
                return self._tool_by_category(inputs), False

            if name == "handoff_to_human":
                return self._tool_handoff(phone, inputs), True

            return f"Bilinmeyen araç: {name}", False

        except Exception as exc:
            log.exception("Araç hatası [%s]: %s", name, exc)
            return f"Araç çalışırken hata: {exc}", False

    def _tool_search(self, inputs: dict) -> str:
        query = inputs.get("query", "")
        top_k = int(inputs.get("top_k", 5))
        results = self._catalog.search(query, top_k=top_k)
        if not results:
            return "Bu arama için sonuç bulunamadı."
        return self._catalog.format_list(results)

    def _tool_get_product(self, inputs: dict) -> str:
        pid = inputs.get("product_id", "")
        product = self._catalog.by_id(pid)
        if not product:
            return f"'{pid}' kodlu ürün bulunamadı."
        return self._catalog.format_product(product)

    def _tool_list_categories(self) -> str:
        cats = self._catalog.categories()
        if not cats:
            return "Kategori bilgisi bulunamadı."
        return "Kategoriler:\n" + "\n".join(f"• {c}" for c in cats)

    def _tool_by_category(self, inputs: dict) -> str:
        cat = inputs.get("category", "")
        products = self._catalog.by_category(cat)
        if not products:
            return f"'{cat}' kategorisinde ürün bulunamadı."
        return self._catalog.format_list(products)

    def _tool_handoff(self, phone: str, inputs: dict) -> str:
        reason = inputs.get("reason", "belirtilmedi")
        summary = inputs.get("summary", "")
        self._store.set_handoff(phone, reason, summary)
        return f"Handoff kaydedildi. Neden: {reason}"
