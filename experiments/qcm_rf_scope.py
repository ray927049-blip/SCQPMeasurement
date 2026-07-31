from __future__ import annotations

from scqp_qblox.acquisition import configure_qcm_rf_scope
from scqp_qblox.config import assert_execute, check_duty_cycle, check_rf_frequency
from scqp_qblox.data import create_run_dir, save_run_metadata
from scqp_qblox.hardware import check_sequencer_status, cluster_session, module_for
from scqp_qblox.sequences import qcm_rf_scope_sequence

from ._common import load, parser, print_plan


def main() -> None:
    args = parser("Finite low-power QCM-RF II burst for RF scope/spectrum-analyzer bring-up").parse_args()
    config = load(args)
    defaults = config["defaults"]
    module_cfg = config["modules"]["qcm_rf"]
    rf_hz = float(module_cfg["lo_frequency_hz"]) + float(module_cfg["nco_frequency_hz"])
    check_rf_frequency(config, rf_hz)
    amplitude = min(float(defaults["waveform_amplitude"]), float(config["safety"]["max_qcm_rf_output_amplitude"]))
    parameters = {
        "slot": module_cfg["slot"],
        "output": module_cfg["output"],
        "rf_frequency_hz_nominal": rf_hz,
        "length_ns": defaults["waveform_length_ns"],
        "amplitude": amplitude,
        "repetitions": defaults["repeat_count"],
        "period_ns": defaults["repeat_period_ns"],
        "output_attenuation_db": module_cfg["output_attenuation_db"],
    }
    sequence_dict = qcm_rf_scope_sequence(**{key: parameters[key] for key in ("length_ns", "amplitude", "repetitions", "period_ns")})
    check_duty_cycle(config, active_ns=int(parameters["length_ns"]), period_ns=int(parameters["period_ns"]))
    print_plan("QCM-RF II scope test plan", parameters, execute=args.execute)
    if not args.execute:
        print("Generated Q1ASM:\n" + sequence_dict["program"])
        return
    assert_execute(args.execute)

    status: dict[str, str] = {}
    with cluster_session(config, reset=args.reset, output_capable=True) as cluster:
        module = module_for(cluster, config, "qcm_rf")
        configure_qcm_rf_scope(module, module_cfg, sequence_dict)
        index = int(module_cfg["sequencer"])
        module.arm_sequencer(index)
        module.start_sequencer(index)
        status["sequencer"] = check_sequencer_status(
            module, index, timeout_minutes=float(defaults["timeout_minutes"])
        )

    run_dir = create_run_dir(args.data_root, "qcm_rf_scope")
    save_run_metadata(run_dir, config=config, parameters=parameters, status=status)
    print(f"Saved run metadata to {run_dir}")


if __name__ == "__main__":
    main()
