from __future__ import annotations

import math
from typing import Any


class SequenceError(ValueError):
    pass


def _aligned_ns(value: int, name: str) -> int:
    value = int(value)
    if value < 4 or value % 4:
        raise SequenceError(f"{name} must be >= 4 ns and a multiple of 4 ns")
    return value


def _validate_amplitude(amplitude: float) -> float:
    amplitude = float(amplitude)
    if not 0 < amplitude <= 1:
        raise SequenceError("Waveform amplitude must be in (0, 1]")
    return amplitude


def gaussian(length_ns: int, amplitude: float) -> list[float]:
    length_ns = _aligned_ns(length_ns, "waveform length")
    amplitude = _validate_amplitude(amplitude)
    center = (length_ns - 1) / 2
    sigma = 0.12 * length_ns
    return [amplitude * math.exp(-0.5 * ((sample - center) / sigma) ** 2) for sample in range(length_ns)]


def block(length_ns: int, amplitude: float) -> list[float]:
    return [_validate_amplitude(amplitude)] * _aligned_ns(length_ns, "waveform length")


def qcm_scope_sequence(
    *, length_ns: int, amplitude: float, repetitions: int, period_ns: int
) -> dict[str, Any]:
    length_ns = _aligned_ns(length_ns, "waveform length")
    period_ns = _aligned_ns(period_ns, "period")
    wait_ns = period_ns - length_ns - 4
    if wait_ns < 4:
        raise SequenceError("period must be at least waveform length + 4 ns")
    if repetitions < 1:
        raise SequenceError("repetitions must be positive")
    return {
        "waveforms": {
            "pulse": {"data": gaussian(length_ns, amplitude), "index": 0},
            "zero": {"data": [0.0] * length_ns, "index": 1},
        },
        "weights": {},
        "acquisitions": {},
        "program": f"""
wait_sync 4
move {int(repetitions)},R0
scope_loop:
set_mrk 1
play 0,1,{length_ns}
set_mrk 0
upd_param 4
wait {wait_ns}
loop R0,@scope_loop
stop
""".strip(),
    }


def qcm_rf_scope_sequence(
    *, length_ns: int, amplitude: float, repetitions: int, period_ns: int
) -> dict[str, Any]:
    length_ns = _aligned_ns(length_ns, "waveform length")
    period_ns = _aligned_ns(period_ns, "period")
    wait_ns = period_ns - length_ns - 4
    if wait_ns < 4:
        raise SequenceError("period must be at least waveform length + 8 ns")
    if repetitions < 1:
        raise SequenceError("repetitions must be positive")
    return {
        "waveforms": {
            "i": {"data": gaussian(length_ns, amplitude), "index": 0},
            "q": {"data": [0.0] * length_ns, "index": 1},
        },
        "weights": {},
        "acquisitions": {},
        "program": f"""
wait_sync 4
move {int(repetitions)},R0
rf_loop:
set_mrk 1
play 0,1,{length_ns}
set_mrk 0
upd_param 4
wait {wait_ns}
loop R0,@rf_loop
stop
""".strip(),
    }


def qrm_rf_acquisition_sequence(
    *, pulse_length_ns: int, acquisition_length_ns: int, amplitude: float, averages: int, period_ns: int
) -> dict[str, Any]:
    pulse_length_ns = _aligned_ns(pulse_length_ns, "pulse length")
    acquisition_length_ns = _aligned_ns(acquisition_length_ns, "acquisition length")
    period_ns = _aligned_ns(period_ns, "period")
    if acquisition_length_ns > 16380:
        raise SequenceError("scope acquisition length cannot exceed 16380 ns in this example")
    used_ns = 8 + acquisition_length_ns
    wait_ns = period_ns - used_ns
    if wait_ns < 4:
        raise SequenceError("period is too short for acquisition plus 4 ns idle")
    if averages < 1:
        raise SequenceError("averages must be positive")
    return {
        "waveforms": {
            "i": {"data": block(pulse_length_ns, amplitude), "index": 0},
            "q": {"data": [0.0] * pulse_length_ns, "index": 1},
        },
        "weights": {},
        "acquisitions": {"measurement": {"num_bins": 1, "index": 0}},
        "program": f"""
wait_sync 4
move {int(averages)},R0
acq_loop:
set_mrk 3
play 0,1,4
acquire 0,0,{acquisition_length_ns}
set_mrk 0
upd_param 4
wait {wait_ns}
loop R0,@acq_loop
set_mrk 0
upd_param 4
stop
""".strip(),
    }


def parametric_pair_sequences(
    *,
    flux_length_ns: int,
    flux_amplitude: float,
    probe_length_ns: int,
    probe_amplitude: float,
    pump_lead_ns: int,
    acquisition_length_ns: int,
    averages: int,
    period_ns: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    flux_length_ns = _aligned_ns(flux_length_ns, "flux length")
    probe_length_ns = _aligned_ns(probe_length_ns, "probe length")
    pump_lead_ns = _aligned_ns(pump_lead_ns, "pump lead")
    acquisition_length_ns = _aligned_ns(acquisition_length_ns, "acquisition length")
    period_ns = _aligned_ns(period_ns, "period")
    if pump_lead_ns + acquisition_length_ns > flux_length_ns:
        raise SequenceError("Flux pulse must cover pump lead plus acquisition")
    if period_ns - pump_lead_ns - acquisition_length_ns - 8 < 4:
        raise SequenceError("period is too short for the synchronized probe acquisition")
    idle_ns = period_ns - flux_length_ns
    if idle_ns < 4:
        raise SequenceError("period must be longer than the flux pulse")

    qcm = {
        "waveforms": {
            "pump": {"data": block(flux_length_ns, flux_amplitude), "index": 0},
            "zero": {"data": [0.0] * flux_length_ns, "index": 1},
        },
        "weights": {},
        "acquisitions": {},
        "program": f"""
wait_sync 4
move {int(averages)},R0
pump_loop:
play 0,1,{flux_length_ns}
wait {idle_ns}
loop R0,@pump_loop
stop
""".strip(),
    }
    qrm = {
        "waveforms": {
            "probe_i": {"data": block(probe_length_ns, probe_amplitude), "index": 0},
            "probe_q": {"data": [0.0] * probe_length_ns, "index": 1},
        },
        "weights": {},
        "acquisitions": {"measurement": {"num_bins": 1, "index": 0}},
        "program": f"""
wait_sync 4
move {int(averages)},R0
probe_loop:
wait {pump_lead_ns}
set_mrk 3
play 0,1,4
acquire 0,0,{acquisition_length_ns}
set_mrk 0
upd_param 4
wait {period_ns - pump_lead_ns - acquisition_length_ns - 8}
loop R0,@probe_loop
stop
""".strip(),
    }
    return qcm, qrm
