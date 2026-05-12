"""
Visualise how networks differ across tariff strata.

Caveat: 'treated' tags all global trade in HS6 codes that received US Section 301
tariffs. So the network captures these products' bilateral flows worldwide —
NOT specifically US-from-China flows. This means China's 'treated' subnetwork
share captures China's exports of tariffed products to ALL destinations
(including redirected non-US exports), not US imports of tariffed Chinese goods.

Two figures in figures/:
  fig9_tariff_stratum_metrics.png   Density, modularity, HHI, Jaccard over time
  fig10_tariff_country_panels.png   CHN share, VNM/MEX/S19 PageRank by stratum
"""

from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator

ROOT = Path(__file__).parent
BACI_DIR = ROOT / "BACI_HS92_V202601"
FIG_DIR = ROOT / "figures"
FIG_DIR.mkdir(exist_ok=True)

plt.rcParams.update({
    "figure.dpi": 110, "savefig.dpi": 200, "font.size": 10,
    "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False,
})

# Tariff-bucket palette: ramp from light (low) to dark (high)
STRATUM_STYLE = {
    "aggregate":     dict(color="#222222", lw=2.4, ls="--", label="Aggregate"),
    "untreated":     dict(color="#1f77b4", lw=2.0, ls="-",  label="Untreated (0% tariff)"),
    "low":           dict(color="#ffbf66", lw=1.8, ls="-",  label="Low tariff (0–7.5%)"),
    "mid":           dict(color="#e6772a", lw=2.0, ls="-",  label="Mid tariff (7.5–17.5%)"),
    "high":          dict(color="#c10000", lw=2.4, ls="-",  label="High tariff (>17.5%)"),
}
STRATA = ["aggregate","untreated","low","mid","high"]

TRADE_WAR = (2018, 2019)
COVID = 2020
WINDOW = (2010, 2024)

FILE_MAP = {
    "aggregate": "",  # baseline files
    "untreated": "tariff_untreated",
    "low":       "tariff_bucket_low_0_7p5",
    "mid":       "tariff_bucket_mid_7p5_17p5",
    "high":      "tariff_bucket_high_17p5plus",
}


def load_global() -> pd.DataFrame:
    parts = []
    for s, suffix in FILE_MAP.items():
        f = "long_run_global_metrics.csv" if not suffix else f"long_run_global_metrics_{suffix}.csv"
        d = pd.read_csv(BACI_DIR / f)
        d["stratum"] = s
        parts.append(d)
    return pd.concat(parts, ignore_index=True)


def load_country() -> pd.DataFrame:
    parts = []
    for s, suffix in FILE_MAP.items():
        f = "long_run_country_metrics.csv" if not suffix else f"long_run_country_metrics_{suffix}.csv"
        d = pd.read_csv(BACI_DIR / f)
        d["stratum"] = s
        parts.append(d)
    return pd.concat(parts, ignore_index=True)


def shade_shocks(ax):
    ax.axvspan(*TRADE_WAR, color="#ffa500", alpha=0.15)
    ax.axvline(COVID, color="#999999", ls=":", lw=0.8, alpha=0.6)
    ax.text(TRADE_WAR[0] + 0.3, ax.get_ylim()[1],
            "Trade war", fontsize=8, color="#b86200", ha="left", va="top",
            fontweight="bold")


def plot_metric(ax, g: pd.DataFrame, metric: str, ylabel: str, title: str):
    for s in STRATA:
        sub = g[(g.stratum == s) & (g.year.between(*WINDOW))].sort_values("year")
        ax.plot(sub.year, sub[metric], **STRATUM_STYLE[s])
    ax.set_title(title, loc="left", fontweight="bold")
    ax.set_xlabel("Year"); ax.set_ylabel(ylabel)
    ax.set_xlim(WINDOW[0]-0.3, WINDOW[1]+0.3)
    ax.xaxis.set_major_locator(MultipleLocator(2))
    ax.grid(axis="y", alpha=0.25, lw=0.5)
    shade_shocks(ax)


def fig9_metrics(g: pd.DataFrame):
    fig, axes = plt.subplots(2, 2, figsize=(13, 8.5))
    plot_metric(axes[0,0], g, "density",            "Density",   "Network density")
    plot_metric(axes[0,1], g, "modularity_louvain", "Modularity","Modularity (Louvain)")
    plot_metric(axes[1,0], g, "hhi_out_strength",   "HHI",       "Export concentration (HHI)")
    plot_metric(axes[1,1], g, "jaccard_vs_prev",    "Jaccard",   "Edge turnover (Jaccard vs prev year)")
    h, l = axes[0,0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=5, bbox_to_anchor=(0.5, -0.005), fontsize=9.5)
    fig.suptitle("Network structure by tariff stratum, 2010–2024",
                 fontsize=13, fontweight="bold", y=0.995)
    fig.tight_layout(rect=[0, 0.03, 1, 0.97])
    out = FIG_DIR / "fig9_tariff_stratum_metrics.png"
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  → {out.relative_to(ROOT)}")


