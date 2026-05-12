"""
Partition BACI bilateral trade by FGKK tariff treatment status (z_usch_w > 0).

Two parallel edge lists:
  baci_edges_country_by_tariff.parquet
    year × source × target × tariff_status × value_busd
    tariff_status ∈ {treated, untreated}

Also writes a 3-bucket variant for more granular analysis:
  baci_edges_country_by_tariff_bucket.parquet
    year × source × target × tariff_bucket × value_busd
    tariff_bucket ∈ {none, low_0_7.5, mid_7.5_17.5, high_17.5+}

Assignment rule:
  - HS6 in FGKK with z_usch_w > 0  → treated (and bucketed by post-tariff size)
  - HS6 in FGKK with z_usch_w = 0  → untreated (FGKK control)
  - HS6 NOT in FGKK universe       → untreated (outside FGKK's tracked set)

Caveats:
  - Tariffs are US-on-China bilateral, but we tag ALL global trade in tariffed
    HS6 codes as "treated". This tests whether tariff-targeted products show
    global network restructuring, not just US-CHN bilateral effects.
  - BACI = HS92, FGKK uses HS17 (likely). HS6 mismatch is ~5%, treated as
    untreated by default. Net: a slight under-count of treated trade value.
"""

from __future__ import annotations
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.dataset as ds

ROOT = Path(__file__).parent
BACI_DIR = ROOT / "BACI_HS92_V202601"
COMBINED = BACI_DIR / "baci_combined.parquet"
TARIFF_MASTER = BACI_DIR / "hs6_tariff_master.csv"

OUT_BIN = BACI_DIR / "baci_edges_country_by_tariff.parquet"
OUT_BUCKET = BACI_DIR / "baci_edges_country_by_tariff_bucket.parquet"


def build_hs6_lookup() -> tuple[set[str], dict[str, str]]:
    """Return (set of treated HS6, dict mapping HS6 → tariff_bucket)."""
    tm = pd.read_csv(TARIFF_MASTER, dtype={"hs6": str})
    tm["hs6"] = tm["hs6"].str.zfill(6)
    treated_set = set(tm.loc[tm["tariff_post_w"] > 0, "hs6"])
    bucket_map = dict(zip(tm["hs6"], tm["tariff_bucket"].astype(str)))
    print(f"[tariff] FGKK universe: {len(tm):,} HS6  treated={len(treated_set):,}")
    return treated_set, bucket_map


def main() -> None:
    treated_set, bucket_map = build_hs6_lookup()

    dset = ds.dataset(COMBINED, format="parquet")
    years = sorted(int(y) for y in pd.unique(
        dset.to_table(columns=["t"]).to_pandas()["t"]
    ))
    print(f"[stream] {len(years)} years")

    acc_bin    = {"treated":   defaultdict(float), "untreated": defaultdict(float)}
    acc_bucket = defaultdict(lambda: defaultdict(float))  # bucket → {(y,s,t): v}

    t0 = time.time()
    for yr in years:
        t = time.time()
        tbl = dset.to_table(
            columns=["t","k","v","iso3_exporter","iso3_importer"],
            filter=ds.field("t") == yr,
        )
        df = tbl.to_pandas()
        # Tag rows
        is_treated = df["k"].isin(treated_set)
        # Binary
        treated_rows  = df.loc[is_treated]
        untreated_rows = df.loc[~is_treated]
        for status, sub in [("treated", treated_rows), ("untreated", untreated_rows)]:
            g = sub.groupby(["iso3_exporter","iso3_importer"], observed=True)["v"].sum()
            for (src, tgt), val in g.items():
                acc_bin[status][(yr, src, tgt)] += float(val)
        # Bucket
        bucket = df["k"].map(bucket_map).fillna("none")  # un-mapped → 'none'
        for buck, idx in df.groupby(bucket).groups.items():
            sub = df.loc[idx]
            g = sub.groupby(["iso3_exporter","iso3_importer"], observed=True)["v"].sum()
            for (src, tgt), val in g.items():
                acc_bucket[str(buck)][(yr, src, tgt)] += float(val)
        t_pct = 100.0 * treated_rows["v"].sum() / df["v"].sum()
        print(f"  {yr}  rows={len(df):>10,}  treated_share={t_pct:5.2f}%  dt={time.time()-t:4.1f}s")

    def materialise(acc: dict, key_col: str) -> pd.DataFrame:
        rows = []
        for status, d in acc.items():
            for (y, s, t), v in d.items():
                rows.append({"year": y, "source": s, "target": t, key_col: status,
                             "value_kusd": v})
        out = pd.DataFrame.from_records(rows)
        out["value_busd"] = out["value_kusd"] / 1_000_000
        return out[["year","source","target",key_col,"value_kusd","value_busd"]]

    bin_df = materialise(acc_bin, "tariff_status")
    bin_df.to_parquet(OUT_BIN, compression="snappy", index=False)
    print(f"\n[binary] {len(bin_df):,} rows → {OUT_BIN.name}")

    buck_df = materialise(acc_bucket, "tariff_bucket")
    buck_df.to_parquet(OUT_BUCKET, compression="snappy", index=False)
    print(f"[bucket] {len(buck_df):,} rows → {OUT_BUCKET.name}")
    print(f"[total ] {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
