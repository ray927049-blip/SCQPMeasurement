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
