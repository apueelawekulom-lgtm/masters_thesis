"""
Tables for the friend-shoring argument:

Table 1: US imports of tariffed products by source country and BEC stage —
         2017 baseline, 2024 latest, % shares and absolute $ values, Δ for both.

Table 2: Connector countries' (VNM, MEX) intermediate-import source mix in
         tariffed-product chapters — the transshipment-vs-relocation discriminator.

Outputs:
  console pretty-print
  tables/friendshoring_us_imports.csv
  tables/friendshoring_connector_sources.csv
"""

from pathlib import Path

import pandas as pd
import pyarrow.dataset as ds

ROOT = Path(__file__).parent
BACI_DIR = ROOT / "BACI_HS92_V202601"
PLAID_DIR = ROOT / "PLAID Indicator"
TABLE_DIR = ROOT / "tables"
TABLE_DIR.mkdir(exist_ok=True)

KEY_SOURCES = ["CHN", "MEX", "VNM", "S19", "KOR", "JPN", "DEU", "IND",
               "MYS", "THA", "BRA", "GBR", "CAN", "FRA", "NLD", "IDN"]


def load_hs6_bec() -> dict[str, str]:
    p = pd.read_csv(PLAID_DIR / "PLAID_v0.1_bec_H6.csv", dtype={"hs6_code": str})
    p["hs6"] = p["hs6_code"].str.zfill(6)
    return dict(zip(p["hs6"], p["bec"]))


def load_tariffed_hs6() -> set[str]:
    tar = pd.read_csv(BACI_DIR / "hs6_tariff_master.csv", dtype={"hs6": str})
    tar["hs6"] = tar["hs6"].str.zfill(6)
    return set(tar.loc[tar["tariff_post_w"] > 0, "hs6"])


def load_filtered_flows(importer: str, years: list[int]) -> pd.DataFrame:
    hs6_bec = load_hs6_bec()
    tariffed = load_tariffed_hs6()
    dset = ds.dataset(BACI_DIR / "baci_combined.parquet", format="parquet")
    parts = []
    for yr in years:
        tbl = dset.to_table(
            columns=["t","k","v","iso3_exporter","iso3_importer"],
            filter=(ds.field("t") == yr) & (ds.field("iso3_importer") == importer),
        )
        df = tbl.to_pandas()
        df["bec"]     = df["k"].map(hs6_bec)
        df["is_tar"]  = df["k"].isin(tariffed)
        df["v_busd"]  = df["v"] / 1_000_000
        df["year"]    = yr
        parts.append(df)
    return pd.concat(parts, ignore_index=True)


def table_us_imports() -> pd.DataFrame:
    flows = load_filtered_flows("USA", [2017, 2024])
    sub = flows[flows["is_tar"] & flows["bec"].notna()].copy()
    sub["src"] = sub["iso3_exporter"].where(sub["iso3_exporter"].isin(KEY_SOURCES), "Other")

    def by_stage(stage: str | None) -> pd.DataFrame:
        d = sub if stage is None else sub[sub["bec"] == stage]
        g = d.groupby(["year","src"])["v_busd"].sum().reset_index()
        tot = d.groupby("year")["v_busd"].sum().reset_index().rename(columns={"v_busd":"total"})
        g = g.merge(tot, on="year")
        g["pct"] = 100 * g["v_busd"] / g["total"]
        wide_pct = g.pivot(index="src", columns="year", values="pct").fillna(0)
        wide_val = g.pivot(index="src", columns="year", values="v_busd").fillna(0)
        out = pd.DataFrame({
            "share_2017_pct":  wide_pct[2017],
            "share_2024_pct":  wide_pct[2024],
            "delta_pp":        wide_pct[2024] - wide_pct[2017],
            "value_2017_busd": wide_val[2017],
            "value_2024_busd": wide_val[2024],
            "delta_busd":      wide_val[2024] - wide_val[2017],
            "delta_pct":       100 * (wide_val[2024] - wide_val[2017]) / wide_val[2017].replace(0, float("nan")),
        }).reindex(index=KEY_SOURCES + ["Other"])
        out["stage"] = stage or "AGGREGATE"
        out = out.reset_index().rename(columns={"src": "source"})
        return out

    parts = [by_stage(None)] + [by_stage(s) for s in ["consumption","intermediate","capital"]]
    tbl = pd.concat(parts, ignore_index=True)
    tbl = tbl[["stage","source","share_2017_pct","share_2024_pct","delta_pp",
               "value_2017_busd","value_2024_busd","delta_busd","delta_pct"]]
    return tbl


