"""共通の入出力ヘルパー。"""

from __future__ import annotations


def log(message: str) -> None:
    print(message, flush=True)


def die(message: str) -> None:
    log(f"!! {message}")
    raise SystemExit(1)


def ask(prompt_text: str) -> str | None:
    """対話入力。EOF と Ctrl+C は None を返す。"""
    try:
        return input(prompt_text).strip()
    except (EOFError, KeyboardInterrupt):
        log("")
        return None
