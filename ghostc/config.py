"""Load and validate privacy.yaml against schemas/privacy-config.schema.json."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "privacy-config.schema.json"


class ConfigError(Exception):
    pass


def load_config(path: str | Path) -> dict:
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"config not found: {path}")
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))

    try:
        import jsonschema
    except ModuleNotFoundError:
        # schema validation is best-effort until deps are installed
        return cfg

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = sorted(jsonschema.Draft202012Validator(schema).iter_errors(cfg),
                    key=lambda e: list(e.path))
    if errors:
        msg = "\n".join(f"  - {'/'.join(map(str, e.path)) or '<root>'}: {e.message}"
                        for e in errors)
        raise ConfigError(f"{path} failed schema validation:\n{msg}")
    return cfg


def entities_needing_approval(cfg: dict) -> list[dict]:
    """restricted entities from `discover`/`human` that have no approved_by yet."""
    out = []
    for e in cfg.get("entities", []):
        if (e.get("level") == "restricted"
                and e.get("source") in {"discovered", "human"}
                and not e.get("approved_by")):
            out.append(e)
    return out
