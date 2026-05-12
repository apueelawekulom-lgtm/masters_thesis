"""
Run long-run network metrics on each tariff stratum.

Outputs in BACI_HS92_V202601/:
  long_run_global_metrics_tariff_{treated,untreated}.csv
  long_run_country_metrics_tariff_{treated,untreated}.csv
  long_run_community_assignments_tariff_{treated,untreated}.csv

  long_run_global_metrics_tariff_bucket_{none,low_0_7.5,mid_7.5_17.5,high_17.5+}.csv
  long_run_country_metrics_tariff_bucket_{...}.csv
  long_run_community_assignments_tariff_bucket_{...}.csv
"""

from pathlib import Path

import pandas as pd

from long_run_network_metrics import run_long_run

ROOT = Path(__file__).parent
BACI_DIR = ROOT / "BACI_HS92_V202601"
EDGES_BIN    = BACI_DIR / "baci_edges_country_by_tariff.parquet"
EDGES_BUCKET = BACI_DIR / "baci_edges_country_by_tariff_bucket.parquet"


def run_partition(df: pd.DataFrame, key_col: str, file_safe_tag: str, label_prefix: str) -> None:
    for value in sorted(df[key_col].unique()):
        sub = df.loc[df[key_col] == value, ["year","source","target","value_busd"]].copy()
        safe = value.replace(".","p").replace("+","plus").replace(" ","_")
        out_g = BACI_DIR / f"long_run_global_metrics_{file_safe_tag}_{safe}.csv"
        out_c = BACI_DIR / f"long_run_country_metrics_{file_safe_tag}_{safe}.csv"
        out_m = BACI_DIR / f"long_run_community_assignments_{file_safe_tag}_{safe}.csv"
        run_long_run(sub, out_g, out_c, out_m, label=f"{label_prefix}:{value}")
        print()


def main() -> None:
    bin_df = pd.read_parquet(EDGES_BIN)
    print(f"[load] {EDGES_BIN.name}  shape={bin_df.shape}")
    run_partition(bin_df, "tariff_status", "tariff", "tariff")

    buck_df = pd.read_parquet(EDGES_BUCKET)
    print(f"[load] {EDGES_BUCKET.name}  shape={buck_df.shape}")
    run_partition(buck_df, "tariff_bucket", "tariff_bucket", "bucket")


if __name__ == "__main__":
    main()
