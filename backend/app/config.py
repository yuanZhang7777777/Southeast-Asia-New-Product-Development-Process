from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


LOCAL_APP_ENVS = {"local", "test", "testing"}
DEFAULT_AUTH_SECRET_KEY = "local-dev-auth-secret-change-me"
WEAK_AUTH_SECRET_KEYS = {DEFAULT_AUTH_SECRET_KEY, "change-this-in-production"}


def is_local_app_env(value: str) -> bool:
    return value.strip().lower() in LOCAL_APP_ENVS


class Settings(BaseSettings):
    app_env: str = "local"
    app_name: str = "Hengzhe New Product Workflow"
    database_url: str = "sqlite:///./workflow_dev.db"
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8080,http://127.0.0.1:8080"
    dingtalk_webhook_url: str = ""
    dingtalk_client_id: str = ""
    dingtalk_client_secret: str = ""
    dingtalk_agent_id: str = ""
    dingtalk_robot_code: str = ""
    dingtalk_arrival_card_template_id: str = ""
    dingtalk_card_autosend_enabled: bool = False
    dingtalk_card_test_receiver_name: str = ""
    dingtalk_test_recipient_user_id: str = ""
    dingtalk_user_sync_enabled: bool = False
    platform_base_url: str = "http://127.0.0.1:5173"
    auth_required: bool = False
    auth_secret_key: str = DEFAULT_AUTH_SECRET_KEY
    auth_token_ttl_seconds: int = 86400
    write_back_to_online_sheets: bool = False
    workflow_automation_enabled: bool = False
    plm_sync_enabled: bool = False
    plm_base_url: str = ""
    plm_open_base_url: str = ""
    plm_username: str = ""
    plm_password: str = ""
    plm_bloc_name: str = "\u96c6\u56e2\u516b\u90e8"
    plm_cache_dir: str = "/data/plm"
    erp_login_url: str = ""
    erp_product_list_url: str = ""
    erp_download_list_url: str = ""
    erp_username: str = ""
    erp_password: str = ""
    finebi_base_url: str = ""
    finebi_username: str = ""
    finebi_password: str = ""
    finebi_report_id: str = ""
    finebi_payload_file: str = ""
    finebi_cache_dir: str = "/data/finebi"
    finebi_auto_pull_enabled: bool = False
    finebi_scheduler_enabled: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    def __init__(self, **values: object) -> None:
        super().__init__(**values)
        if not is_local_app_env(self.app_env) and self.database_url.strip().lower().startswith("sqlite"):
            raise ValueError("SQLite is only allowed for local/test environments; set DATABASE_URL to PostgreSQL.")
        self.auth_secret_key = self.auth_secret_key.strip()
        if not is_local_app_env(self.app_env) and (not self.auth_secret_key or self.auth_secret_key in WEAK_AUTH_SECRET_KEYS):
            raise ValueError("Default AUTH_SECRET_KEY is only allowed for local/test environments.")
        if self.plm_sync_enabled and not all(
            [self.plm_base_url.strip(), self.plm_username.strip(), self.plm_password]
        ):
            raise ValueError("PLM credentials are required when PLM sync is enabled.")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
