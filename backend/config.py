"""Configuration management for Triathlon App.
Stores user settings, credentials (Garmin, Intervals.icu, Gemini AI),
and athletic baseline parameters securely in a local JSON config.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent.parent
APP_DATA_DIR = Path.home() / ".tricoach"
APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = APP_DATA_DIR / "athlete_config.json"
HISTORICO_FILE = BASE_DIR / "historico_semanal.json"

DEFAULT_GARMIN_TOKEN_DIR = (
    Path.home()
    / "AppData"
    / "Local"
    / "garmin-mcp"
    / "garmin-mcp"
    / "Cache"
    / "garth"
)


class AppConfig(BaseModel):
    # Garmin Connect
    garmin_email: Optional[str] = ""
    garmin_password: Optional[str] = ""
    garmin_token_dir: str = str(DEFAULT_GARMIN_TOKEN_DIR)
    garmin_connected: bool = False
    garmin_athlete_name: Optional[str] = "Pastor"

    # Intervals.icu
    intervals_athlete_id: Optional[str] = ""
    intervals_api_key: Optional[str] = ""
    intervals_connected: bool = False

    # AI & Coach
    gemini_api_key: Optional[str] = ""
    athlete_phase: str = "Periodo de Base (Aerobic Base)"
    athlete_discipline: str = "Triatlón (Natación, Ciclismo, Carrera, Fuerza)"

    # Athletic Thresholds & Zones (defaults or loaded from intervals/garmin)
    ftp: int = 348  # FTP en Ciclismo (W)
    css_pace: str = "1:29.0"  # CSS Natación (min/100m)
    run_threshold_pace: str = "3:40"  # Ritmo Umbral Carrera (min/km)
    max_hr: int = 183
    rest_hr_baseline: int = 36
    lthr: int = 159  # Umbral de Lactato FC (bpm)
    weight: Optional[float] = 75.2  # Peso corporal (kg)
    thresholds_source: str = "intervals.icu"
    thresholds_last_sync: Optional[str] = None
    disciplines_thresholds: Optional[Dict[str, Any]] = None


def _apply_env_overrides(cfg: AppConfig) -> AppConfig:
    """Overlays environment variables for seamless cloud deployment."""
    import base64

    env_email = os.environ.get("GARMIN_EMAIL")
    if env_email:
        cfg.garmin_email = env_email.strip()
    env_pass = os.environ.get("GARMIN_PASSWORD")
    if env_pass:
        cfg.garmin_password = env_pass.strip()

    env_int_id = os.environ.get("INTERVALS_ATHLETE_ID")
    if env_int_id:
        cfg.intervals_athlete_id = env_int_id.strip()
        cfg.intervals_connected = True
    env_int_key = os.environ.get("INTERVALS_API_KEY")
    if env_int_key:
        cfg.intervals_api_key = env_int_key.strip()
        cfg.intervals_connected = True

    env_gemini = os.environ.get("GEMINI_API_KEY")
    if env_gemini:
        cfg.gemini_api_key = env_gemini.strip()

    # Base64 Garmin tokens from environment
    env_tokens_b64 = os.environ.get("GARMIN_TOKENS_B64")
    if env_tokens_b64:
        try:
            token_dir = Path(cfg.garmin_token_dir)
            token_dir.mkdir(parents=True, exist_ok=True)
            token_file = token_dir / "garmin_tokens.json"
            decoded = base64.b64decode(env_tokens_b64).decode("utf-8")
            with open(token_file, "w", encoding="utf-8") as f:
                f.write(decoded)
            cfg.garmin_connected = True
        except Exception as e:
            print(f"Warning: could not decode GARMIN_TOKENS_B64: {e}")

    token_p = Path(cfg.garmin_token_dir)
    if token_p.exists() and (token_p / "garmin_tokens.json").exists():
        cfg.garmin_connected = True

    return cfg


def load_config() -> AppConfig:
    # 1. Primary config file (.tricoach/athlete_config.json)
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                cfg = AppConfig(**data)
                return _apply_env_overrides(cfg)
        except Exception:
            pass

    # 2. Workspace root fallback (athlete_config.json)
    root_cfg = BASE_DIR / "athlete_config.json"
    if root_cfg.exists():
        try:
            with open(root_cfg, "r", encoding="utf-8") as f:
                data = json.load(f)
                cfg = AppConfig(**data)
                return _apply_env_overrides(cfg)
        except Exception:
            pass

    # 3. Environment variables or baseline defaults
    cfg = AppConfig()
    cfg = _apply_env_overrides(cfg)
    save_config(cfg)
    return cfg


def save_config(cfg: AppConfig) -> None:
    try:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg.model_dump(), f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving config: {e}")
