from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Iterator


class HardwareError(RuntimeError):
    """Raised for connection, inventory, or instrument-state failures."""


def connect_cluster(config: dict[str, Any], *, reset: bool = False):
    """Connect without resetting unless the caller explicitly requests it."""
    try:
        from qblox_instruments import Cluster
    except ImportError as exc:
        raise HardwareError(
            "qblox-instruments is not installed. Create the project venv and run `python -m pip install -e .`."
        ) from exc

    if reset and not config["safety"].get("allow_cluster_reset", False):
        raise HardwareError("Cluster reset is blocked by safety.allow_cluster_reset=false")

    cluster_cfg = config["cluster"]
    try:
        cluster = Cluster(name=cluster_cfg["name"], identifier=cluster_cfg["address"])
    except Exception as exc:
        raise HardwareError(f"Could not connect to Cluster at {cluster_cfg['address']!r}: {exc}") from exc

    if reset:
        try:
            cluster.reset()
        except Exception:
            cluster.close()
            raise
    return cluster


def connected_modules(cluster) -> dict[int, Any]:
    try:
        return dict(cluster.get_connected_modules())
    except Exception as exc:
        raise HardwareError(f"Could not read connected module inventory: {exc}") from exc


def inventory(cluster) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for slot, module in sorted(connected_modules(cluster).items()):
        module_type = getattr(module, "module_type", None)
        if callable(module_type):
            module_type = module_type()
        rows.append(
            {
                "slot": int(slot),
                "module_type": str(module_type),
                "is_qcm_type": bool(getattr(module, "is_qcm_type", False)),
                "is_qrm_type": bool(getattr(module, "is_qrm_type", False)),
                "is_rf_type": bool(getattr(module, "is_rf_type", False)),
            }
        )
    return rows


def module_for(cluster, config: dict[str, Any], logical_name: str):
    module_cfg = config["modules"][logical_name]
    slot = int(module_cfg["slot"])
    modules = connected_modules(cluster)
    if slot not in modules:
        raise HardwareError(f"Expected {logical_name} in slot {slot}, but the slot is empty")
    module = modules[slot]

    is_qcm = bool(getattr(module, "is_qcm_type", False))
    is_qrm = bool(getattr(module, "is_qrm_type", False))
    is_rf = bool(getattr(module, "is_rf_type", False))
    expected_flags = {
        "qcm": (True, False, False),
        "qcm_rf": (True, False, True),
        "qrm_rf": (False, True, True),
    }[logical_name]
    actual_flags = (is_qcm, is_qrm, is_rf)
    if actual_flags != expected_flags:
        raise HardwareError(
            f"Slot {slot} does not match {module_cfg['expected_type']}: "
            f"is_qcm={is_qcm}, is_qrm={is_qrm}, is_rf={is_rf}"
        )
    return module


def sequencer(module, index: int):
    try:
        return getattr(module, f"sequencer{int(index)}")
    except AttributeError as exc:
        raise HardwareError(f"Module has no sequencer {index}") from exc


def call_if_present(obj: Any, name: str, *args: Any) -> bool:
    function = getattr(obj, name, None)
    if function is None:
        return False
    function(*args)
    return True


def check_sequencer_status(module, index: int, *, timeout_minutes: float = 1.0) -> str:
    seq = sequencer(module, index)
    try:
        status = seq.get_sequencer_status(timeout=timeout_minutes)
    except TypeError:
        status = module.get_sequencer_status(index, timeout=timeout_minutes)
    text = str(status)
    upper = text.upper()
    if "ERROR" in upper and "ERROR FLAGS: NONE" not in upper:
        raise HardwareError(f"Sequencer {index} reported an error: {text}")
    return text


def ramp_qcm_offset(
    qcm,
    output: int,
    target_v: float,
    *,
    step_v: float,
    delay_s: float,
) -> None:
    """Ramp a QCM static offset instead of applying an abrupt flux jump."""
    parameter = getattr(qcm, f"out{int(output)}_offset")
    current = float(parameter())
    target = float(target_v)
    step = abs(float(step_v))
    if step <= 0:
        raise HardwareError("Flux ramp step must be positive")
    while abs(target - current) > step:
        current += step if target > current else -step
        parameter(current)
        if delay_s > 0:
            time.sleep(delay_s)
    parameter(target)


def safe_shutdown(cluster, config: dict[str, Any], *, restore_flux_idle: bool) -> list[str]:
    """Best-effort shutdown; returns warnings rather than masking the original error."""
    warnings: list[str] = []
    try:
        cluster.stop_sequencer()
    except Exception as exc:
        warnings.append(f"stop_sequencer failed: {exc}")

    try:
        modules = connected_modules(cluster)
    except Exception as exc:
        return warnings + [f"inventory during shutdown failed: {exc}"]

    for slot, module in modules.items():
        try:
            if bool(getattr(module, "is_rf_type", False)):
                if bool(getattr(module, "is_qcm_type", False)):
                    call_if_present(module, "out0_lo_en", False)
                    call_if_present(module, "out1_lo_en", False)
                elif bool(getattr(module, "is_qrm_type", False)):
                    call_if_present(module, "out0_in0_lo_en", False)
                for index in range(6):
                    seq = getattr(module, f"sequencer{index}", None)
                    if seq is not None:
                        call_if_present(seq, "marker_ovr_en", True)
                        call_if_present(seq, "marker_ovr_value", 0)
            call_if_present(module, "disconnect_outputs")
            if bool(getattr(module, "is_qrm_type", False)):
                call_if_present(module, "disconnect_inputs")
        except Exception as exc:
            warnings.append(f"slot {slot} RF/channel cleanup failed: {exc}")

    if restore_flux_idle:
        try:
            qcm = module_for(cluster, config, "qcm")
            qcm_cfg = config["modules"]["qcm"]
            flux = config["flux"]
            for side in ("left", "right"):
                ramp_qcm_offset(
                    qcm,
                    int(qcm_cfg[f"{side}_flux_output"]),
                    float(flux[f"{side}_idle_voltage_v"]),
                    step_v=float(flux["ramp_step_v"]),
                    delay_s=float(flux["ramp_delay_s"]),
                )
        except Exception as exc:
            warnings.append(f"flux idle restore failed: {exc}")
    return warnings


@contextmanager
def cluster_session(
    config: dict[str, Any],
    *,
    reset: bool = False,
    output_capable: bool = False,
    restore_flux_idle: bool = False,
) -> Iterator[Any]:
    cluster = connect_cluster(config, reset=reset)
    try:
        yield cluster
    finally:
        if output_capable:
            for warning in safe_shutdown(cluster, config, restore_flux_idle=restore_flux_idle):
                print(f"WARNING during safe shutdown: {warning}")
        cluster.close()
