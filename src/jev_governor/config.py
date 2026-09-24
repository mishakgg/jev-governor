"""Configuration: environment, .env file, data directory, non-secret settings.

The secret value (TYPESAFE_API_KEY) is never stored on the Settings object and
never printed. Use :func:`read_api_key` only at the moment a live call is made,
and only when the caller has already established explicit authorization.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_JEV_MODEL = "jev-1.13.0"
JEV_ENDPOINT = "https://api.typesafe.ai/v1/systemone"
JEV_RUBRIC_VERSION = "alpha-1"

APP_DIR_NAME = "jev-governor"


def _strtobool(value: str, default: bool) -> bool:
    v = value.strip().lower()
    if v in {"1", "true", "yes", "on"}:
        return True
    if v in {"0", "false", "no", "off"}:
        return False
    return default


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    mode: str = "advisory"
    jev_enabled: bool = False
    jev_model: str = DEFAULT_JEV_MODEL
    live_max_attempts: int = 0
    jev_timeout_seconds: float = 10.0
    share_raw_content: bool = False
    api_key_present: bool = False


def load_dotenv_file(path: Path) -> dict[str, str]:
    """Parse a minimal KEY=VALUE dotenv file. No shell expansion, no export."""
    values: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return values
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip("'\"")
        if key and key not in values:
            values[key] = val
    return values


def default_data_dir() -> Path:
    override = os.environ.get("JEV_GOVERNOR_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA", "")
        if base:
            return Path(base) / APP_DIR_NAME
        return Path.home() / ("." + APP_DIR_NAME)
    xdg = os.environ.get("XDG_DATA_HOME", "")
    if xdg:
        return Path(xdg) / APP_DIR_NAME
    return Path.home() / ".local" / "share" / APP_DIR_NAME


def load_settings(data_dir: str | os.PathLike[str] | None = None) -> Settings:
    file_values = load_dotenv_file(Path.cwd() / ".env")

    def get(name: str, default: str = "") -> str:
        if name in os.environ:
            return os.environ[name]
        return file_values.get(name, default)

    if data_dir is not None:
        resolved = Path(data_dir).expanduser()
    else:
        resolved = default_data_dir()
    try:
        timeout = float(get("JEV_GOVERNOR_JEV_TIMEOUT_SECONDS", "10"))
    except ValueError:
        timeout = 10.0
    try:
        attempts = int(get("JEV_GOVERNOR_LIVE_MAX_ATTEMPTS", "0"))
    except ValueError:
        attempts = 0
    key = get("TYPESAFE_API_KEY", "")
    return Settings(
        data_dir=resolved,
        mode=get("JEV_GOVERNOR_MODE", "advisory") or "advisory",
        jev_enabled=_strtobool(get("JEV_GOVERNOR_JEV_ENABLED", "false"), False),
        jev_model=get("JEV_GOVERNOR_JEV_MODEL", DEFAULT_JEV_MODEL) or DEFAULT_JEV_MODEL,
        live_max_attempts=max(0, attempts),
        jev_timeout_seconds=min(max(timeout, 1.0), 120.0),
        share_raw_content=_strtobool(get("JEV_GOVERNOR_SHARE_RAW_CONTENT", "false"), False),
        api_key_present=bool(key.strip()),
    )


def read_api_key() -> str | None:
    """Return the secret value, or None. Callers must never log it."""
    key = os.environ.get("TYPESAFE_API_KEY", "")
    if not key.strip():
        key = load_dotenv_file(Path.cwd() / ".env").get("TYPESAFE_API_KEY", "")
    key = key.strip()
    return key or None


def ensure_data_dir(settings: Settings) -> Path:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings.data_dir
