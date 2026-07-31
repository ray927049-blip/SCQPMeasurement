from __future__ import annotations

import numpy as np

from scqp_qblox.acquisition import configure_qrm_rf, run_and_fetch_qrm_rf, scope_iq
from scqp_qblox.config import ConfigError, assert_execute, check_duty_cycle, check_rf_frequency
from scqp_qblox.data import create_run_dir, save_run_metadata
from scqp_qblox.hardware import cluster_session, module_for
from scqp_qblox.sequences import qrm_rf_acquisition_sequence

from ._common import load, parser, print_plan


def main() -> None:
    args = parser("QRM-RF O1 -> fixed attenuator -> I1 loopback acquisition").parse_args()
    config = load(args)
    defaults = config["defaults"]
    module_cfg = config["modules"]["qrm_rf"]
    fixed_att = config["microwave_chain"].get("loopback_fixed_attenuation_db")
    rf_hz = float(module_cfg["lo_frequency_hz"]) + float(module_cfg["nco_frequency_hz"])
    check_rf_frequency(config, rf_hz)
    amplitude = min(float(defaults["waveform_amplitude"]), float(config["safety"]["max_qrm_rf_output_amplitude"]))
    parameters = {
        "wiring": "QRM-RF O1 -> fixed attenuator -> QRM-RF I1",
        "fixed_attenuation_db": fixed_att,
        "rf_frequency_hz_nominal": rf_hz,
        "pulse_length_ns": defaults["waveform_length_ns"],
        "acquisition_length_ns": defaults["acquisition_length_ns"],
        "amplitude": amplitude,
        "averages": defaults["averages"],
        "period_ns": defaults["repeat_period_ns"],
    }
    sequence_dict = qrm_rf_acquisition_sequence(**{key: parameters[key] for key in (
        "pulse_length_ns", "acquisition_length_ns", "amplitude", "averages", "period_ns"
    )})
    check_duty_cycle(
        config,
        active_ns=max(int(parameters["pulse_length_ns"]), int(parameters["acquisition_length_ns"])),
        period_ns=int(parameters["period_ns"]),
    )
    print_plan("QRM-RF loopback plan", parameters, execute=args.execute)
    if not args.execute:
        print("Generated Q1ASM:\n" + sequence_dict["program"])
        return
    assert_execute(args.execute)
    if fixed_att is None:
        raise ConfigError("Set microwave_chain.loopback_fixed_attenuation_db after checking the physical attenuator")
    if float(fixed_att) < 30:
        raise ConfigError("First loopback requires at least 30 dB of verified fixed external attenuation")

    with cluster_session(config, reset=args.reset, output_capable=True) as cluster:
        module = module_for(cluster, config, "qrm_rf")
        configure_qrm_rf(
            module,
            module_cfg,
            sequence_dict,
            lo_frequency_hz=float(module_cfg["lo_frequency_hz"]),
            acquisition_length_ns=int(defaults["acquisition_length_ns"]),
        )
        acquisitions, sequencer_status = run_and_fetch_qrm_rf(
            module,
            index=int(module_cfg["sequencer"]),
            timeout_minutes=float(defaults["timeout_minutes"]),
            save_scope=True,
        )
        path0, path1, out_of_range = scope_iq(acquisitions)

    run_dir = create_run_dir(args.data_root, "qrm_rf_loopback")
    save_run_metadata(
        run_dir,
        config=config,
        parameters=parameters,
        status={"sequencer": sequencer_status, "scope_out_of_range": out_of_range},
    )
    np.savetxt(
        run_dir / "scope.csv",
        np.column_stack([np.arange(len(path0)), path0, path1]),
        delimiter=",",
        header="time_ns,path0,path1",
        comments="",
    )
    import matplotlib.pyplot as plt

    fig, axis = plt.subplots(constrained_layout=True)
    axis.plot(path0, label="path0")
    axis.plot(path1, label="path1")
    axis.set(xlabel="Time (ns)", ylabel="Normalized ADC amplitude")
    axis.grid(alpha=0.2)
    axis.legend()
    fig.savefig(run_dir / "scope.png", dpi=180)
    plt.close(fig)
    print(f"Saved loopback data to {run_dir}")


if __name__ == "__main__":
    main()
