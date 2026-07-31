from __future__ import annotations

import pytest

from scqp_qblox.sequences import (
    SequenceError,
    parametric_pair_sequences,
    qcm_scope_sequence,
    qrm_rf_acquisition_sequence,
)


def test_qcm_scope_is_finite_and_turns_marker_off():
    sequence = qcm_scope_sequence(length_ns=100, amplitude=0.002, repetitions=10, period_ns=10000)
    assert "move 10,R0" in sequence["program"]
    assert "loop R0,@scope_loop" in sequence["program"]
    assert "set_mrk 0" in sequence["program"]
    assert "wait 9896" in sequence["program"]
    assert sequence["program"].endswith("stop")


def test_qrm_sequence_has_acquisition_and_rf_switch_cleanup():
    sequence = qrm_rf_acquisition_sequence(
        pulse_length_ns=100,
        acquisition_length_ns=1000,
        amplitude=0.002,
        averages=20,
        period_ns=10000,
    )
    assert sequence["acquisitions"]["measurement"]["num_bins"] == 1
    assert "set_mrk 3" in sequence["program"]
    assert "set_mrk 0" in sequence["program"]


def test_invalid_timing_is_rejected():
    with pytest.raises(SequenceError):
        qcm_scope_sequence(length_ns=101, amplitude=0.002, repetitions=1, period_ns=10000)


def test_parametric_sequences_are_synchronized_and_finite():
    qcm, qrm = parametric_pair_sequences(
        flux_length_ns=2000,
        flux_amplitude=0.002,
        probe_length_ns=100,
        probe_amplitude=0.002,
        pump_lead_ns=100,
        acquisition_length_ns=1000,
        averages=10,
        period_ns=10000,
    )
    assert qcm["program"].startswith("wait_sync")
    assert qrm["program"].startswith("wait_sync")
    assert qcm["program"].endswith("stop")
    assert qrm["program"].endswith("stop")