def country_share_by_stratum(c: pd.DataFrame, g: pd.DataFrame, country: str) -> pd.DataFrame:
    """Share of out-strength per year per stratum."""
    sub = c[c.country == country].merge(
        g[["year","stratum","total_trade_busd"]],
        on=["year","stratum"], how="left")
    sub["share_pct"] = 100 * sub["out_strength_busd"] / sub["total_trade_busd"]
    return sub


def fig10_country_panels(g: pd.DataFrame, c: pd.DataFrame):
    fig, axes = plt.subplots(2, 2, figsize=(13, 8.5))

    # Panel A: China share by stratum
    ax = axes[0,0]
    chn = country_share_by_stratum(c, g, "CHN")
    for s in STRATA:
        sub = chn[(chn.stratum == s) & (chn.year.between(*WINDOW))].sort_values("year")
        ax.plot(sub.year, sub.share_pct, **STRATUM_STYLE[s])
    ax.set_title("China — global export share by tariff stratum",
                 loc="left", fontweight="bold")
    ax.set_xlabel("Year"); ax.set_ylabel("China's export share (%)")
    ax.set_xlim(WINDOW[0]-0.3, WINDOW[1]+0.3)
    ax.xaxis.set_major_locator(MultipleLocator(2))
    ax.grid(axis="y", alpha=0.25, lw=0.5)
    shade_shocks(ax)

    # Panel B: USA share by stratum
    ax = axes[0,1]
    usa = country_share_by_stratum(c, g, "USA")
    for s in STRATA:
        sub = usa[(usa.stratum == s) & (usa.year.between(*WINDOW))].sort_values("year")
        ax.plot(sub.year, sub.share_pct, **STRATUM_STYLE[s])
    ax.set_title("USA — global export share by tariff stratum",
                 loc="left", fontweight="bold")
    ax.set_xlabel("Year"); ax.set_ylabel("USA's export share (%)")
    ax.set_xlim(WINDOW[0]-0.3, WINDOW[1]+0.3)
    ax.xaxis.set_major_locator(MultipleLocator(2))
    ax.grid(axis="y", alpha=0.25, lw=0.5)
    shade_shocks(ax)

    # Panel C: Vietnam PageRank
    ax = axes[1,0]
    for s in STRATA:
        sub = c[(c.country == "VNM") & (c.stratum == s) & (c.year.between(*WINDOW))].sort_values("year")
        ax.plot(sub.year, sub.pagerank, **STRATUM_STYLE[s])
    ax.set_title("Vietnam — PageRank by tariff stratum",
                 loc="left", fontweight="bold")
    ax.set_xlabel("Year"); ax.set_ylabel("PageRank")
    ax.set_xlim(WINDOW[0]-0.3, WINDOW[1]+0.3)
    ax.xaxis.set_major_locator(MultipleLocator(2))
    ax.grid(axis="y", alpha=0.25, lw=0.5)
    shade_shocks(ax)

    # Panel D: Mexico PageRank
    ax = axes[1,1]
    for s in STRATA:
        sub = c[(c.country == "MEX") & (c.stratum == s) & (c.year.between(*WINDOW))].sort_values("year")
        ax.plot(sub.year, sub.pagerank, **STRATUM_STYLE[s])
    ax.set_title("Mexico — PageRank by tariff stratum",
                 loc="left", fontweight="bold")
    ax.set_xlabel("Year"); ax.set_ylabel("PageRank")
    ax.set_xlim(WINDOW[0]-0.3, WINDOW[1]+0.3)
    ax.xaxis.set_major_locator(MultipleLocator(2))
    ax.grid(axis="y", alpha=0.25, lw=0.5)
    shade_shocks(ax)

    h, l = axes[0,0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=5, bbox_to_anchor=(0.5, -0.005), fontsize=9.5)
    fig.suptitle("Country repositioning by tariff stratum, 2010–2024",
                 fontsize=13, fontweight="bold", y=0.995)
    fig.tight_layout(rect=[0, 0.03, 1, 0.97])
    out = FIG_DIR / "fig10_tariff_country_panels.png"
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  → {out.relative_to(ROOT)}")


def main():
    g = load_global()
    c = load_country()
    print(f"[load] global={g.shape}  country={c.shape}")
    print("[plot] →")
    fig9_metrics(g)
    fig10_country_panels(g, c)


if __name__ == "__main__":
    main()
