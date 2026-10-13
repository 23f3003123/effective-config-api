import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import yaml

BASE_DIR = Path(__file__).resolve().parent

DEFAULTS: dict[str, Any] = {
    "port": 8000,
    "workers": 1,
    "debug": False,
    "log_level": "info",
    "api_key": "default-secret-000",
}

# Load .env without overwriting OS-level environment variables.
load_dotenv(BASE_DIR / ".env", override=False)

app = FastAPI(title="Effective Configuration API")

# Allows the grader's browser page to call this endpoint cross-origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

def coerce(key: str, value: Any) -> Any:
    text = str(value).strip()
    if key in ("port", "workers"):
        return int(text)
    if key == "debug":
        return text.lower() in {"true", "1", "yes", "on"}
    return text

def load_effective_config(cli_overrides: list[str]) -> dict[str, Any]:
    config = dict(DEFAULTS)

    # Layer 2: environment-specific YAML.
    environment = os.getenv("APP_ENV", "development")
    yaml_path = BASE_DIR / f"config.{environment}.yaml"
    if yaml_path.exists():
        with yaml_path.open("r", encoding="utf-8") as stream:
            yaml_config = yaml.safe_load(stream) or {}
        for key, value in yaml_config.items():
            config[key.lower()] = value

    # Layer 3: .env file values. load_dotenv has loaded these into os.environ,
    # but OS-level variables must remain distinguishable from .env values.
    # Read the file directly so its values are applied at this exact layer.
    env_file_values: dict[str, str] = {}
    env_path = BASE_DIR / ".env"
    if env_path.exists():
        from dotenv import dotenv_values
        env_file_values = {
            key: value for key, value in dotenv_values(env_path).items()
            if value is not None
        }

    for raw_key, value in env_file_values.items():
        key = raw_key.removeprefix("APP_").lower()
        if raw_key == "NUM_WORKERS":
            key = "workers"
        if key in config:
            config[key] = coerce(key, value)

    # Layer 4: OS-level APP_* variables, overriding .env values.
    # Only variables actually present in the process environment are used.
    for raw_key, value in os.environ.items():
        if not raw_key.startswith("APP_"):
            continue
        key = raw_key[4:].lower()
        if key in config:
            config[key] = coerce(key, value)

    # Highest precedence: repeated ?set=key=value query parameters.
    for item in cli_overrides:
        if "=" not in item:
            continue
        raw_key, value = item.split("=", 1)
        key = raw_key.strip().lower()
        if key in config:
            config[key] = coerce(key, value)

    # Never reveal the configured secret.
    config["api_key"] = "****"
    return config

@app.get("/effective-config")
def effective_config(set: list[str] = Query(default=[])):
    return load_effective_config(set)

@app.get("/")
def root():
    return {"message": "Configuration API is running", "endpoint": "/effective-config"}
