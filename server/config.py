"""Application settings loaded from environment variables."""

import os
from urllib.parse import quote_plus
from pydantic_settings import BaseSettings

# Load .env from project root
_env_path = os.path.join(os.path.dirname(__file__), '..', '.env')


class Settings(BaseSettings):
    # PostgreSQL (where dude_replicate_meta schema lives)
    PG_HOST: str = "127.0.0.1"
    PG_PORT: int = 5432
    PG_USER: str = "postgres"
    PG_PASS: str = ""
    PG_DB: str = "enterprise_dw"

    # JWT
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRY_MINUTES: int = 10080  # 7 days

    # pgcrypto encryption key for endpoint credentials
    ENCRYPTION_KEY: str

    # Default admin (created on first startup if users table is empty)
    ADMIN_EMAIL: str
    ADMIN_PASSWORD: str

    # SQL Server (for seed data / adapters)
    MSSQL_HOST: str = "127.0.0.1"
    MSSQL_PORT: int = 1433
    MSSQL_USER: str = "sa"
    MSSQL_PASS: str = ""
    MSSQL_DB: str = "EnterpriseDW"

    # Oracle (for seed data / adapters)
    ORACLE_HOST: str = "127.0.0.1"
    ORACLE_PORT: int = 1521
    ORACLE_USER: str = "repltest"
    ORACLE_PASS: str = ""
    ORACLE_SYS_PASS: str = ""
    ORACLE_CDB_DSN: str = "127.0.0.1:1521/FREE"
    ORACLE_PDB_DSN: str = "127.0.0.1:1521/FREEPDB1"
    ORACLE_SCHEMA: str = "REPLTEST"

    # Server
    API_PORT: int = 8000

    # Paths
    ENGINE_SCRIPTS_DIR: str = os.path.join(os.path.dirname(__file__), '..', 'src')
    PROJECT_ROOT: str = os.path.join(os.path.dirname(__file__), '..')

    @property
    def database_url(self) -> str:
        pw = quote_plus(self.PG_PASS)
        return f"postgresql+asyncpg://{self.PG_USER}:{pw}@{self.PG_HOST}:{self.PG_PORT}/{self.PG_DB}"

    @property
    def database_url_sync(self) -> str:
        pw = quote_plus(self.PG_PASS)
        return f"postgresql+psycopg2://{self.PG_USER}:{pw}@{self.PG_HOST}:{self.PG_PORT}/{self.PG_DB}"

    model_config = {"env_file": _env_path, "extra": "ignore"}


settings = Settings()
