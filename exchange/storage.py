"""Сохранение состояния обменного пункта в JSON-файл."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .core import ExchangeOffice


def load(path: str | os.PathLike) -> ExchangeOffice:
    with open(path, encoding="utf-8") as f:
        return ExchangeOffice.from_dict(json.load(f))


def save(office: ExchangeOffice, path: str | os.PathLike) -> None:
    """Атомарно записать состояние: сначала во временный файл, затем переименовать."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(office.to_dict(), f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise
