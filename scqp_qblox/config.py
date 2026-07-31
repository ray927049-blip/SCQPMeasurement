from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    """Raised before hardware access when the JSON is incomplete or unsafe."""


def load_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path).expanduser().resolve()
    if not config_path.is_file():
        raise ConfigError(f"Config file not found: {config_path}")
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in {config_path}: {exc}") from exc
    validate_config(config)
    config["_config_path"] = str(config_path)
    return config


def require(mapping: dict[str, Any], key: str, where: str) -> Any:
    if key not in mapping:
        raise ConfigError(f"Missing {where}.{key}")
    return mapping[key]


def validate_config(config: dict[str, Any]) -> None:
    if config.get("schema_version") != 1:
        raise ConfigError("schema_version must be 1")

    cluster = require(config, "cluster", "root")
    address = require(cluster, "address", "cluster")
    if not isinstance(address, str) or not address.strip():
        raise ConfigError("cluster.address must be a non-empty hostname/IP")

    modules = require(config, "modules", "root")
    expected = {
        "qcm": "QCM",
        "qcm_rf": "QCM-RF II",
        "qrm_rf": "QRM-RF",
    }
    for name, module_type in expected.items():
        module = require(modules, name, "modules")
        slot = require(module, "slot", f"modules.{name}")
        if not isinstance(slot, int) or not 1 <= slot <= 20:
            raise ConfigError(f"modules.{name}.slot must be an integer in [1, 20]")
        if module.get("expected_type") != module_type:
            raise ConfigError(f"modules.{name}.expected_type must be {module_type!r}")

    sample = require(config, "sample", "root")
    if sample.get("has_resonator") is not False:
        raise ConfigError("This project expects sample.has_resonator=false")
    if sample.get("microwave_topology") not in {"transmission", "reflection"}:
        raise ConfigError("sample.microwave_topology must be transmission or reflection")

    safety = require(config, "safety", "root")
    if float(safety.get("max_abs_static_flux_voltage_v", 0)) <= 0:
        raise ConfigError("safety.max_abs_static_flux_voltage_v must be positive")
    if not 0 < float(safety.get("max_duty_cycle", 0)) <= 1:
        raise ConfigError("safety.max_duty_cycle must be in (0, 1]")

    flux = require(config, "flux", "root")
    absolute_limit = float(safety["max_abs_static_flux_voltage_v"])
    for side in ("left", "right"):
        low = float(require(flux, f"{side}_min_voltage_v", "flux"))
        high = float(require(flux, f"{side}_max_voltage_v", "flux"))
        idle = float(require(flux, f"{side}_idle_voltage_v", "flux"))
        if not -absolute_limit <= low <= idle <= high <= absolute_limit:
            raise ConfigError(
                f"flux.{side} limits/idle must be ordered and within +/-{absolute_limit} V"
            )


def require_verified_sample_connectors(config: dict[str, Any]) -> None:
    sample = config["sample"]
    unknown = [
        key
        for key in ("microwave_input_connector", "microwave_output_connector")
        if sample.get(key) in {None, "", "UNVERIFIED"}
    ]
    if unknown:
        raise ConfigError(
            "Real sample output is blocked until these fields are verified: " + ", ".join(unknown)
        )


def assert_execute(execute: bool) -> None:
    if not execute:
        raise ConfigError("Hardware output requires the explicit --execute flag")


def check_rf_frequency(config: dict[str, Any], frequency_hz: float) -> None:
    safety = config["safety"]
    if not float(safety["min_rf_frequency_hz"]) <= frequency_hz <= float(
        safety["max_rf_frequency_hz"]
    ):
        raise ConfigError(f"RF frequency {frequency_hz:g} Hz is outside the configured safe RF band")


def check_parametric_frequency(config: dict[str, Any], frequency_hz: float) -> None:
    maximum = float(config["safety"]["max_qcm_parametric_frequency_hz"])
    if not 0 <= frequency_hz <= maximum:
        raise ConfigError(
            f"QCM cannot generate requested parametric frequency {frequency_hz:g} Hz; "
            f"configured maximum is {maximum:g} Hz. The 400 MHz-2 GHz gap needs an external source."
        )


def check_duty_cycle(config: dict[str, Any], *, active_ns: int, period_ns: int) -> None:
    duty_cycle = float(active_ns) / float(period_ns)
    maximum = float(config["safety"]["max_duty_cycle"])
    if duty_cycle > maximum:
        raise ConfigError(f"Duty cycle {duty_cycle:.3f} exceeds configured maximum {maximum:.3f}")


def public_snapshot(config: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in config.items() if not key.startswith("_")}
