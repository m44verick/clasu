"""
OpenAI GPT satış ajanı.

Function calling ile ürün kataloğunu sorgular, gerektiğinde insan temsilciye devreder.

Araçlar (functions):
  search_products       – ürün arama
  get_product           – ID ile ürün getirme
  list_categories       – kategori listesi
  products_by_category  – kategoriye göre ürün listeleme
  handoff_to_human      – insan temsilciye devretme
"""
from __future__ import annotations

import json
import logging
from typing import Any

from openai import AsyncOpenAI

from app.catalog import ProductCatalog
from app.config import get_settings
from app.conversation_store import ConversationStore

log = logging.getLogger(__name__)

# ── Araç tanımları ─────────────────────────────────────────────────────────

TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": (
                "Ürün kataloğunda anahtar kelimeyle arama yapar. "
                "Müşteri belirli bir ürün sorduğunda kullan."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Arama terimi (ürün adı, özellik, vb.)",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Döndürülecek maksimum sonuç sayısı (varsayılan: 5)",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_product",
            "description": "Ürün ID/kodu ile tek bir ürünün tam detayını getirir.",
            "parameters": {
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
    },
    {
        "type": "function",
        "function": {
            "name": "list_categories",
            "description": "Katalogdaki tüm ürün kategorilerini listeler.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "products_by_category",
            "description": "Belirli bir kategorideki ürünleri listeler.",
            "parameters": {
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
    },
    {
        "type": "function",
        "function": {
            "name": "handoff_to_human",
            "description": (
                "Konuşmayı insan temsilciye devreder. "
                "Müşteri insan istemesi, iade/şikayet/özel teklif talep etmesi "
                "veya sorunun çözülemediği durumlarda kullan."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Devir nedeni (kısa)",
                    },
                    "summary": {
                        "type": "string",
                        "description": "Konuşma özeti (temsilci için)",
                    },
                },
                "required": ["reason", "summary"],
            },
        },
    },
]


# ── Ajan ───────────────────────────────────────────────────────────────────

class SalesAgent:
    def __init__(self, catalog: ProductCatalog, store: ConversationStore):
        self._catalog = catalog
        self._store = store
        self._settings = get_settings()
        self._client = AsyncOpenAI(api_key=self._settings.OPENAI_API_KEY)

    def _system_prompt(self) -> str:
        return (
            f"Sen {self._settings.COMPANY_NAME} adına çalışan {self._settings.AGENT_NAME} adlı "
            "bir satış asistanısın. WhatsApp üzerinden müşterilere yardım ediyorsun.\n\n"
            "Görevlerin:\n"
            "• Ürün kataloğunu kullanarak müşterilerin sorularını yanıtla.\n"
            "• Fiyat, stok, özellik bilgilerini doğru aktar.\n"
            "• Satın alma sürecinde yardımcı ol.\n"
            "• Kataloğda olmayan, iade/şikayet veya insan gerektiren durumlarda "
            "handoff_to_human fonksiyonunu kullan.\n\n"
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
        # Sistem mesajı her seferinde başa eklenir (geçmişte saklanmaz)
        full_messages = [{"role": "system", "content": self._system_prompt()}] + messages
        full_messages.append({"role": "user", "content": user_text})

        handoff = False
        reply_text = ""

        # Agentic döngü
        while True:
            response = await self._client.chat.completions.create(
                model=self._settings.OPENAI_MODEL,
                tools=TOOLS,
                tool_choice="auto",
                messages=full_messages,
            )

            msg = response.choices[0].message
            finish_reason = response.choices[0].finish_reason

            # Mesajı geçmişe ekle
            full_messages.append(msg)

            if finish_reason == "stop":
                reply_text = msg.content or ""
                break

            if finish_reason == "tool_calls" and msg.tool_calls:
                for tc in msg.tool_calls:
                    fn_name = tc.function.name
                    try:
                        fn_args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        fn_args = {}

                    result, should_handoff = self._run_tool(phone, fn_name, fn_args)
                    if should_handoff:
                        handoff = True

                    full_messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result,
                    })

                if handoff:
                    # Handoff sonrası son bir yanıt al
                    final = await self._client.chat.completions.create(
                        model=self._settings.OPENAI_MODEL,
                        messages=full_messages,
                    )
                    reply_text = final.choices[0].message.content or ""
                    break
            else:
                reply_text = msg.content or ""
                break

        # Sistem mesajını çıkar, sadece user/assistant/tool geçmişini kaydet
        history = [m for m in full_messages if not (
            isinstance(m, dict) and m.get("role") == "system"
        )]
        # openai ChatCompletionMessage nesnelerini dict'e çevir
        history_dicts = []
        for m in history:
            if isinstance(m, dict):
                history_dicts.append(m)
            else:
                # ChatCompletionMessage nesnesi
                d: dict[str, Any] = {"role": m.role, "content": m.content or ""}
                if m.tool_calls:
                    d["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in m.tool_calls
                    ]
                history_dicts.append(d)

        self._store.set_messages(phone, history_dicts)
        return reply_text, handoff

    # ── Araç çalıştırıcı ──────────────────────────────────────────────────

    def _run_tool(self, phone: str, name: str, inputs: dict) -> tuple[str, bool]:
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
            return f"Araç hatası: {exc}", False

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
