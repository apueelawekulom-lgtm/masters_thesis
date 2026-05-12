"""
Build PLAID-stratified country edge lists from baci_combined.parquet.

Bridges BACI HS92 ↔ PLAID HS22 by aggregating to HS4 chapter level
(99%+ trade-value coverage, ~90% within-HS4 PLAID homogeneity).

Approach: allocate each trade flow fractionally across PLAID strata using
HS4-level share columns (preserves trade-value totals; no hard cutoffs).

Inputs  : BACI_HS92_V202601/baci_combined.parquet
          PLAID Indicator/PLAID_v0.1_*.csv
Outputs : BACI_HS92_V202601/hs4_plaid_master.csv             — HS4 lookup
          BACI_HS92_V202601/baci_edges_country_by_bec.parquet
          BACI_HS92_V202601/baci_edges_country_by_rauch.parquet
          BACI_HS92_V202601/baci_edges_country_microchip.parquet

Streaming year-by-year; peak memory ~one year (~1.5 GB).
"""

from __future__ import annotations

import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds

ROOT = Path(__file__).parent
BACI_DIR = ROOT / "BACI_HS92_V202601"
PLAID_DIR = ROOT / "PLAID Indicator"
COMBINED = BACI_DIR / "baci_combined.parquet"

OUT_MASTER    = BACI_DIR / "hs4_plaid_master.csv"
OUT_BEC       = BACI_DIR / "baci_edges_country_by_bec.parquet"
OUT_RAUCH     = BACI_DIR / "baci_edges_country_by_rauch.parquet"
OUT_MICROCHIP = BACI_DIR / "baci_edges_country_microchip.parquet"


def build_hs4_plaid_master() -> pd.DataFrame:
    """One row per HS4: averaged PLAID shares + n_hs6 (children count)."""
    def load(fname: str) -> pd.DataFrame:
        d = pd.read_csv(PLAID_DIR / fname, dtype={"hs6_code": str})
        d["hs4"] = d["hs6_code"].str.zfill(6).str[:4]
        return d

    bec  = load("PLAID_v0.1_bec_H6.csv")
    rau  = load("PLAID_v0.1_rauch_H6.csv")
    chip = load("PLAID_v0.1_microchip_H6.csv")
    per  = load("PLAID_v0.1_perishability_H6.csv")
    haz  = load("PLAID_v0.1_hazmat_H6.csv")

    # BEC — average the three shares (they sum to 1 at HS6)
    a_bec = bec.groupby("hs4").agg(
        bec_share_capital      =("bec_share_capital",      "mean"),
        bec_share_intermediate =("bec_share_intermediate", "mean"),
        bec_share_consumption  =("bec_share_consumption",  "mean"),
        n_hs6                  =("hs6_code",               "size"),
    )
    # Renormalise to sum=1 (averages may drift slightly off)
    s = a_bec[["bec_share_capital","bec_share_intermediate","bec_share_consumption"]].sum(axis=1)
    for c in ["bec_share_capital","bec_share_intermediate","bec_share_consumption"]:
        a_bec[c] = a_bec[c] / s

    # Rauch — three shares (w=differentiated, r=reference-priced, n=homogeneous/world-priced)
    a_rau = rau.groupby("hs4").agg(
        rauch_share_w=("rauch_share_w", "mean"),
        rauch_share_r=("rauch_share_r", "mean"),
        rauch_share_n=("rauch_share_n", "mean"),
    )
    s = a_rau.sum(axis=1)
    for c in a_rau.columns:
        a_rau[c] = a_rau[c] / s

    # Microchip — fraction of HS6 children flagged as containing microchips
    a_chip = chip.groupby("hs4").agg(
        microchip_share         =("microchip_content",      "mean"),  # bool→fraction
        microchip_content_mean  =("microchip_content_mean", "mean"),
    )

    # Perishability + hazmat (kept as descriptive HS4 attributes)
    a_per = per.groupby("hs4").agg(
        perishability_class_mean=("perishability_class_mean","mean"),
        half_life_days_mean     =("half_life_days_mean",     "mean"),
    )
    a_haz = haz.groupby("hs4").agg(
        hazardous_share=("hazardous",      "mean"),
        hazardous_mean =("hazardous_mean", "mean"),
    )

    master = a_bec.join([a_rau, a_chip, a_per, a_haz], how="outer").reset_index()
    return master


