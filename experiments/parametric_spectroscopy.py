from __future__ import annotations

import numpy as np
import xarray as xr

from scqp_qblox.acquisition import clear_acquisitions, configure_qrm_rf, integrated_iq
from scqp_qblox.config import (
    ConfigError,
    assert_execute,
    check_parametric_frequency,
    check_duty_cycle,
    check_rf_frequency,
    require_verified_sample_connectors,
)
from scqp_qblox.data import create_run_dir, save_run_metadata
from scqp_qblox.hardware import check_sequencer_status, cluster_session, module_for, ramp_qcm_offset, sequencer
from scqp_qblox.sequences import parametric_pair_sequences

from ._common import load, parser, print_plan


def main() -> None:
    cli = parser("Pump-OFF/ON flux-parametric spectroscopy with a fixed microwave probe")
    cli.add_argument("--side", choices=("left", "right"), default="left")
    cli.add_argument("--probe-hz", type=float, required=True)
    cli.add_argument("--pump-start-hz", type=float)
    cli.add_argument("--pump-stop-hz", type=float)
    cli.add_argument("--pump-points", type=int, default=101)
    cli.add_argument("--pump-amplitude", type=float)
    cli.add_argument("--flux-bias-v", type=float)
    args = cli.parse_args()
    config = load(args)
    defaults = config["defaults"]
    safety = config["safety"]
    flux_cfg = config["flux"]
    probe_hz = float(args.probe_hz)
    check_rf_frequency(config, probe_hz)
    pump_start = float(args.pump_start_hz or defaults["parametric_start_hz"])
    pump_stop = float(args.pump_stop_hz or defaults["parametric_stop_hz"])
    check_parametric_frequency(config, pump_start)
    check_parametric_frequency(config, pump_stop)
    if args.pump_points < 2 or pump_stop <= pump_start:
        raise ConfigError("Parametric sweep needs pump-points >= 2 and stop > start")
    pump_amplitude = float(args.pump_amplitude or defaults["waveform_amplitude"])
    if not 0 < pump_amplitude <= float(safety["max_flux_waveform_amplitude"]):
        raise ConfigError("pump-amplitude is outside the configured flux-waveform safety limit")
    flux_bias_v = (
        float(flux_cfg[f"{args.side}_idle_voltage_v"])
        if args.flux_bias_v is None
        else float(args.flux_bias_v)
    )
    if not float(flux_cfg[f"{args.side}_min_voltage_v"]) <= flux_bias_v <= float(
        flux_cfg[f"{args.side}_max_voltage_v"]
    ):
        raise ConfigError("flux-bias-v is outside the configured side-specific limits")

    acquisition_length_ns = int(defaults["acquisition_length_ns"])
    pump_lead_ns = 100
    flux_length_ns = max(2000, pump_lead_ns + acquisition_length_ns + 100)
    parameters = {
        "side": args.side,
        "probe_hz": probe_hz,
        "pump_start_hz": pump_start,
        "pump_stop_hz": pump_stop,
        "pump_points": args.pump_points,
        "pump_amplitude": pump_amplitude,
        "flux_bias_v": flux_bias_v,
        "pump_states": ["off", "on"],
        "measurement": "relative S21 response; not direct qubit population",
    }
    qcm_sequence, qrm_sequence = parametric_pair_sequences(
        flux_length_ns=flux_length_ns,
        flux_amplitude=pump_amplitude,
        probe_length_ns=int(defaults["waveform_length_ns"]),
        probe_amplitude=min(float(defaults["waveform_amplitude"]), float(safety["max_qrm_rf_output_amplitude"])),
        pump_lead_ns=pump_lead_ns,
        acquisition_length_ns=acquisition_length_ns,
        averages=int(defaults["averages"]),
        period_ns=int(defaults["repeat_period_ns"]),
    )
    check_duty_cycle(config, active_ns=flux_length_ns, period_ns=int(defaults["repeat_period_ns"]))
    print_plan("Flux-parametric spectroscopy plan", parameters, execute=args.execute)
    if not args.execute:
        print("QCM Q1ASM:\n" + qcm_sequence["program"])
        print("\nQRM-RF Q1ASM:\n" + qrm_sequence["program"])
        return
    assert_execute(args.execute)
    require_verified_sample_connectors(config)
    if config["microwave_chain"].get("source_to_sample_attenuation_db") is None:
        raise ConfigError("Fill microwave_chain.source_to_sample_attenuation_db before connecting the sample")

    pump_frequency = np.linspace(pump_start, pump_stop, args.pump_points)
    i_data = np.empty((len(pump_frequency), 2))
    q_data = np.empty_like(i_data)
    statuses: list[str] = []
    with cluster_session(config, reset=args.reset, output_capable=True, restore_flux_idle=True) as cluster:
        qcm = module_for(cluster, config, "qcm")
        qrm_rf = module_for(cluster, config, "qrm_rf")
        qcm_cfg = config["modules"]["qcm"]
        qrm_cfg = config["modules"]["qrm_rf"]
        qcm_index = int(qcm_cfg["parametric_sequencer"])
        qrm_index = int(qrm_cfg["sequencer"])
        qcm_seq = sequencer(qcm, qcm_index)
        qrm_seq = sequencer(qrm_rf, qrm_index)
        flux_output = int(qcm_cfg[f"{args.side}_flux_output"])

        ramp_qcm_offset(
            qcm,
            flux_output,
            flux_bias_v,
            step_v=float(flux_cfg["ramp_step_v"]),
            delay_s=float(flux_cfg["ramp_delay_s"]),
        )
        qcm.disconnect_outputs()
        qcm_seq.sequence(qcm_sequence)
        qcm_seq.sync_en(True)
        qcm_seq.mod_en_awg(True)
        qcm_seq.gain_awg_path1(0.0)
        getattr(qcm_seq, f"connect_out{flux_output}")("I")

        nco_hz = float(qrm_cfg["nco_frequency_hz"])
        configure_qrm_rf(
            qrm_rf,
            qrm_cfg,
            qrm_sequence,
            lo_frequency_hz=probe_hz - nco_hz,
            acquisition_length_ns=acquisition_length_ns,
        )

        for row, pump_hz in enumerate(pump_frequency):
            qcm_seq.nco_freq(float(pump_hz))
            for state_index, gain in enumerate((0.0, 1.0)):
                qcm_seq.gain_awg_path0(gain)
                clear_acquisitions(qrm_rf, qrm_index)
                qcm.arm_sequencer(qcm_index)
                qrm_rf.arm_sequencer(qrm_index)
                cluster.start_sequencer()
                qrm_seq.get_acquisition_status(timeout=float(defaults["timeout_minutes"]))
                try:
                    acquisitions = qrm_seq.get_acquisitions(as_numpy=True)
                except TypeError:
                    acquisitions = qrm_seq.get_acquisitions()
                value = integrated_iq(acquisitions, integration_length_ns=acquisition_length_ns)
                i_data[row, state_index] = value.real
                q_data[row, state_index] = value.imag
                statuses.append(check_sequencer_status(qrm_rf, qrm_index, timeout_minutes=float(defaults["timeout_minutes"])))
                check_sequencer_status(qcm, qcm_index, timeout_minutes=float(defaults["timeout_minutes"]))

    amplitude = np.hypot(i_data, q_data)
    phase = np.arctan2(q_data, i_data)
    dataset = xr.Dataset(
        data_vars={
            "I": (("parametric_frequency_hz", "pump_state"), i_data),
            "Q": (("parametric_frequency_hz", "pump_state"), q_data),
            "amplitude": (("parametric_frequency_hz", "pump_state"), amplitude),
            "phase_rad": (("parametric_frequency_hz", "pump_state"), phase),
            "delta_I": ("parametric_frequency_hz", i_data[:, 1] - i_data[:, 0]),
            "delta_Q": ("parametric_frequency_hz", q_data[:, 1] - q_data[:, 0]),
            "delta_amplitude": ("parametric_frequency_hz", amplitude[:, 1] - amplitude[:, 0]),
        },
        coords={"parametric_frequency_hz": pump_frequency, "pump_state": ["off", "on"]},
        attrs={"probe_frequency_hz": probe_hz, "interpretation": "transmission response, not population"},
    )
    run_dir = create_run_dir(args.data_root, "parametric_spectroscopy")
    dataset.to_netcdf(run_dir / "parametric_spectroscopy.nc", engine="h5netcdf")
    save_run_metadata(
        run_dir,
        config=config,
        parameters=parameters,
        status={"measurements_completed": len(statuses), "last_sequencer_status": statuses[-1]},
    )
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 1, sharex=True, constrained_layout=True)
    axes[0].plot(pump_frequency / 1e6, dataset["delta_amplitude"].values)
    axes[0].set_ylabel("Delta amplitude")
    axes[1].plot(pump_frequency / 1e6, dataset["delta_I"].values, label="Delta I")
    axes[1].plot(pump_frequency / 1e6, dataset["delta_Q"].values, label="Delta Q")
    axes[1].set(xlabel="Parametric frequency (MHz)", ylabel="Delta I/Q")
    axes[1].legend()
    for axis in axes:
        axis.grid(alpha=0.2)
    fig.savefig(run_dir / "parametric_response.png", dpi=180)
    plt.close(fig)
    print(f"Saved parametric spectroscopy to {run_dir}")


if __name__ == "__main__":
    main()
