#!/usr/bin/env python3
"""
Örnek ürün kataloğu Excel dosyası oluşturur.
Çalıştır: python scripts/create_sample_catalog.py

Çıktı: data/products.xlsx
"""
from pathlib import Path
import pandas as pd

PRODUCTS = [
    # Elektronik
    {"id": "EL001", "name": "Laptop Pro 15", "category": "Elektronik",
     "price": "24999", "unit": "adet", "stock": "12",
     "description": "15.6\" FHD IPS ekran, Intel i7-1255U, 16GB RAM, 512GB NVMe SSD, Windows 11 Pro."},
    {"id": "EL002", "name": "Kablosuz Kulaklık X1", "category": "Elektronik",
     "price": "1299", "unit": "adet", "stock": "45",
     "description": "Aktif gürültü engelleme, 30 saat pil ömrü, Bluetooth 5.3."},
    {"id": "EL003", "name": "Mekanik Klavye TKL", "category": "Elektronik",
     "price": "899", "unit": "adet", "stock": "28",
     "description": "Red switch, RGB aydınlatma, alüminyum kasa, USB-C bağlantı."},
    {"id": "EL004", "name": "4K Monitör 27\"", "category": "Elektronik",
     "price": "8499", "unit": "adet", "stock": "8",
     "description": "3840x2160 çözünürlük, IPS panel, 144Hz, HDR400, USB-C 65W."},
    {"id": "EL005", "name": "USB-C Hub 7in1", "category": "Elektronik",
     "price": "449", "unit": "adet", "stock": "60",
     "description": "USB-C, 4K HDMI, 3×USB-A, SD kart, 100W PD şarj."},

    # Ofis
    {"id": "OF001", "name": "Ergonomik Sandalye", "category": "Ofis",
     "price": "4599", "unit": "adet", "stock": "15",
     "description": "Mesh sırtlık, ayarlanabilir kol, bel desteği, 5 yıl garanti."},
    {"id": "OF002", "name": "Ayaklı Masa 140cm", "category": "Ofis",
     "price": "3299", "unit": "adet", "stock": "7",
     "description": "Elektrikli yükseklik ayarlı, 140×70cm MDF masa yüzeyi, hafıza tuşları."},
    {"id": "OF003", "name": "Beyaz Tahta 90×120", "category": "Ofis",
     "price": "799", "unit": "adet", "stock": "20",
     "description": "Alüminyum çerçeve, kalemlik ve silgi dahil, duvara montaj."},
    {"id": "OF004", "name": "Dosyalama Dolabı", "category": "Ofis",
     "price": "2199", "unit": "adet", "stock": "5",
     "description": "4 çekmece, A4/Foolscap uyumlu, kilitli, antrasit renk."},

    # Yazılım / Lisans
    {"id": "YZ001", "name": "Office 365 Business", "category": "Yazılım",
     "price": "2499", "unit": "yıl/kullanıcı", "stock": "999",
     "description": "Word, Excel, PowerPoint, Teams, 1TB OneDrive, 5 cihaza kadar."},
    {"id": "YZ002", "name": "Antivirüs Pro 3 Cihaz", "category": "Yazılım",
     "price": "349", "unit": "yıl", "stock": "999",
     "description": "Gerçek zamanlı koruma, fidye yazılımı kalkanı, VPN dahil."},

    # Aksesuar
    {"id": "AK001", "name": "Mouse Pad XL", "category": "Aksesuar",
     "price": "149", "unit": "adet", "stock": "80",
     "description": "90×40cm, 4mm kalınlık, dikiş kenarlı, su geçirmez yüzey."},
    {"id": "AK002", "name": "Laptop Soğutucu", "category": "Aksesuar",
     "price": "299", "unit": "adet", "stock": "35",
     "description": "2 fanlı, USB güçlü, 15.6\"'ye kadar uyumlu, mavi LED."},
    {"id": "AK003", "name": "Webcam 1080p", "category": "Aksesuar",
     "price": "549", "unit": "adet", "stock": "22",
     "description": "Full HD 30fps, gizlilik kapağı, dahili mikrofon, plug & play."},
]

def main():
    out_path = Path("data/products.xlsx")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(PRODUCTS)
    df.to_excel(out_path, index=False)
    print(f"✅ Örnek katalog oluşturuldu: {out_path} ({len(df)} ürün)")

if __name__ == "__main__":
    main()
