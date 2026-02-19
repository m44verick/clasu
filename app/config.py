from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # WhatsApp Business Cloud API
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_ACCESS_TOKEN: str = ""
    WHATSAPP_VERIFY_TOKEN: str = "my_secret_verify_token_123"

    # Anthropic
    ANTHROPIC_API_KEY: str = ""

    # Şirket
    COMPANY_NAME: str = "Şirket"
    AGENT_NAME: str = "Asistan"

    # Ürün kataloğu
    PRODUCT_CATALOG_FILE: str = "data/products.xlsx"

    # İnsan devreye alma
    ADMIN_PHONE: str = ""

    # Uygulama
    APP_SECRET: str = "change_me_in_production"
    MAX_CONVERSATION_TURNS: int = 50

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
