from __future__ import annotations

import numpy as np


def synthetic_transmission(
    frequency_hz: np.ndarray,
    *,
    resonance_hz: float,
    linewidth_hz: float,
    depth: float = 0.35,
    cable_delay_s: float = 2.0e-9,
    noise_std: float = 0.002,
    seed: int = 12345,
) -> tuple[np.ndarray, np.ndarray]:
    """Return deterministic, noisy complex S21 data for an offline pipeline test."""
    frequencies = np.asarray(frequency_hz, dtype=float)
    if frequencies.ndim != 1 or frequencies.size < 2:
        raise ValueError("frequency_hz must be a one-dimensional array with at least two points")
    if linewidth_hz <= 0:
        raise ValueError("linewidth_hz must be positive")
    if not 0 < depth < 1:
        raise ValueError("depth must be between 0 and 1")
    if noise_std < 0:
        raise ValueError("noise_std must be non-negative")

    detuning = 2.0 * (frequencies - float(resonance_hz)) / float(linewidth_hz)
    notch = 1.0 - float(depth) / (1.0 + 1j * detuning)
    phase = np.exp(-2j * np.pi * (frequencies - frequencies[0]) * float(cable_delay_s))
    response = notch * phase

    rng = np.random.default_rng(seed)
    noise = noise_std * (
        rng.normal(size=frequencies.size) + 1j * rng.normal(size=frequencies.size)
    )
    response += noise
    return response.real, response.imag


def synthetic_dispersive_power_sweep(
    frequency_hz: np.ndarray,
    readout_power_dbm: np.ndarray,
    *,
    resonator_hz: float,
    chi_hz: float,
    linewidth_hz: float,
    critical_power_dbm: float,
    depth: float = 0.45,
    cable_delay_s: float = 2.0e-9,
    noise_std: float = 0.002,
    seed: int = 12345,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Simulate complex resonator S21 versus power for qubit states |g> and |e>.

    The returned I/Q arrays have shape ``(2, power, frequency)`` with state order
    ``(|g>, |e>)``. At low power the resonances are separated by ``2 * chi_hz``.
    The effective dispersive shift decreases above ``critical_power_dbm`` to mimic
    the breakdown of the low-photon dispersive approximation.
    """
    frequencies = np.asarray(frequency_hz, dtype=float)
    powers = np.asarray(readout_power_dbm, dtype=float)
    if frequencies.ndim != 1 or frequencies.size < 2:
        raise ValueError("frequency_hz must be a one-dimensional array with at least two points")
    if powers.ndim != 1 or powers.size < 2:
        raise ValueError("readout_power_dbm must be a one-dimensional array with at least two points")
    if chi_hz <= 0:
        raise ValueError("chi_hz must be positive")
    if linewidth_hz <= 0:
        raise ValueError("linewidth_hz must be positive")
    if not 0 < depth < 1:
        raise ValueError("depth must be between 0 and 1")
    if noise_std < 0:
        raise ValueError("noise_std must be non-negative")

    photon_ratio = 10.0 ** ((powers - float(critical_power_dbm)) / 10.0)
    effective_chi_hz = float(chi_hz) / np.sqrt(1.0 + photon_ratio)
    power_saturation = photon_ratio / (1.0 + photon_ratio)
    effective_linewidth_hz = float(linewidth_hz) * (1.0 + 0.35 * power_saturation)
    effective_depth = float(depth) * (1.0 - 0.30 * power_saturation)

    response = np.empty((2, powers.size, frequencies.size), dtype=complex)
    phase = np.exp(-2j * np.pi * (frequencies - frequencies[0]) * float(cable_delay_s))
    rng = np.random.default_rng(seed)
    for state_index, state_sign in enumerate((-1.0, 1.0)):
        state_resonance_hz = float(resonator_hz) + state_sign * effective_chi_hz
        detuning = 2.0 * (
            frequencies[np.newaxis, :] - state_resonance_hz[:, np.newaxis]
        ) / effective_linewidth_hz[:, np.newaxis]
        notch = 1.0 - effective_depth[:, np.newaxis] / (1.0 + 1j * detuning)
        noise = noise_std * (
            rng.normal(size=notch.shape) + 1j * rng.normal(size=notch.shape)
        )
        response[state_index] = notch * phase[np.newaxis, :] + noise

    return response.real, response.imag, effective_chi_hz
