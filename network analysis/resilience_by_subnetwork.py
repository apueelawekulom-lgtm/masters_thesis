"""
Run the resilience pipeline on each BEC subnetwork and on the narrow
semiconductor (HS 8541+8542) subnetwork.

Thresholds chosen so each subnetwork retains roughly comparable edge counts
(scaling roughly with the subnetwork's total trade volume):
  intermediate : $30M
  consumption  : $15M
  capital      : $10M
  semiconductor: $3M
"""

from pathlib import Path

import pandas as pd

from resilience_aggregate import run_resilience

ROOT = Path(__file__).parent
BACI_DIR = ROOT / "BACI_HS92_V202601"

JOBS = [
    # (file,                                          filter,           threshold, suffix,            label)
    ("baci_edges_country_by_bec.parquet",            ("bec_stage","intermediate"), 0.030, "_bec_intermediate", "bec:intermediate"),
    ("baci_edges_country_by_bec.parquet",            ("bec_stage","capital"),       0.010, "_bec_capital",      "bec:capital"),
    ("baci_edges_country_by_bec.parquet",            ("bec_stage","consumption"),   0.015, "_bec_consumption",  "bec:consumption"),
    ("baci_edges_country_semiconductors.parquet",    None,                          0.003, "_semi",             "semiconductor"),
]


def main() -> None:
    for fname, flt, thresh, suffix, label in JOBS:
        df = pd.read_parquet(BACI_DIR / fname)
        if flt is not None:
            col, val = flt
            df = df[df[col] == val]
        sub = df[["year","source","target","value_busd"]].copy()
        run_resilience(sub, thresh, BACI_DIR, suffix=suffix, label=label)


if __name__ == "__main__":
    main()
