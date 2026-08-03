from __future__ import annotations

import time
from typing import Callable, TypeVar

T = TypeVar("T")


def call_with_retry(fn: Callable[[], T], attempts: int = 3, delay_seconds: float = 5.0) -> T:
    """Chama fn() de novo em caso de erro, com backoff linear entre tentativas.

    Cobre instabilidades transitorias de rede nas chamadas ao Garmin Connect e ao
    Gemini durante a execucao agendada, onde nao ha ninguem para simplesmente tentar de novo.
    """
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception:
            if attempt == attempts:
                raise
            time.sleep(delay_seconds * attempt)
    raise AssertionError("unreachable")
