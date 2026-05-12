"""
Run the long-run network metrics pipeline on each BEC stage separately
(intermediate / capital / consumption). Lets us compare GVC-subnetwork
restructuring against the aggregate-network story.

Outputs in BACI_HS92_V202601/:
  long_run_global_metrics_bec_{stage}.csv
  long_run_country_metrics_bec_{stage}.csv
  long_run_community_assignments_bec_{stage}.csv
"""

from pathlib import Path

import pandas as pd

from long_run_network_metrics import run_long_run

ROOT = Path(__file__).parent
BACI_DIR = ROOT / "BACI_HS92_V202601"
BEC_EDGES = BACI_DIR / "baci_edges_country_by_bec.parquet"

STAGES = ["intermediate", "capital", "consumption"]


def main() -> None:
    edges = pd.read_parquet(BEC_EDGES)
    print(f"[load] {BEC_EDGES.name}  shape={edges.shape}")

    for stage in STAGES:
        sub = edges.loc[edges["bec_stage"] == stage, ["year", "source", "target", "value_busd"]].copy()
        out_g = BACI_DIR / f"long_run_global_metrics_bec_{stage}.csv"
        out_c = BACI_DIR / f"long_run_country_metrics_bec_{stage}.csv"
        out_m = BACI_DIR / f"long_run_community_assignments_bec_{stage}.csv"
        run_long_run(sub, out_g, out_c, out_m, label=f"bec:{stage}")
        print()


if __name__ == "__main__":
    main()
