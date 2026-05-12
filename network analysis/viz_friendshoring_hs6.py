"""
Simple friend-shoring analysis at HS6 level, comparing the aggregate diversion
view against a BEC-stratified view (consumption / intermediate / capital).

Question: When the US tariffs Chinese products, do US imports of those products
shift away from China? And does the source-country shift differ across BEC stages?

Universe: HS6 codes that BOTH (a) appear in FGKK as tariffed (z_usch_w > 0) AND
          (b) have a PLAID BEC classification at HS6.
          Same flows used for aggregate and stage-stratified views.

Outputs (figures/):
  fig11_friendshoring_aggregate_vs_bec.png
  fig12_connector_intermediate_source_mix.png
  + console summary table
"""

from pathlib import Path

import pandas as pd
import pyarrow.dataset as ds
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator

ROOT = Path(__file__).parent
BACI_DIR = ROOT / "BACI_HS92_V202601"
PLAID_DIR = ROOT / "PLAID Indicator"
FIG_DIR = ROOT / "figures"
FIG_DIR.mkdir(exist_ok=True)

# Connector watchlist for the "rising suppliers to US" hypothesis
KEY_SOURCES = ["CHN", "MEX", "VNM", "S19", "KOR", "IND", "MYS", "THA", "DEU", "JPN"]
SOURCE_COLOR = {
    "CHN": "#c10000",  # red — the displaced incumbent
    "MEX": "#1f77b4",  # blue
    "VNM": "#ff7f0e",  # orange
    "S19": "#9467bd",  # purple (Taiwan)
    "KOR": "#2ca02c",  # green
    "IND": "#8c564b",  # brown
    "MYS": "#e377c2",  # pink
    "THA": "#7f7f7f",  # grey
    "DEU": "#17becf",  # cyan
    "JPN": "#bcbd22",  # olive
    "Other": "#cccccc",
}
WINDOW = (2010, 2024)
TRADE_WAR = (2018, 2019)

plt.rcParams.update({
    "figure.dpi": 110, "savefig.dpi": 200, "font.size": 10,
    "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False,
})


def load_hs6_bec() -> dict[str, str]:
    p = pd.read_csv(PLAID_DIR / "PLAID_v0.1_bec_H6.csv", dtype={"hs6_code": str})
    p["hs6"] = p["hs6_code"].str.zfill(6)
    return dict(zip(p["hs6"], p["bec"]))


def load_tariffed_hs6() -> set[str]:
    tar = pd.read_csv(BACI_DIR / "hs6_tariff_master.csv", dtype={"hs6": str})
    tar["hs6"] = tar["hs6"].str.zfill(6)
    return set(tar.loc[tar["tariff_post_w"] > 0, "hs6"])


def load_us_imports_panel() -> pd.DataFrame:
    """For each year in window, USA-as-importer flows with HS6, source, value."""
    hs6_bec    = load_hs6_bec()
    tariffed   = load_tariffed_hs6()
    dset       = ds.dataset(BACI_DIR / "baci_combined.parquet", format="parquet")

    parts = []
    for yr in range(WINDOW[0], WINDOW[1] + 1):
        tbl = dset.to_table(
            columns=["t","k","v","iso3_exporter","iso3_importer"],
            filter=(ds.field("t") == yr) & (ds.field("iso3_importer") == "USA"),
        )
        df = tbl.to_pandas()
        df["bec"]     = df["k"].map(hs6_bec)
        df["is_tar"]  = df["k"].isin(tariffed)
        df["year"]    = yr
        df["v_busd"]  = df["v"] / 1_000_000  # USD thousands → USD billions
        parts.append(df)
    out = pd.concat(parts, ignore_index=True)
    print(f"[load] US-import rows: {len(out):,}")
    return out


