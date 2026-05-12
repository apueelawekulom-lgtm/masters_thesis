"""
Integrate the FGKK-style US-on-China tariff data into the product-level master.

Source: Tariffs US:CHina/z_usch_w.dta  (US tariffs on Chinese imports, FGKK 2023).
        Structure: 4,726 HS6 × 3 periods (t = -1, 0, 1).
        t = -1: pre-period baseline; t = 1: post-trade-war realised tariff.

Variables (per FGKK 2023):
  z_usch       : simple statutory rate (level)
  z_usch_w     : weight-collapsed rate (pre-war flow-weighted across HS10)
  z_usch_max   : maximum stacked rate (when multiple Lists overlap)
  dz_usch_w    : change vs pre-period (= z_usch_w(t=1) − z_usch_w(t=-1))
  dlz_usch_w   : log-change (≈ ln(1+τ_post) − ln(1+τ_pre))

Outputs in BACI_HS92_V202601/:
  hs6_tariff_master.csv   one row per HS6 with post-period tariff exposure
  hs4_tariff_master.csv   HS4-level aggregation (mean of HS6 within chapter)
  hs4_master.csv          PLAID master + HS4 tariff exposure (merged)

The tariff exposure can then be merged onto BACI HS6 product codes to flag
treated products in the network analysis.

Caveat: BACI uses HS92, FGKK uses the HS revision current at the time of
tariff implementation (likely HS17). Same HS6 mismatch as PLAID — we accept
~0.5% loss and aggregate to HS4 for analyses that need full coverage.
"""

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent
BACI_DIR = ROOT / "BACI_HS92_V202601"
TARIFFS = ROOT / "Tariffs US:CHina/z_usch_w.dta"
PLAID_MASTER = BACI_DIR / "hs4_plaid_master.csv"


def main() -> None:
    # 1. Load and reshape
    raw = pd.read_stata(TARIFFS)
    print(f"[load] {TARIFFS.name}  rows={len(raw):,}  hs6={raw['hs6'].nunique():,}  "
          f"periods={sorted(raw['t'].unique())}")

    # Pad HS6 to 6-digit zero-padded string for consistency with BACI/PLAID
    raw["hs6"] = raw["hs6"].astype(int).astype(str).str.zfill(6)

    # Take post-period (t=1) tariff levels as the realised "treatment intensity"
    post = raw[raw["t"] == 1].set_index("hs6")
    pre  = raw[raw["t"] == -1].set_index("hs6")

    hs6_master = pd.DataFrame(index=post.index)
    hs6_master["tariff_post_w"]   = post["z_usch_w"]
    hs6_master["tariff_post"]     = post["z_usch"]
    hs6_master["tariff_post_max"] = post["z_usch_max"]
    hs6_master["tariff_change_w"] = post["dz_usch_w"]
    hs6_master["tariff_change_max"] = post["dz_usch_max"]
    hs6_master["tariff_pre_w"]    = pre["z_usch_w"]
    hs6_master["any_tariff"]      = (hs6_master["tariff_post_w"] > 0).astype(int)
    hs6_master["treated"]         = (hs6_master["tariff_change_w"] > 0).astype(int)
    # Tariff exposure category (post-period weighted)
    hs6_master["tariff_bucket"] = pd.cut(
        hs6_master["tariff_post_w"],
        bins=[-0.001, 0.0, 0.075, 0.175, 1.0],
        labels=["none", "low_0_7.5", "mid_7.5_17.5", "high_17.5+"],
    )
    hs6_master["hs4"] = hs6_master.index.str[:4]
    hs6_master.reset_index(inplace=True)

    out_hs6 = BACI_DIR / "hs6_tariff_master.csv"
    hs6_master.to_csv(out_hs6, index=False)
    print(f"  → {out_hs6.name}  ({len(hs6_master):,} HS6)")

    # 2. HS4 aggregation (mean across HS6 children in the FGKK universe)
    hs4 = hs6_master.groupby("hs4").agg(
        tariff_post_w_mean   =("tariff_post_w",   "mean"),
        tariff_post_w_max    =("tariff_post_w",   "max"),
        tariff_post_max_mean =("tariff_post_max", "mean"),
        tariff_change_w_mean =("tariff_change_w", "mean"),
        treated_share        =("treated",         "mean"),
        n_hs6_fgkk           =("hs6",             "size"),
    ).reset_index()
    out_hs4 = BACI_DIR / "hs4_tariff_master.csv"
    hs4.to_csv(out_hs4, index=False)
    print(f"  → {out_hs4.name}  ({len(hs4):,} HS4 with any FGKK coverage)")

    # 3. Merge with hs4_plaid_master.csv → unified product master
    plaid = pd.read_csv(PLAID_MASTER, dtype={"hs4": str})
    plaid["hs4"] = plaid["hs4"].str.zfill(4)
    hs4["hs4"]   = hs4["hs4"].str.zfill(4)
    master = plaid.merge(hs4, on="hs4", how="left")
    master["tariff_post_w_mean"]   = master["tariff_post_w_mean"].fillna(0)
    master["tariff_post_w_max"]    = master["tariff_post_w_max"].fillna(0)
    master["tariff_post_max_mean"] = master["tariff_post_max_mean"].fillna(0)
    master["tariff_change_w_mean"] = master["tariff_change_w_mean"].fillna(0)
    master["treated_share"]        = master["treated_share"].fillna(0)
    master["n_hs6_fgkk"]           = master["n_hs6_fgkk"].fillna(0).astype(int)
    out_master = BACI_DIR / "hs4_master.csv"
    master.to_csv(out_master, index=False)
    print(f"  → {out_master.name}  ({len(master):,} HS4 chapters with PLAID + tariffs)")

    # 4. Sanity reports
    print("\n=== HS4 tariff exposure summary ===")
    print(f"  HS4 chapters with any treated HS6 child: {(master['treated_share']>0).sum()} of {len(master)}")
    print(f"  HS4 chapters with mean post-tariff > 10%: {(master['tariff_post_w_mean']>0.10).sum()}")
    print(f"  HS4 chapters with max stacked tariff > 25%: {(master['tariff_post_w_max']>0.25).sum()}")

    print("\n=== Tariff bucket distribution at HS6 level (FGKK universe only) ===")
    print(hs6_master["tariff_bucket"].value_counts(dropna=False).sort_index())


if __name__ == "__main__":
    main()
