from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    app_name: str = "Business Platform"
    app_version: str = "1.1.0"
    debug: bool = False

    database_url: str = "postgresql+asyncpg://bizplatform:bizplatform@localhost:5432/bizplatform"
    database_url_sync: str = "postgresql://bizplatform:bizplatform@localhost:5432/bizplatform"
    redis_url: str = "redis://localhost:6379/0"

    secret_key: str = "change-me"
    access_token_expire_minutes: int = 60

    # Dynamic table prefix
    bo_table_prefix: str = "bo_"

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