def main() -> None:
    print("[plaid] building HS4 master …")
    master = build_hs4_plaid_master()
    master.to_csv(OUT_MASTER, index=False)
    print(f"  → {OUT_MASTER.name}  ({len(master):,} HS4 chapters)")

    # Compact lookup: HS4 → arrays of shares
    master = master.set_index("hs4")
    bec_cols    = ["bec_share_capital", "bec_share_intermediate", "bec_share_consumption"]
    rauch_cols  = ["rauch_share_w", "rauch_share_r", "rauch_share_n"]

    # Accumulators keyed by (year, source, target)
    acc_bec       = {c: defaultdict(float) for c in bec_cols}
    acc_rauch     = {c: defaultdict(float) for c in rauch_cols}
    acc_chip      = defaultdict(float)   # value * microchip_share
    acc_chip_comp = defaultdict(float)   # value * (1 - microchip_share)
    acc_unmatched = defaultdict(float)   # value of rows with no HS4 match

    dset = ds.dataset(COMBINED, format="parquet")
    years = sorted(int(y) for y in pd.unique(
        dset.to_table(columns=["t"]).to_pandas()["t"]
    ))
    print(f"[stream] {len(years)} years to process")

    t_total = time.time()
    for yr in years:
        t = time.time()
        tbl = dset.to_table(
            columns=["t","k","v","iso3_exporter","iso3_importer"],
            filter=ds.field("t") == yr,
        )
        df = tbl.to_pandas()
        df["hs4"] = df["k"].str[:4]
        df = df.join(master, on="hs4", how="left")

        # Unmatched flow (no PLAID HS4 record)
        unm = df["bec_share_capital"].isna()
        n_unmatched = int(unm.sum())
        v_unmatched = float(df.loc[unm, "v"].sum())
        v_total     = float(df["v"].sum())
        if v_unmatched > 0:
            for _, row in df.loc[unm, ["iso3_exporter","iso3_importer","v"]].iterrows():
                acc_unmatched[(yr, row.iso3_exporter, row.iso3_importer)] += float(row.v)

        # Drop unmatched for stratified allocation
        d = df.loc[~unm]

        # Vectorised BEC allocation
        for c in bec_cols:
            alloc = d["v"] * d[c]
            g = alloc.groupby([d["iso3_exporter"], d["iso3_importer"]]).sum()
            for (src, tgt), val in g.items():
                acc_bec[c][(yr, src, tgt)] += float(val)

        # Rauch
        for c in rauch_cols:
            alloc = d["v"] * d[c]
            g = alloc.groupby([d["iso3_exporter"], d["iso3_importer"]]).sum()
            for (src, tgt), val in g.items():
                acc_rauch[c][(yr, src, tgt)] += float(val)

        # Microchip (fractional)
        alloc_mc  = d["v"] * d["microchip_share"]
        alloc_nmc = d["v"] * (1.0 - d["microchip_share"])
        g_mc  = alloc_mc.groupby([d["iso3_exporter"], d["iso3_importer"]]).sum()
        g_nmc = alloc_nmc.groupby([d["iso3_exporter"], d["iso3_importer"]]).sum()
        for (src, tgt), val in g_mc.items():
            acc_chip[(yr, src, tgt)] += float(val)
        for (src, tgt), val in g_nmc.items():
            acc_chip_comp[(yr, src, tgt)] += float(val)

        cov_pct = 100.0 * (1 - v_unmatched / v_total) if v_total > 0 else 0.0
        print(
            f"  {yr}  rows={len(df):>10,}  unmatched_rows={n_unmatched:>8,}  "
            f"PLAID_cov={cov_pct:5.2f}%  dt={time.time()-t:4.1f}s"
        )

    # --- Materialise the three edge-list parquets ---
    def to_df(acc: dict, value_col: str, stratum: str | None = None,
              stratum_value: str | None = None) -> pd.DataFrame:
        rows = [
            {"year": y, "source": s, "target": t, value_col: v}
            for (y, s, t), v in acc.items()
        ]
        out = pd.DataFrame.from_records(rows)
        if stratum:
            out[stratum] = stratum_value
        return out

    # BEC
    parts = []
    for col in bec_cols:
        stage = col.replace("bec_share_", "")
        parts.append(to_df(acc_bec[col], "value_kusd", stratum="bec_stage", stratum_value=stage))
    bec_edges = pd.concat(parts, ignore_index=True)
    bec_edges["value_busd"] = bec_edges["value_kusd"] / 1_000_000
    bec_edges = bec_edges[["year","source","target","bec_stage","value_kusd","value_busd"]]
    bec_edges.to_parquet(OUT_BEC, compression="snappy", index=False)
    print(f"[BEC]   {len(bec_edges):,} rows → {OUT_BEC.name}")

    # Rauch
    parts = []
    rauch_label = {"rauch_share_w": "differentiated",
                   "rauch_share_r": "reference",
                   "rauch_share_n": "homogeneous"}
    for col in rauch_cols:
        parts.append(to_df(acc_rauch[col], "value_kusd", stratum="rauch_class",
                           stratum_value=rauch_label[col]))
    rau_edges = pd.concat(parts, ignore_index=True)
    rau_edges["value_busd"] = rau_edges["value_kusd"] / 1_000_000
    rau_edges = rau_edges[["year","source","target","rauch_class","value_kusd","value_busd"]]
    rau_edges.to_parquet(OUT_RAUCH, compression="snappy", index=False)
    print(f"[Rauch] {len(rau_edges):,} rows → {OUT_RAUCH.name}")

    # Microchip
    parts = [
        to_df(acc_chip,      "value_kusd", stratum="microchip", stratum_value="microchip"),
        to_df(acc_chip_comp, "value_kusd", stratum="microchip", stratum_value="non_microchip"),
    ]
    mc_edges = pd.concat(parts, ignore_index=True)
    mc_edges["value_busd"] = mc_edges["value_kusd"] / 1_000_000
    mc_edges = mc_edges[["year","source","target","microchip","value_kusd","value_busd"]]
    mc_edges.to_parquet(OUT_MICROCHIP, compression="snappy", index=False)
    print(f"[Chip]  {len(mc_edges):,} rows → {OUT_MICROCHIP.name}")

    print(f"[total] {time.time()-t_total:.1f}s")


if __name__ == "__main__":
    main()
