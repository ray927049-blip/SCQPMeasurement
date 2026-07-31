from __future__ import annotations

from typing import Any

import numpy as np

from .acquisition import configure_qrm_rf, integrated_iq, run_and_fetch_qrm_rf
from .config import check_rf_frequency
from .hardware import module_for


def transmission_sweep(
    cluster,
    config: dict[str, Any],
    *,
    frequencies_hz: np.ndarray,
    sequence_dict: dict[str, Any],
    acquisition_length_ns: int,
    save_scope_first_point: bool = False,
) -> tuple[np.ndarray, np.ndarray, list[str], dict[str, Any] | None]:
    qrm_rf = module_for(cluster, config, "qrm_rf")
    module_cfg = config["modules"]["qrm_rf"]
    index = int(module_cfg["sequencer"])
    nco_hz = float(module_cfg["nco_frequency_hz"])
    first_frequency = float(frequencies_hz[0])
    check_rf_frequency(config, first_frequency)
    configure_qrm_rf(
        qrm_rf,
        module_cfg,
        sequence_dict,
        lo_frequency_hz=first_frequency - nco_hz,
        acquisition_length_ns=acquisition_length_ns,
    )

    i_values = np.empty(len(frequencies_hz), dtype=float)
    q_values = np.empty(len(frequencies_hz), dtype=float)
    statuses: list[str] = []
    first_acquisition: dict[str, Any] | None = None
    for point, frequency_hz in enumerate(frequencies_hz):
        frequency_hz = float(frequency_hz)
        check_rf_frequency(config, frequency_hz)
        lo_hz = frequency_hz - nco_hz
        check_rf_frequency(config, lo_hz)
        qrm_rf.out0_in0_lo_freq(lo_hz)
        acquisitions, status = run_and_fetch_qrm_rf(
            qrm_rf,
            index=index,
            timeout_minutes=float(config["defaults"]["timeout_minutes"]),
            save_scope=save_scope_first_point and point == 0,
        )
        value = integrated_iq(acquisitions, integration_length_ns=acquisition_length_ns)
        i_values[point] = value.real
        q_values[point] = value.imag
        statuses.append(status)
        if point == 0 and save_scope_first_point:
            first_acquisition = acquisitions
    return i_values, q_values, statuses, first_acquisition

