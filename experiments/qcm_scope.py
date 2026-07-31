from __future__ import annotations

from scqp_qblox.acquisition import configure_qcm_scope
from scqp_qblox.config import assert_execute, check_duty_cycle
from scqp_qblox.data import create_run_dir, save_run_metadata
from scqp_qblox.hardware import check_sequencer_status, cluster_session, module_for
from scqp_qblox.sequences import qcm_scope_sequence

from ._common import load, parser, print_plan


def main() -> None:
    cli = parser("Finite low-amplitude QCM pulse for oscilloscope bring-up")
    cli.add_argument("--side", choices=("left", "right"), default="left")
    args = cli.parse_args()
    config = load(args)
    defaults = config["defaults"]
    qcm_cfg = config["modules"]["qcm"]
    output = int(qcm_cfg[f"{args.side}_flux_output"])
    parameters = {
        "side": args.side,
        "slot": qcm_cfg["slot"],
        "output": output,
        "length_ns": defaults["waveform_length_ns"],
        "amplitude": defaults["waveform_amplitude"],
        "repetitions": defaults["repeat_count"],
        "period_ns": defaults["repeat_period_ns"],
    }
    sequence_dict = qcm_scope_sequence(**{key: parameters[key] for key in ("length_ns", "amplitude", "repetitions", "period_ns")})
    check_duty_cycle(config, active_ns=int(parameters["length_ns"]), period_ns=int(parameters["period_ns"]))
    print_plan("QCM scope test plan", parameters, execute=args.execute)
    if not args.execute:
        print("Generated Q1ASM:\n" + sequence_dict["program"])
        return
    assert_execute(args.execute)

    status: dict[str, str] = {}
    with cluster_session(config, reset=args.reset, output_capable=True, restore_flux_idle=False) as cluster:
        qcm = module_for(cluster, config, "qcm")
        getattr(qcm, f"out{output}_offset")(0.0)
        configure_qcm_scope(qcm, qcm_cfg, sequence_dict, output=output)
        index = int(qcm_cfg["parametric_sequencer"])
        qcm.arm_sequencer(index)
        qcm.start_sequencer(index)
        status["sequencer"] = check_sequencer_status(
            qcm, index, timeout_minutes=float(defaults["timeout_minutes"])
        )

    run_dir = create_run_dir(args.data_root, "qcm_scope")
    save_run_metadata(run_dir, config=config, parameters=parameters, status=status)
    print(f"Saved run metadata to {run_dir}")


if __name__ == "__main__":
    main()
