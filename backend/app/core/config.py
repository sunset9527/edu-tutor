"""应用配置：从 .env 加载，pydantic-settings 管理"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ 目录（.env 所在位置，绝对路径避免 cwd 依赖）
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- MySQL ----
    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = "123456"
    mysql_db: str = "edu_tutor"

    # ---- 安全（v1.1）----
    secret_key: str = "edututor-dev-secret-change-me"

    # ---- DeepSeek ----
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    # ---- Chroma（v0.2 记忆引擎用）----
    chroma_dir: str = "./data/chroma_db"

    # ---- 记忆参数（v0.2 用）----
    working_memory_window_size: int = 10
    decay_stability: float = 7.0
    consolidation_threshold: int = 3

    # ---- 遗忘曲线（v0.3）----
    decay_lambda: float = 0.1  # 遗忘速率 λ：越大忘得越快（评测时对比不同 λ）
    review_interval_base: int = 1  # 首次复习间隔（天）

    @property
    def sqlalchemy_url(self) -> str:
        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_db}?charset=utf8mb4"
        )

    @property
    def llm_configured(self) -> bool:
        """真实 Key 判定：非空 且 不含占位符标记（your/here/sk-you）"""
        key = self.deepseek_api_key.strip()
        if not key:
            return False
        lowered = key.lower()
        return "your" not in lowered and "here" not in lowered


settings = Settings()
