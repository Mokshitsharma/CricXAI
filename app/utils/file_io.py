"""File helpers for CricXAI data pipeline scripts."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from typing import Any

import yaml

PathLike = str | Path


def ensure_dir(path: PathLike) -> Path:
    """Create a directory if needed and return it as a Path."""
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def read_json(path: PathLike) -> Any:
    """Read JSON from disk."""
    with Path(path).open("r", encoding="utf-8") as file:
        return json.load(file)


def write_json(data: Any, path: PathLike, indent: int = 2) -> Path:
    """Write JSON data to disk."""
    output_path = Path(path)
    ensure_dir(output_path.parent)
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=indent, ensure_ascii=False)
    return output_path


def read_yaml(path: PathLike) -> Any:
    """Read YAML from disk."""
    with Path(path).open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def write_yaml(data: Any, path: PathLike) -> Path:
    """Write YAML data to disk."""
    output_path = Path(path)
    ensure_dir(output_path.parent)
    with output_path.open("w", encoding="utf-8") as file:
        yaml.safe_dump(data, file, sort_keys=False)
    return output_path


def list_files(directory: PathLike, pattern: str = "*") -> list[Path]:
    """Return files matching a glob pattern under a directory."""
    root = Path(directory)
    if not root.exists():
        return []
    return sorted(path for path in root.glob(pattern) if path.is_file())


def read_frame(stem: PathLike):
    """Read ``<stem>.parquet`` if it exists, else ``<stem>.csv``.

    Parquet is ~8x smaller and ~10x faster to load for the big processed
    tables; the pipeline writes both so CSV-based tooling keeps working.
    ``stem`` is the path without extension.
    """
    import pandas as pd

    stem = Path(stem)
    parquet = stem.with_suffix(".parquet")
    if parquet.exists():
        return pd.read_parquet(parquet)
    return pd.read_csv(stem.with_suffix(".csv"))


def write_frame(df, stem: PathLike) -> Path:
    """Write a DataFrame as both ``<stem>.csv`` and ``<stem>.parquet``.

    CSV stays the canonical, inspectable artifact; parquet is a load-time
    optimisation and its failure is non-fatal. Returns the CSV path.
    """
    stem = Path(stem)
    ensure_dir(stem.parent)
    csv_path = stem.with_suffix(".csv")
    df.to_csv(csv_path, index=False)
    with contextlib.suppress(Exception):  # parquet is an optional optimisation
        df.to_parquet(stem.with_suffix(".parquet"), index=False)
    return csv_path
