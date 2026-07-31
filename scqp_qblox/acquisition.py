from __future__ import annotations

from typing import Any

import numpy as np

from .hardware import call_if_present, check_sequencer_status, sequencer


def configure_qcm_scope(qcm, module_config: dict[str, Any], sequence_dict: dict[str, Any], *, output: int) -> None:
    index = int(module_config["parametric_sequencer"])
    seq = sequencer(qcm, index)
    qcm.disconnect_outputs()
    seq.sequence(sequence_dict)
    seq.sync_en(True)
    seq.mod_en_awg(False)
    call_if_present(seq, "marker_ovr_en", False)
    getattr(seq, f"connect_out{int(output)}")("I")


def configure_qcm_rf_scope(qcm_rf, module_config: dict[str, Any], sequence_dict: dict[str, Any]) -> None:
    index = int(module_config["sequencer"])
    output = int(module_config["output"])
    seq = sequencer(qcm_rf, index)
    qcm_rf.disconnect_outputs()
    seq.sequence(sequence_dict)
    seq.sync_en(True)
    call_if_present(seq, "marker_ovr_en", False)
    getattr(seq, f"connect_out{output}")("IQ")
    seq.mod_en_awg(True)
    seq.nco_freq(float(module_config["nco_frequency_hz"]))
    getattr(qcm_rf, f"out{output}_att")(int(module_config["output_attenuation_db"]))
    getattr(qcm_rf, f"out{output}_lo_freq")(float(module_config["lo_frequency_hz"]))
    getattr(qcm_rf, f"out{output}_lo_en")(True)


def configure_qrm_rf(
    qrm_rf,
    module_config: dict[str, Any],
    sequence_dict: dict[str, Any],
    *,
    lo_frequency_hz: float,
    acquisition_length_ns: int,
) -> None:
    index = int(module_config["sequencer"])
    seq = sequencer(qrm_rf, index)
    qrm_rf.disconnect_outputs()
    qrm_rf.disconnect_inputs()
    seq.sequence(sequence_dict)
    seq.sync_en(True)
    call_if_present(seq, "marker_ovr_en", False)
    seq.connect_out0("IQ")
    seq.connect_acq("in0")
    seq.mod_en_awg(True)
    seq.demod_en_acq(True)
    call_if_present(seq, "nco_prop_delay_comp_en", True)
    seq.nco_freq(float(module_config["nco_frequency_hz"]))
    seq.integration_length_acq(int(acquisition_length_ns))

    qrm_rf.scope_acq_sequencer_select(index)
    qrm_rf.scope_acq_trigger_mode_path0("sequencer")
    qrm_rf.scope_acq_trigger_mode_path1("sequencer")
    call_if_present(qrm_rf, "scope_acq_avg_mode_en_path0", False)
    call_if_present(qrm_rf, "scope_acq_avg_mode_en_path1", False)

    call_if_present(qrm_rf, "out0_att", int(module_config["output_attenuation_db"]))
    call_if_present(qrm_rf, "in0_att", int(module_config["input_attenuation_db"]))
    qrm_rf.out0_in0_lo_freq(float(lo_frequency_hz))
    qrm_rf.out0_in0_lo_en(True)


def clear_acquisitions(module, index: int) -> None:
    seq = sequencer(module, index)
    try:
        seq.delete_acquisition_data(all=True)
    except TypeError:
        seq.delete_acquisition_data("measurement")


def run_and_fetch_qrm_rf(
    qrm_rf,
    *,
    index: int,
    timeout_minutes: float,
    save_scope: bool,
) -> tuple[dict[str, Any], str]:
    seq = sequencer(qrm_rf, index)
    clear_acquisitions(qrm_rf, index)
    qrm_rf.arm_sequencer(index)
    qrm_rf.start_sequencer(index)
    seq.get_acquisition_status(timeout=float(timeout_minutes))
    if save_scope:
        seq.store_scope_acquisition("measurement")
    try:
        acquisitions = seq.get_acquisitions(as_numpy=True)
    except TypeError:
        acquisitions = seq.get_acquisitions()
    status = check_sequencer_status(qrm_rf, index, timeout_minutes=timeout_minutes)
    return acquisitions, status


def integrated_iq(acquisitions: dict[str, Any], *, integration_length_ns: int) -> complex:
    measurement = acquisitions["measurement"]["acquisition"]["bins"]
    integration = measurement["integration"]
    avg_cnt = np.asarray(measurement.get("avg_cnt", [1]), dtype=float)
    count = float(avg_cnt[0]) if avg_cnt.size and avg_cnt[0] else 1.0
    i_value = float(np.asarray(integration["path0"], dtype=float)[0])
    q_value = float(np.asarray(integration["path1"], dtype=float)[0])
    scale = count * float(integration_length_ns)
    return complex(i_value / scale, q_value / scale)


def scope_iq(acquisitions: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, bool]:
    scope = acquisitions["measurement"]["acquisition"]["scope"]
    path0 = np.asarray(scope["path0"]["data"], dtype=float)
    path1 = np.asarray(scope["path1"]["data"], dtype=float)
    out_of_range = bool(scope["path0"].get("out-of-range")) or bool(scope["path1"].get("out-of-range"))
    return path0, path1, out_of_range
