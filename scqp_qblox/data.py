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


def save_dispersive_power_sweep(
    run_dir: Path,
    *,
    frequency_hz: np.ndarray,
    readout_power_dbm: np.ndarray,
    i_values: np.ndarray,
    q_values: np.ndarray,
    effective_chi_hz: np.ndarray,
    resonator_hz: float,
    prefix: str = "dummy_dispersive_power",
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import xarray as xr

    states = np.array(["g", "e"])
    amplitude = np.hypot(i_values, q_values)
    phase = np.unwrap(np.arctan2(q_values, i_values), axis=-1)
    expected_shape = (2, len(readout_power_dbm), len(frequency_hz))
    if i_values.shape != expected_shape or q_values.shape != expected_shape:
        raise ValueError(f"I/Q arrays must have shape {expected_shape}")
    if effective_chi_hz.shape != (len(readout_power_dbm),):
        raise ValueError("effective_chi_hz must have one value per readout power")

    dataset = xr.Dataset(
        data_vars={
            "I": (("qubit_state", "readout_power_dbm", "probe_frequency_hz"), i_values),
            "Q": (("qubit_state", "readout_power_dbm", "probe_frequency_hz"), q_values),
            "amplitude": (
                ("qubit_state", "readout_power_dbm", "probe_frequency_hz"),
                amplitude,
            ),
            "phase_rad": (
                ("qubit_state", "readout_power_dbm", "probe_frequency_hz"),
                phase,
            ),
            "effective_chi_hz": (("readout_power_dbm",), effective_chi_hz),
            "resonance_separation_hz": (("readout_power_dbm",), 2.0 * effective_chi_hz),
        },
        coords={
            "qubit_state": states,
            "readout_power_dbm": readout_power_dbm,
            "probe_frequency_hz": frequency_hz,
        },
        attrs={
            "model": "synthetic dispersive resonator power sweep",
            "calibration": "simulated relative S21; not hardware data",
            "bare_resonator_hz": float(resonator_hz),
        },
    )
    dataset.to_netcdf(run_dir / f"{prefix}.nc", engine="h5netcdf")

    state_column = np.repeat(states, len(readout_power_dbm) * len(frequency_hz))
    power_column = np.tile(
        np.repeat(readout_power_dbm, len(frequency_hz)), len(states)
    )
    frequency_column = np.tile(frequency_hz, len(states) * len(readout_power_dbm))
    np.savetxt(
        run_dir / f"{prefix}.csv",
        np.column_stack(
            [
                state_column,
                power_column,
                frequency_column,
                i_values.reshape(-1),
                q_values.reshape(-1),
                amplitude.reshape(-1),
                phase.reshape(-1),
            ]
        ),
        fmt="%s",
        delimiter=",",
        header="qubit_state,readout_power_dbm,probe_frequency_hz,I,Q,amplitude,phase_rad",
        comments="",
    )

    frequency_mhz = (frequency_hz - float(resonator_hz)) / 1e6
    amplitude_db = 20.0 * np.log10(np.maximum(amplitude, np.finfo(float).tiny))
    fig, axes = plt.subplots(2, 2, figsize=(11, 8), constrained_layout=True)
    for state_index, (state, sign, axis) in enumerate(
        zip(states, (-1.0, 1.0), axes[0], strict=True)
    ):
        mesh = axis.pcolormesh(
            frequency_mhz,
            readout_power_dbm,
            amplitude_db[state_index],
            shading="auto",
            cmap="viridis",
        )
        track_mhz = sign * effective_chi_hz / 1e6
        axis.plot(track_mhz, readout_power_dbm, "w--", linewidth=1.4, label="model resonance")
        axis.set(
            title=f"Qubit |{state}>: resonator |S21|",
            xlabel="Detuning from bare resonator (MHz)",
            ylabel="Readout power (dBm)",
        )
        axis.legend(loc="lower right")
        fig.colorbar(mesh, ax=axis, label="Relative amplitude (dB)")

    low_power_index = 0
    axes[1, 0].plot(
        frequency_mhz,
        amplitude_db[0, low_power_index],
        label="qubit |g>",
    )
    axes[1, 0].plot(
        frequency_mhz,
        amplitude_db[1, low_power_index],
        label="qubit |e>",
    )
    axes[1, 0].set(
        title=f"Low-power line cut ({readout_power_dbm[low_power_index]:g} dBm)",
        xlabel="Detuning from bare resonator (MHz)",
        ylabel="Relative amplitude (dB)",
    )
    axes[1, 0].grid(alpha=0.2)
    axes[1, 0].legend()

    axes[1, 1].plot(readout_power_dbm, 2.0 * effective_chi_hz / 1e6, marker="o", ms=3)
    axes[1, 1].set(
        title="Dispersive resonance separation",
        xlabel="Readout power (dBm)",
        ylabel="2 chi effective (MHz)",
    )
    axes[1, 1].grid(alpha=0.2)
    fig.suptitle("Dummy resonator power sweep with qubit-state dispersive shift")
    fig.savefig(run_dir / f"{prefix}.png", dpi=180)
    plt.close(fig)

