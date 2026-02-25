from __future__ import annotations

from dataclasses import dataclass

from server.config import AppConfig, load_config
from server.core.filesystem import ensure_runtime_dirs
from server.db.store import Store
from server.workers.engine import Engine


@dataclass
class RuntimeState:
    cfg: AppConfig
    store: Store
    engine: Engine


_STATE: RuntimeState | None = None


def initialize(config_path: str = "config.yaml") -> RuntimeState:
    global _STATE
    if _STATE is not None:
        return _STATE
    cfg = load_config(config_path)
    ensure_runtime_dirs(cfg)
    store = Store(cfg)
    store.init_db()
    engine = Engine(cfg, store)
    _STATE = RuntimeState(cfg=cfg, store=store, engine=engine)
    return _STATE


def get_state() -> RuntimeState:
    if _STATE is None:
        raise RuntimeError("Runtime not initialized")
    return _STATE
