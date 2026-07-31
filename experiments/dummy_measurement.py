from __future__ import annotations

import numpy as np

from scqp_qblox.config import ConfigError, check_rf_frequency
from scqp_qblox.data import create_run_dir, save_dispersive_power_sweep, save_run_metadata
from scqp_qblox.dummy import synthetic_dispersive_power_sweep

from ._common import load, parser, print_plan


def main() -> None:
    cli = parser(
        "Offline resonator power sweep with qubit dispersive shift; never connects to hardware",
        output=False,
    )
    cli.add_argument("--start-hz", type=float)
    cli.add_argument("--stop-hz", type=float)
    cli.add_argument("--points", type=int)
    cli.add_argument("--resonance-hz", type=float)
    cli.add_argument("--linewidth-hz", type=float)
    cli.add_argument("--chi-hz", type=float, default=2.0e6)
    cli.add_argument("--power-start-dbm", type=float, default=-70.0)
    cli.add_argument("--power-stop-dbm", type=float, default=-20.0)
    cli.add_argument("--power-points", type=int, default=51)
    cli.add_argument("--critical-power-dbm", type=float, default=-35.0)
    cli.add_argument("--noise-std", type=float, default=0.002)
    cli.add_argument("--seed", type=int, default=12345)
    args = cli.parse_args()

    config = load(args)
    qrm_cfg = config["modules"]["qrm_rf"]
    resonance_hz = float(
        args.resonance_hz
        or (float(qrm_cfg["lo_frequency_hz"]) + float(qrm_cfg["nco_frequency_hz"]))
    )
    start_hz = float(args.start_hz or resonance_hz - 10.0e6)
    stop_hz = float(args.stop_hz or resonance_hz + 10.0e6)
    points = int(args.points or 301)
    linewidth_hz = float(args.linewidth_hz or 1.5e6)

    if points < 2 or stop_hz <= start_hz:
        raise ConfigError("Dummy frequency sweep needs points >= 2 and stop > start")
    check_rf_frequency(config, start_hz)
    check_rf_frequency(config, stop_hz)
    if not start_hz <= resonance_hz <= stop_hz:
        raise ConfigError("Dummy resonance must be inside the requested frequency sweep")
    if linewidth_hz <= 0:
        raise ConfigError("Dummy linewidth must be positive")
    if args.chi_hz <= 0:
        raise ConfigError("Dummy chi must be positive")
    if args.power_points < 2 or args.power_stop_dbm <= args.power_start_dbm:
        raise ConfigError("Dummy power sweep needs power-points >= 2 and power-stop > power-start")
    if args.noise_std < 0:
        raise ConfigError("Dummy noise standard deviation must be non-negative")

    parameters = {
        "backend": "dummy",
        "measurement": "synthetic resonator power sweep with qubit dispersive shift",
        "start_hz": start_hz,
        "stop_hz": stop_hz,
        "points": points,
        "resonance_hz": resonance_hz,
        "linewidth_hz": linewidth_hz,
        "chi_hz": args.chi_hz,
        "low_power_resonance_separation_hz": 2.0 * args.chi_hz,
        "power_start_dbm": args.power_start_dbm,
        "power_stop_dbm": args.power_stop_dbm,
        "power_points": args.power_points,
        "critical_power_dbm": args.critical_power_dbm,
        "noise_std": args.noise_std,
        "seed": args.seed,
    }
    print_plan("Offline dummy measurement plan", parameters, execute=True)

    frequency_hz = np.linspace(start_hz, stop_hz, points)
    readout_power_dbm = np.linspace(
        args.power_start_dbm, args.power_stop_dbm, args.power_points
    )
    i_values, q_values, effective_chi_hz = synthetic_dispersive_power_sweep(
        frequency_hz,
        readout_power_dbm,
        resonator_hz=resonance_hz,
        chi_hz=args.chi_hz,
        linewidth_hz=linewidth_hz,
        critical_power_dbm=args.critical_power_dbm,
        noise_std=args.noise_std,
        seed=args.seed,
    )

    run_dir = create_run_dir(args.data_root, "dummy_dispersive_power")
    save_run_metadata(
        run_dir,
        config=config,
        parameters=parameters,
        status={
            "backend": "dummy",
            "connected_to_hardware": False,
            "qubit_states": ["g", "e"],
            "frequency_points": points,
            "power_points": args.power_points,
            "points_completed": 2 * points * args.power_points,
            "result": "success",
        },
    )
    save_dispersive_power_sweep(
        run_dir,
        frequency_hz=frequency_hz,
        readout_power_dbm=readout_power_dbm,
        i_values=i_values,
        q_values=q_values,
        effective_chi_hz=effective_chi_hz,
        resonator_hz=resonance_hz,
    )
    print(f"Dummy dispersive power sweep succeeded; saved data and plot to {run_dir}")


if __name__ == "__main__":
    main()
