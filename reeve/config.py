from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    mongo_uri: str = Field(default="mongodb://localhost:27017")
    mongo_db: str = Field(default="reeve")

    aws_region: str = Field(default="us-east-1")
    audit_table: str = Field(default="reeve-audit-events")
    audit_gsi_entity: str = Field(default="entity_id-ts-index")
    # 'dynamo' (prod) | 'mongo' (local dev — same Mongo as the entity store).
    audit_backend: str = Field(default="mongo")
    proposals_backend: str = Field(default="mongo")
    proposals_table: str = Field(default="reeve-proposals")
    proposals_gsi_status: str = Field(default="status_created-index")

    # Auth — JWT issued by the dev-token endpoint (later: SSO/OIDC).
    jwt_secret: str = Field(default="reeve-dev-secret-change-me")
    jwt_algorithm: str = Field(default="HS256")
    jwt_ttl_minutes: int = Field(default=60 * 12)  # 12h
    # PBKDF2-HMAC-SHA256 work factor (OWASP 2023 floor is 600k). Lower it in
    # tests for speed; never below ~100k in production.
    password_iterations: int = Field(default=600_000)
    # The id-based dev-token endpoint is a backdoor — disable in prod.
    enable_dev_token: bool = Field(default=True)

    # Categorizer: 'rules' | 'cascade' (rules → LLM fallback for `other`).
    categorizer: str = Field(default="rules")

    # LLM provider: 'anthropic' (direct API, ANTHROPIC_API_KEY) or
    # 'bedrock' (AWS Bedrock — uses the standard AWS credential chain,
    # IAM role / env / profile).
    llm_provider: str = Field(default="anthropic")
    aws_bedrock_region: str = Field(default="us-east-1")
    # JSON map from friendly model id → Bedrock inference-profile id.
    # Example: '{"claude-sonnet-4-6":"us.anthropic.claude-sonnet-4-6-20251029-v1:0"}'
    bedrock_model_aliases: str = Field(default="")

    anthropic_api_key: str | None = None


settings = Settings()
