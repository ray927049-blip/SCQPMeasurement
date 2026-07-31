from __future__ import annotations

import json

from scqp_qblox.hardware import cluster_session, inventory

from ._common import load, parser


def main() -> None:
    args = parser("Read-only Cluster connection and module inventory", output=False).parse_args()
    config = load(args)
    with cluster_session(config, output_capable=False) as cluster:
        result = {
            "cluster_name": str(cluster.get_name()) if hasattr(cluster, "get_name") else config["cluster"]["name"],
            "system_status": str(cluster.get_system_status()),
            "hardware_revisions": (
                str(cluster.get_hardware_revisions()) if hasattr(cluster, "get_hardware_revisions") else "unavailable"
            ),
            "modules": inventory(cluster),
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

