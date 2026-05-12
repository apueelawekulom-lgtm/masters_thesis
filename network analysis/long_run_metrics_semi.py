"""
Run the long-run network metrics pipeline on the narrow semiconductor subnetwork
(HS 8541 + HS 8542). Outputs in BACI_HS92_V202601/:
  long_run_global_metrics_semi.csv
  long_run_country_metrics_semi.csv
  long_run_community_assignments_semi.csv
"""

from pathlib import Path

import pandas as pd

from long_run_network_metrics import run_long_run

ROOT = Path(__file__).parent
BACI_DIR = ROOT / "BACI_HS92_V202601"
EDGES = BACI_DIR / "baci_edges_country_semiconductors.parquet"


def main() -> None:
    edges = pd.read_parquet(EDGES)
    print(f"[load] {EDGES.name}  shape={edges.shape}")
    sub = edges[["year","source","target","value_busd"]].copy()
    run_long_run(
        sub,
        BACI_DIR / "long_run_global_metrics_semi.csv",
        BACI_DIR / "long_run_country_metrics_semi.csv",
        BACI_DIR / "long_run_community_assignments_semi.csv",
        label="semiconductors",
    )


if __name__ == "__main__":
    main()