def table_connector_intermediates() -> pd.DataFrame:
    rows = []
    for connector in ["VNM", "MEX"]:
        flows = load_filtered_flows(connector, [2017, 2024])
        sub = flows[flows["is_tar"] & (flows["bec"] == "intermediate")].copy()
        sub["src"] = sub["iso3_exporter"].where(sub["iso3_exporter"].isin(KEY_SOURCES), "Other")
        g = sub.groupby(["year","src"])["v_busd"].sum().reset_index()
        tot = sub.groupby("year")["v_busd"].sum().reset_index().rename(columns={"v_busd":"total"})
        g = g.merge(tot, on="year")
        g["pct"] = 100 * g["v_busd"] / g["total"]
        wide_pct = g.pivot(index="src", columns="year", values="pct").fillna(0)
        wide_val = g.pivot(index="src", columns="year", values="v_busd").fillna(0)
        out = pd.DataFrame({
            "connector":        connector,
            "share_2017_pct":   wide_pct[2017],
            "share_2024_pct":   wide_pct[2024],
            "delta_pp":         wide_pct[2024] - wide_pct[2017],
            "value_2017_busd":  wide_val[2017],
            "value_2024_busd":  wide_val[2024],
            "delta_busd":       wide_val[2024] - wide_val[2017],
            "delta_pct":        100*(wide_val[2024]-wide_val[2017]) / wide_val[2017].replace(0, float("nan")),
        }).reindex(index=KEY_SOURCES + ["Other"]).reset_index().rename(columns={"src":"source"})
        rows.append(out)
    return pd.concat(rows, ignore_index=True)


def pretty(df: pd.DataFrame, value_fmt: dict | None = None) -> str:
    """Format float columns nicely for console output."""
    fmt = {
        "share_2017_pct":  "{:>6.2f}",
        "share_2024_pct":  "{:>6.2f}",
        "delta_pp":        "{:>+6.2f}",
        "value_2017_busd": "{:>9.1f}",
        "value_2024_busd": "{:>9.1f}",
        "delta_busd":      "{:>+9.1f}",
        "delta_pct":       "{:>+7.1f}",
    }
    if value_fmt:
        fmt.update(value_fmt)
    d = df.copy()
    for c, f in fmt.items():
        if c in d.columns:
            d[c] = d[c].map(lambda v: f.format(v) if pd.notna(v) else "      —")
    return d.to_string(index=False)


def main():
    t1 = table_us_imports()
    t2 = table_connector_intermediates()

    out1 = TABLE_DIR / "friendshoring_us_imports.csv"
    out2 = TABLE_DIR / "friendshoring_connector_sources.csv"
    t1.to_csv(out1, index=False, float_format="%.4f")
    t2.to_csv(out2, index=False, float_format="%.4f")

    print("\n" + "="*100)
    print(" TABLE 1 — US imports of TARIFFED products: source-country shares & values, 2017→2024")
    print(" (Universe: tariffed HS6 with PLAID BEC at HS6)")
    print("="*100)
    for stage in ["AGGREGATE","consumption","intermediate","capital"]:
        sub = t1[t1["stage"] == stage].drop(columns="stage")
        total_val = sub["value_2017_busd"].sum()
        total_24  = sub["value_2024_busd"].sum()
        print(f"\n--- {stage}  (2017 total ${total_val:.0f}B → 2024 total ${total_24:.0f}B) ---")
        print(pretty(sub.sort_values("delta_pp", ascending=False)))

    print("\n" + "="*100)
    print(" TABLE 2 — Connector intermediate-import source mix (tariffed-product chapters)")
    print(" (Discriminator: rising China share → transshipment; falling China share → relocation)")
    print("="*100)
    for conn in ["VNM", "MEX"]:
        sub = t2[t2["connector"] == conn].drop(columns="connector")
        total_val = sub["value_2017_busd"].sum()
        total_24  = sub["value_2024_busd"].sum()
        print(f"\n--- {conn}  (2017 ${total_val:.1f}B → 2024 ${total_24:.1f}B intermediate imports) ---")
        print(pretty(sub.sort_values("delta_pp", ascending=False)))

    print(f"\n[saved]  {out1.relative_to(ROOT)}  {out2.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
