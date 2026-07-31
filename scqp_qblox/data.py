from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from .config import public_snapshot


def json_default(value: Any):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    return str(value)


def create_run_dir(root: str | Path, experiment: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = Path(root).expanduser().resolve() / datetime.now().strftime("%Y-%m-%d") / f"{experiment}_{timestamp}"
    path.mkdir(parents=True, exist_ok=False)
    return path


def write_json(path: str | Path, data: Any) -> None:
    Path(path).write_text(json.dumps(data, indent=2, default=json_default), encoding="utf-8")


def save_run_metadata(
    run_dir: Path,
    *,
    config: dict[str, Any],
    parameters: dict[str, Any],
    status: dict[str, Any],
) -> None:
    write_json(run_dir / "hardware_config_snapshot.json", public_snapshot(config))
    write_json(run_dir / "parameters.json", parameters)
    write_json(run_dir / "instrument_status.json", status)


def save_frequency_sweep(
    run_dir: Path,
    *,
    frequency_hz: np.ndarray,
    i_values: np.ndarray,
    q_values: np.ndarray,
    prefix: str = "transmission",
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import xarray as xr

    amplitude = np.hypot(i_values, q_values)
    phase = np.unwrap(np.arctan2(q_values, i_values))
    dataset = xr.Dataset(
        data_vars={
            "I": ("probe_frequency_hz", i_values),
            "Q": ("probe_frequency_hz", q_values),
            "amplitude": ("probe_frequency_hz", amplitude),
            "phase_rad": ("probe_frequency_hz", phase),
        },
        coords={"probe_frequency_hz": frequency_hz},
        attrs={"calibration": "relative/un-calibrated; not absolute S21"},
    )
    dataset.to_netcdf(run_dir / f"{prefix}.nc", engine="h5netcdf")
    np.savetxt(
        run_dir / f"{prefix}.csv",
        np.column_stack([frequency_hz, i_values, q_values, amplitude, phase]),
        delimiter=",",
        header="probe_frequency_hz,I,Q,amplitude,phase_rad",
        comments="",
    )

    fig, axes = plt.subplots(2, 1, sharex=True, constrained_layout=True)
    axes[0].plot(frequency_hz / 1e9, amplitude)
    axes[0].set_ylabel("Relative amplitude")
    axes[1].plot(frequency_hz / 1e9, phase)
    axes[1].set_ylabel("Phase (rad)")
    axes[1].set_xlabel("Probe frequency (GHz)")
    for axis in axes:
        axis.grid(alpha=0.2)
    fig.savefig(run_dir / f"{prefix}.png", dpi=180)
    plt.close(fig)

