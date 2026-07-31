from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scqp_qblox.config import load_config


def parser(description: str, *, output: bool = True) -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=description)
    result.add_argument("--config", default="hardware_config.json", help="Path to local hardware JSON")
    result.add_argument("--data-root", default="data", help="Root data directory")
    if output:
        result.add_argument(
            "--execute",
            action="store_true",
            help="Actually connect and enable outputs; without this flag the command is dry-run only",
        )
        result.add_argument(
            "--reset",
            action="store_true",
            help="Reset the entire Cluster first; also requires safety.allow_cluster_reset=true",
        )
    return result


def load(args: argparse.Namespace) -> dict[str, Any]:
    return load_config(Path(args.config))


def print_plan(title: str, plan: dict[str, Any], *, execute: bool) -> None:
    print(title)
    print(json.dumps(plan, indent=2, ensure_ascii=False))
    if not execute:
        print("\nDRY-RUN ONLY: no Cluster connection was opened and no output was enabled.")

