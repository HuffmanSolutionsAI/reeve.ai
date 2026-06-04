from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    mongo_uri: str = Field(default="mongodb://localhost:27017")
    mongo_db: str = Field(default="reeve")

    aws_region: str = Field(default="us-east-1")
    audit_table: str = Field(default="reeve-audit-events")
    audit_gsi_entity: str = Field(default="entity_id-ts-index")

    anthropic_api_key: str | None = None


settings = Settings()
