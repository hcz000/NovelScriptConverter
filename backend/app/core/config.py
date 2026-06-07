"""全局配置模块：定义项目路径、应用信息和 LLM 相关环境变量。"""
import os
from pathlib import Path

# ---------- 目录与文件路径 ----------
BACKEND_DIR = Path(__file__).resolve().parents[2]      # backend/ 根目录
DATA_DIR = BACKEND_DIR / "data"                         # 数据存储目录
UPLOADS_DIR = DATA_DIR / "uploads"                      # 上传文件存放目录
EXPORTS_DIR = DATA_DIR / "exports"                      # 导出文件存放目录
DATABASE_FILE = DATA_DIR / "studio.sqlite3"             # SQLite 数据库文件
LEGACY_STORE_FILE = DATA_DIR / "store.json"             # 旧版 JSON 数据文件（用于迁移）


def _load_env_file(path: Path) -> None:
    """加载本地 .env 文件，但不覆盖已存在的系统环境变量。"""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key:
            os.environ.setdefault(key, value)


_load_env_file(BACKEND_DIR.parent / ".env")
_load_env_file(BACKEND_DIR / ".env")

# ---------- 应用元信息 ----------
APP_TITLE = "AI Adaptation Studio API"                  # API 文档标题
APP_VERSION = "0.1.0"                                   # 应用版本号
API_PREFIX = "/api/v1"                                  # 所有 API 路由的统一前缀

# ---------- LLM（大语言模型）配置 ----------
# 模型供应商："rule"（纯规则引擎，默认）| "openai" | "bailian"（阿里云百炼）
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "rule")

# 通用 API Key（兼容旧版 OPENAI_API_KEY 环境变量）
LLM_API_KEY = os.getenv("LLM_API_KEY", os.getenv("OPENAI_API_KEY", ""))

# 模型名称
_OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
_BAILIAN_MODEL = os.getenv("BAILIAN_MODEL", "qwen-plus")
LLM_MODEL = os.getenv("LLM_MODEL", "")  # 通用设置优先

# 自定义 API 地址（不填则使用各供应商默认地址）
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")

# ---------- 各供应商预设配置 ----------
PROVIDER_CONFIG = {
    "openai": {
        "model": LLM_MODEL or _OPENAI_MODEL,
        "base_url": LLM_BASE_URL or "https://api.openai.com/v1",
        "api_key": LLM_API_KEY,
    },
    "bailian": {
        "model": LLM_MODEL or _BAILIAN_MODEL,
        "base_url": LLM_BASE_URL or "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key": LLM_API_KEY or os.getenv("DASHSCOPE_API_KEY", ""),
    },
}