def source_shares(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    """Compute % shares per group, with sources outside KEY_SOURCES collapsed to 'Other'."""
    df = df.copy()
    df["src"] = df["iso3_exporter"].where(
        df["iso3_exporter"].isin(KEY_SOURCES), "Other"
    )
    g = df.groupby(group_cols + ["src"], observed=True)["v_busd"].sum().reset_index()
    tot = df.groupby(group_cols, observed=True)["v_busd"].sum().reset_index().rename(
        columns={"v_busd":"total_busd"})
    g = g.merge(tot, on=group_cols)
    g["share_pct"] = 100 * g["v_busd"] / g["total_busd"]
    return g


def plot_stacked(ax, df_grp: pd.DataFrame, title: str):
    """Stacked area plot of source-country shares over time."""
    sources_order = KEY_SOURCES + ["Other"]
    piv = df_grp.pivot_table(index="year", columns="src", values="share_pct",
                             fill_value=0).reindex(columns=sources_order, fill_value=0)
    ax.stackplot(piv.index, piv.T.values,
                 labels=piv.columns,
                 colors=[SOURCE_COLOR[s] for s in piv.columns],
                 alpha=0.92)
    ax.set_xlim(WINDOW[0]-0.3, WINDOW[1]+0.3)
    ax.set_ylim(0, 100)
    ax.set_xlabel("Year"); ax.set_ylabel("Share of US imports (%)")
    ax.set_title(title, loc="left", fontweight="bold")
    ax.axvspan(*TRADE_WAR, color="#ffa500", alpha=0.25, zorder=10)
    ax.axvline(2020, color="white", ls=":", lw=1.0, alpha=0.7)
    ax.xaxis.set_major_locator(MultipleLocator(2))
    ax.grid(axis="y", alpha=0.18, lw=0.5, color="white")


def fig11_aggregate_vs_bec(us: pd.DataFrame):
    """4-panel: aggregate vs 3 BEC stages — US imports of TARIFFED products."""
    tar = us[us["is_tar"] & us["bec"].notna()].copy()
    print(f"[fig11] tariffed × has-BEC rows: {len(tar):,} "
          f"(value covered: ${tar['v_busd'].sum():.0f}B)")

    fig, axes = plt.subplots(2, 2, figsize=(15, 9.5))

    # Aggregate (across BEC stages)
    g_all = source_shares(tar, ["year"])
    plot_stacked(axes[0, 0], g_all, "Aggregate — US imports of tariffed products")

    # By BEC stage
    g_bec = source_shares(tar, ["year","bec"])
    for ax, stage in [(axes[0, 1], "consumption"),
                      (axes[1, 0], "intermediate"),
                      (axes[1, 1], "capital")]:
        sub = g_bec[g_bec["bec"] == stage]
        plot_stacked(ax, sub, f"{stage.capitalize()} stage")

    h, l = axes[0, 0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=6, bbox_to_anchor=(0.5, -0.02),
               fontsize=9.5)
    fig.suptitle(
        "Friend-shoring of US imports of tariffed products — aggregate vs BEC stages\n"
        "(Same product universe in all four panels)",
        fontsize=13, fontweight="bold", y=0.995
    )
    fig.tight_layout(rect=[0, 0.025, 1, 0.97])
    out = FIG_DIR / "fig11_friendshoring_aggregate_vs_bec.png"
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  → {out.relative_to(ROOT)}")


def fig12_connector_intermediates(us_all: pd.DataFrame):
    """For connectors, what's their intermediate-import source mix?
    Uses non-USA-importer BACI flows — but we kept only USA-importer rows above.
    So we need to load a different filter: importer in CONNECTOR set."""
    hs6_bec = load_hs6_bec()
    tariffed = load_tariffed_hs6()
    dset = ds.dataset(BACI_DIR / "baci_combined.parquet", format="parquet")

    connectors = ["VNM", "MEX"]
    fig, axes = plt.subplots(1, 2, figsize=(15, 5.2))
    for ax, importer in zip(axes, connectors):
        parts = []
        for yr in range(WINDOW[0], WINDOW[1] + 1):
            tbl = dset.to_table(
                columns=["t","k","v","iso3_exporter","iso3_importer"],
                filter=(ds.field("t") == yr) & (ds.field("iso3_importer") == importer),
            )
            df = tbl.to_pandas()
            df["bec"]   = df["k"].map(hs6_bec)
            df["is_tar"] = df["k"].isin(tariffed)
            df["year"]  = yr
            df["v_busd"]= df["v"] / 1_000_000
            parts.append(df)
        flows = pd.concat(parts, ignore_index=True)
        # Filter: intermediate-stage imports of tariff-targeted products
        sub = flows[flows["is_tar"] & (flows["bec"] == "intermediate")].copy()
        g = source_shares(sub, ["year"])
        plot_stacked(ax, g, f"{importer} — intermediate imports of tariffed products")
        ax.set_ylabel(f"Share of {importer}'s intermediate imports (%)")

    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=6, bbox_to_anchor=(0.5, -0.02), fontsize=9.5)
    fig.suptitle(
        "Connector countries' source mix of intermediate imports in tariffed-product chapters\n"
        "(Rising China share = transshipment-flavoured; falling China share = relocation-flavoured)",
        fontsize=13, fontweight="bold", y=0.995
    )
    fig.tight_layout(rect=[0, 0.04, 1, 0.97])
    out = FIG_DIR / "fig12_connector_intermediate_source_mix.png"
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  → {out.relative_to(ROOT)}")


def summary_table(us: pd.DataFrame):
    """Print share comparison: 2017 vs 2024, aggregate vs by BEC stage."""
    tar = us[us["is_tar"] & us["bec"].notna()].copy()
    tar["src"] = tar["iso3_exporter"].where(tar["iso3_exporter"].isin(KEY_SOURCES), "Other")

    print("\n" + "="*78)
    print(" Source-country share of US imports of TARIFFED products: 2017 vs 2024")
    print("="*78)

    def shares_for(df_sub, label):
        g = df_sub.groupby(["year","src"])["v_busd"].sum().reset_index()
        tot = df_sub.groupby("year")["v_busd"].sum().reset_index().rename(
            columns={"v_busd":"total"})
        g = g.merge(tot, on="year")
        g["pct"] = 100 * g["v_busd"] / g["total"]
        piv = g.pivot(index="src", columns="year", values="pct").reindex(
            index=KEY_SOURCES + ["Other"], fill_value=0)
        piv["Δ 2017→2024"] = piv[2024] - piv[2017]
        print(f"\n{label}  ({df_sub['v_busd'].sum()/(2024-2010+1):.0f} B avg/yr)")
        print(piv[[2017, 2018, 2019, 2020, 2024, "Δ 2017→2024"]].round(2).to_string())

    shares_for(tar, "AGGREGATE (all tariffed products with PLAID BEC)")
    for stage in ["consumption", "intermediate", "capital"]:
        shares_for(tar[tar["bec"] == stage], f"BEC stage = {stage}")


def main():
    us = load_us_imports_panel()
    summary_table(us)
    print("\n[plot] →")
    fig11_aggregate_vs_bec(us)
    fig12_connector_intermediates(us)


if __name__ == "__main__":
    main()
