"""
Run the long-run network metrics pipeline on the microchip-content subnetwork.

PLAID's microchip indicator is fractional at HS4 (= share of HS6 children flagged
as containing microchips). When we built baci_edges_country_microchip.parquet,
each bilateral trade flow was split fractionally between microchip and
non-microchip components. Here we take the 'microchip' partition and treat it
as the strategic-tech subnetwork.

Outputs in BACI_HS92_V202601/:
  long_run_global_metrics_microchip.csv
  long_run_country_metrics_microchip.csv
  long_run_community_assignments_microchip.csv
"""

from pathlib import Path

import pandas as pd

from long_run_network_metrics import run_long_run

ROOT = Path(__file__).parent
BACI_DIR = ROOT / "BACI_HS92_V202601"
EDGES = BACI_DIR / "baci_edges_country_microchip.parquet"


def main() -> None:
    edges = pd.read_parquet(EDGES)
    print(f"[load] {EDGES.name}  shape={edges.shape}")

    sub = edges.loc[
        edges["microchip"] == "microchip",
        ["year", "source", "target", "value_busd"],
    ].copy()

    out_g = BACI_DIR / "long_run_global_metrics_microchip.csv"
    out_c = BACI_DIR / "long_run_country_metrics_microchip.csv"
    out_m = BACI_DIR / "long_run_community_assignments_microchip.csv"

    run_long_run(sub, out_g, out_c, out_m, label="microchip")


if __name__ == "__main__":
    main()
