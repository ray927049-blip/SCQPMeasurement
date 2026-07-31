from __future__ import annotations

import numpy as np
import pytest

from scqp_qblox.data import save_frequency_sweep
from scqp_qblox.dummy import synthetic_dispersive_power_sweep, synthetic_transmission


def test_dummy_transmission_is_reproducible_and_has_a_resonance_dip():
    frequencies = np.linspace(5.0e9, 7.0e9, 201)
    kwargs = {
        "resonance_hz": 6.0e9,
        "linewidth_hz": 100.0e6,
        "noise_std": 0.0,
        "seed": 7,
    }
    i_first, q_first = synthetic_transmission(frequencies, **kwargs)
    i_second, q_second = synthetic_transmission(frequencies, **kwargs)

    assert i_first.shape == frequencies.shape
    assert q_first.shape == frequencies.shape
    np.testing.assert_array_equal(i_first, i_second)
    np.testing.assert_array_equal(q_first, q_second)
    amplitude = np.hypot(i_first, q_first)
    assert amplitude[100] < amplitude[0]
    assert amplitude[100] < amplitude[-1]


def test_dummy_transmission_rejects_invalid_linewidth():
    with pytest.raises(ValueError, match="linewidth"):
        synthetic_transmission(
            np.array([5.0e9, 6.0e9]),
            resonance_hz=5.5e9,
            linewidth_hz=0,
        )


def test_dummy_data_pipeline_writes_all_output_formats(tmp_path):
    frequencies = np.linspace(5.0e9, 7.0e9, 11)
    i_values, q_values = synthetic_transmission(
        frequencies,
        resonance_hz=6.0e9,
        linewidth_hz=100.0e6,
        noise_std=0.0,
    )

    save_frequency_sweep(
        tmp_path,
        frequency_hz=frequencies,
        i_values=i_values,
        q_values=q_values,
        prefix="dummy",
    )

    assert (tmp_path / "dummy.csv").is_file()
    assert (tmp_path / "dummy.nc").is_file()
    assert (tmp_path / "dummy.png").is_file()


def test_dispersive_power_sweep_resolves_two_chi_and_power_collapse():
    frequencies = np.linspace(5.990e9, 6.010e9, 2001)
    powers = np.array([-70.0, -20.0])
    i_values, q_values, effective_chi = synthetic_dispersive_power_sweep(
        frequencies,
        powers,
        resonator_hz=6.0e9,
        chi_hz=2.0e6,
        linewidth_hz=1.0e6,
        critical_power_dbm=-35.0,
        noise_std=0.0,
    )

    assert i_values.shape == (2, 2, 2001)
    assert q_values.shape == (2, 2, 2001)
    low_power_dips = [
        frequencies[np.argmin(np.hypot(i_values[state, 0], q_values[state, 0]))]
        for state in range(2)
    ]
    assert low_power_dips[1] - low_power_dips[0] == pytest.approx(4.0e6, abs=20.0e3)
    assert effective_chi[1] < effective_chi[0]
