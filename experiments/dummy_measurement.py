from __future__ import annotations

import numpy as np

from scqp_qblox.config import ConfigError, check_rf_frequency
from scqp_qblox.data import create_run_dir, save_frequency_sweep, save_run_metadata
from scqp_qblox.dummy import synthetic_transmission

from ._common import load, parser, print_plan


def main() -> None:
    cli = parser(
        "Offline dummy S21 measurement; never imports the Qblox driver or connects to hardware",
        output=False,
    )
    cli.add_argument("--start-hz", type=float)
    cli.add_argument("--stop-hz", type=float)
    cli.add_argument("--points", type=int)
    cli.add_argument("--resonance-hz", type=float)
    cli.add_argument("--linewidth-hz", type=float)
    cli.add_argument("--noise-std", type=float, default=0.002)
    cli.add_argument("--seed", type=int, default=12345)
    args = cli.parse_args()

    config = load(args)
    defaults = config["defaults"]
    start_hz = float(args.start_hz or defaults["probe_start_hz"])
    stop_hz = float(args.stop_hz or defaults["probe_stop_hz"])
    points = int(args.points or defaults["probe_points"])
    resonance_hz = float(args.resonance_hz or (start_hz + stop_hz) / 2.0)
    linewidth_hz = float(args.linewidth_hz or (stop_hz - start_hz) / 15.0)

    if points < 2 or stop_hz <= start_hz:
        raise ConfigError("Dummy frequency sweep needs points >= 2 and stop > start")
    check_rf_frequency(config, start_hz)
    check_rf_frequency(config, stop_hz)
    if not start_hz <= resonance_hz <= stop_hz:
        raise ConfigError("Dummy resonance must be inside the requested frequency sweep")
    if linewidth_hz <= 0:
        raise ConfigError("Dummy linewidth must be positive")
    if args.noise_std < 0:
        raise ConfigError("Dummy noise standard deviation must be non-negative")

    parameters = {
        "backend": "dummy",
        "measurement": "synthetic relative S21",
        "start_hz": start_hz,
        "stop_hz": stop_hz,
        "points": points,
        "resonance_hz": resonance_hz,
        "linewidth_hz": linewidth_hz,
        "noise_std": args.noise_std,
        "seed": args.seed,
    }
    print_plan("Offline dummy measurement plan", parameters, execute=True)

    frequency_hz = np.linspace(start_hz, stop_hz, points)
    i_values, q_values = synthetic_transmission(
        frequency_hz,
        resonance_hz=resonance_hz,
        linewidth_hz=linewidth_hz,
        noise_std=args.noise_std,
        seed=args.seed,
    )

    run_dir = create_run_dir(args.data_root, "dummy_measurement")
    save_run_metadata(
        run_dir,
        config=config,
        parameters=parameters,
        status={
            "backend": "dummy",
            "connected_to_hardware": False,
            "points_completed": points,
            "result": "success",
        },
    )
    save_frequency_sweep(
        run_dir,
        frequency_hz=frequency_hz,
        i_values=i_values,
        q_values=q_values,
        prefix="dummy_transmission",
    )
    print(f"Dummy measurement succeeded; saved synthetic data to {run_dir}")


if __name__ == "__main__":
    main()
