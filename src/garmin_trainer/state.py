from __future__ import annotations

import json
from typing import Any

from .config import PROJECT_ROOT, load_profile

STATE_PATH = PROJECT_ROOT / "data" / "state.json"


def load_state() -> dict[str, Any]:
    """Estado da execucao agendada (ultima atividade analisada, ultimo relatorio enviado...).

    Fica separado do athlete_profile.yaml (versionado no git) porque muda a cada execucao.
    Na primeira vez, migra o `history` que antes ficava dentro do perfil.
    """
    if STATE_PATH.exists():
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    history = load_profile().get("history") or {}
    return {"last_synced_activity_id": history.get("last_synced_activity_id")}


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    tmp.replace(STATE_PATH)
