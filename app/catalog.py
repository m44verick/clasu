"""
Ürün kataloğu modülü.
Excel (.xlsx) veya CSV dosyasından ürünleri okur, arama ve filtreleme sağlar.

Beklenen sütunlar (büyük/küçük harf duyarsız):
  id, name/ad/ürün, description/açıklama, price/fiyat,
  category/kategori, stock/stok, unit/birim
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd

from app.config import get_settings

# ── Sütun adı eşlemeleri ───────────────────────────────────────────────────
_COL_MAP: dict[str, list[str]] = {
    "id":          ["id", "sku", "kod"],
    "name":        ["name", "ad", "ürün", "urun", "adi", "product"],
    "description": ["description", "açıklama", "aciklama", "detay"],
    "price":       ["price", "fiyat", "tutar"],
    "category":    ["category", "kategori"],
    "stock":       ["stock", "stok", "adet"],
    "unit":        ["unit", "birim"],
}


def _normalize(text: str) -> str:
    """Türkçe karakterleri koru, küçük harf yap, fazla boşlukları sil."""
    return re.sub(r"\s+", " ", text.strip().lower())


class ProductCatalog:
    def __init__(self, filepath: str | None = None):
        self._settings = get_settings()
        self._filepath = filepath or self._settings.PRODUCT_CATALOG_FILE
        self._df: pd.DataFrame = pd.DataFrame()
        self._load()

    # ── Yükleme ────────────────────────────────────────────────────────────

    def _load(self) -> None:
        p = Path(self._filepath)
        if not p.exists():
            return

        if p.suffix.lower() in {".xlsx", ".xls"}:
            df = pd.read_excel(p, dtype=str)
        elif p.suffix.lower() == ".csv":
            df = pd.read_csv(p, dtype=str)
        else:
            raise ValueError(f"Desteklenmeyen dosya formatı: {p.suffix}")

        # Sütun adlarını normalize et
        df.columns = [_normalize(c) for c in df.columns]
        df = self._remap_columns(df)
        df = df.fillna("")
        self._df = df

    def _remap_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        rename = {}
        for canonical, aliases in _COL_MAP.items():
            for col in df.columns:
                if col in aliases and col != canonical:
                    rename[col] = canonical
                    break
        return df.rename(columns=rename)

    def reload(self) -> None:
        """Kataloğu diskten yeniden yükler."""
        self._load()

    # ── Sorgular ───────────────────────────────────────────────────────────

    @property
    def is_loaded(self) -> bool:
        return not self._df.empty

    def all_products(self) -> list[dict]:
        return self._df.to_dict(orient="records")

    def categories(self) -> list[str]:
        if "category" not in self._df.columns:
            return []
        cats = self._df["category"].dropna().unique().tolist()
        return sorted(set(c.strip() for c in cats if c.strip()))

    def by_category(self, category: str) -> list[dict]:
        if "category" not in self._df.columns:
            return []
        mask = self._df["category"].str.lower() == category.lower()
        return self._df[mask].to_dict(orient="records")

    def by_id(self, product_id: str) -> dict | None:
        if "id" not in self._df.columns:
            return None
        mask = self._df["id"].str.lower() == product_id.lower()
        rows = self._df[mask]
        return rows.iloc[0].to_dict() if not rows.empty else None

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """
        Basit anahtar kelime araması.
        Ad, açıklama ve kategori sütunlarında arar.
        Eşleşme sayısına göre sıralar.
        """
        if self._df.empty:
            return []

        terms = [_normalize(t) for t in query.split() if t.strip()]
        if not terms:
            return []

        search_cols = [c for c in ["name", "description", "category"] if c in self._df.columns]

        def score_row(row: Any) -> int:
            combined = " ".join(_normalize(str(row[c])) for c in search_cols)
            return sum(1 for t in terms if t in combined)

        scores = self._df.apply(score_row, axis=1)
        filtered = self._df[scores > 0].copy()
        filtered["_score"] = scores[scores > 0]
        filtered = filtered.sort_values("_score", ascending=False).head(top_k)
        filtered = filtered.drop(columns=["_score"])
        return filtered.to_dict(orient="records")

    def format_product(self, product: dict) -> str:
        """Ürünü okunabilir metin olarak döner (WhatsApp mesajı için)."""
        lines: list[str] = []
        if product.get("name"):
            lines.append(f"*{product['name']}*")
        if product.get("id"):
            lines.append(f"Kod: {product['id']}")
        if product.get("category"):
            lines.append(f"Kategori: {product['category']}")
        if product.get("price"):
            unit = product.get("unit", "")
            lines.append(f"Fiyat: {product['price']} TL" + (f" / {unit}" if unit else ""))
        if product.get("stock"):
            lines.append(f"Stok: {product['stock']}")
        if product.get("description"):
            lines.append(f"\n{product['description']}")
        return "\n".join(lines)

    def format_list(self, products: list[dict], max_items: int = 10) -> str:
        """Ürün listesini numaralandırılmış metin olarak döner."""
        if not products:
            return "Ürün bulunamadı."
        items = products[:max_items]
        lines = []
        for i, p in enumerate(items, 1):
            name = p.get("name", "—")
            price = f"{p['price']} TL" if p.get("price") else ""
            lines.append(f"{i}. {name}" + (f" — {price}" if price else ""))
        if len(products) > max_items:
            lines.append(f"... ve {len(products) - max_items} ürün daha.")
        return "\n".join(lines)
