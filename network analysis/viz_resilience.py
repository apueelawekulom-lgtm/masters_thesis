"""
Visualise aggregate network resilience.

Figures:
  fig13_resilience_metrics.png       λ₂, max k-core, top-shell size, bridges over time
  fig14_attack_robustness.png        attack-decay curves at snapshot years
  fig15_kcore_evolution.png          watchlist countries' k-core membership over time
  fig16_backbone_comparison.png      backbone edge counts + top edges 2017 vs 2024
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

WINDOW = (1995, 2024)
TRADE_WAR = (2018, 2019)
COVID = 2020

plt.rcParams.update({
    "figure.dpi": 110, "savefig.dpi": 200, "font.size": 10,
    "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False,
})


def shade(ax, x0=WINDOW[0], x1=WINDOW[1]):
    if x0 <= 2008 <= x1:
        ax.axvspan(2008, 2009, color="#888888", alpha=0.10)
    if x0 <= TRADE_WAR[0] <= x1:
        ax.axvspan(*TRADE_WAR, color="#ffa500", alpha=0.18)
    if x0 <= COVID <= x1:
        ax.axvline(COVID, color="#999999", ls=":", lw=0.8, alpha=0.6)


def fig13_metrics():
    df = pd.read_csv(BACI_DIR / "resilience_global_metrics.csv")
    fig, axes = plt.subplots(2, 2, figsize=(13, 8.5))

    ax = axes[0, 0]
    ax.plot(df.year, df.lambda2, color="#1f77b4", lw=2.2)
    ax.set_title("Algebraic connectivity (λ₂)  — higher = harder to disconnect",
                 loc="left", fontweight="bold")
    ax.set_xlabel("Year"); ax.set_ylabel("λ₂")
    shade(ax); ax.grid(axis="y", alpha=0.25, lw=0.5)
    ax.xaxis.set_major_locator(MultipleLocator(5))

    ax = axes[0, 1]
    ax.plot(df.year, df.max_k_core, color="#d62728", lw=2.2)
    ax.set_title("Max k-core — depth of the densest backbone",
                 loc="left", fontweight="bold")
    ax.set_xlabel("Year"); ax.set_ylabel("max k")
    shade(ax); ax.grid(axis="y", alpha=0.25, lw=0.5)
    ax.xaxis.set_major_locator(MultipleLocator(5))

    ax = axes[1, 0]
    ax.plot(df.year, df.top_kshell_size, color="#2ca02c", lw=2.2)
    ax.set_title("Top k-shell membership — countries in the innermost core",
                 loc="left", fontweight="bold")
    ax.set_xlabel("Year"); ax.set_ylabel("# countries")
    shade(ax); ax.grid(axis="y", alpha=0.25, lw=0.5)
    ax.xaxis.set_major_locator(MultipleLocator(5))

    ax = axes[1, 1]
    ax.plot(df.year, df.n_bridges, color="#9467bd", lw=2.2)
    ax.set_title("Bridge edges — single-point-of-failure links",
                 loc="left", fontweight="bold")
    ax.set_xlabel("Year"); ax.set_ylabel("# bridges (lower = more redundant)")
    shade(ax); ax.grid(axis="y", alpha=0.25, lw=0.5)
    ax.xaxis.set_major_locator(MultipleLocator(5))

    fig.suptitle(
        "Network resilience metrics, 1995–2024 (edges ≥ $50M, symmetrised)",
        fontsize=13, fontweight="bold", y=0.995
    )
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    out = FIG_DIR / "fig13_resilience_metrics.png"
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  → {out.relative_to(ROOT)}")


def fig14_attack():
    df = pd.read_csv(BACI_DIR / "resilience_attack_curves.csv")
    years = sorted(df.year.unique())
    colors = {2008: "#888888", 2017: "#1f77b4", 2019: "#ff7f0e",
              2021: "#9467bd", 2024: "#c10000"}
    fig, ax = plt.subplots(figsize=(10, 6.5))
    for yr in years:
        sub = df[df.year == yr].sort_values("k_removed")
        ax.plot(sub.k_removed, sub.gc_frac, color=colors.get(yr, "#666666"),
                lw=2.4, label=str(int(yr)), marker="o", markersize=4)
    ax.set_title(
        "Targeted-attack robustness — giant component fraction vs hubs removed\n"
        "Curves that fall faster = network more vulnerable to losing top exporters",
        loc="left", fontweight="bold"
    )
    ax.set_xlabel("# of top-out-strength countries removed")
    ax.set_ylabel("Giant component / total nodes")
    ax.legend(title="Year", loc="lower left")
    ax.grid(axis="y", alpha=0.25, lw=0.5)
    ax.set_xlim(-0.5, df.k_removed.max() + 0.5)
    ax.set_ylim(0, 1.02)
    fig.tight_layout()
    out = FIG_DIR / "fig14_attack_robustness.png"
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  → {out.relative_to(ROOT)}")


def fig15_kcore_evolution():
    """Watchlist countries' core-number trajectory over time."""
    df = pd.read_csv(BACI_DIR / "resilience_kcore_members.csv")
    watchlist = ["CHN","USA","DEU","JPN","KOR","S19","VNM","MEX","IND",
                 "FRA","NLD","GBR","CAN","BRA","AUS","MYS","THA"]
    piv = df[df.country.isin(watchlist)].pivot_table(
        index="country", columns="year", values="core_number", fill_value=0)
    piv = piv.reindex(index=watchlist)

    fig, ax = plt.subplots(figsize=(15, 6.5))
    im = ax.imshow(piv.values, aspect="auto", cmap="viridis")
    ax.set_yticks(range(len(piv.index))); ax.set_yticklabels(piv.index)
    years = piv.columns
    every = 3
    ax.set_xticks(range(0, len(years), every))
    ax.set_xticklabels([str(int(y)) for y in years[::every]])
    fig.colorbar(im, ax=ax, label="k-core number (higher = deeper in backbone)",
                 shrink=0.85)
    ax.set_title(
        "Watchlist countries' k-core trajectory, 1995–2024\n"
        "Cells coloured by depth of country's k-core position; brighter = deeper in backbone",
        loc="left", fontweight="bold"
    )
    fig.tight_layout()
    out = FIG_DIR / "fig15_kcore_evolution.png"
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  → {out.relative_to(ROOT)}")


def fig16_backbone_compare():
    """Compare disparity-filter backbones across snapshot years."""
    snapshot_years = [2008, 2017, 2019, 2021, 2024]
    backbones = {yr: pd.read_csv(BACI_DIR / f"resilience_backbone_{yr}.csv")
                 for yr in snapshot_years}

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    # Left: backbone edge count over snapshots
    ax = axes[0]
    counts = [len(backbones[y]) for y in snapshot_years]
    weights = [backbones[y]["weight_busd"].sum() for y in snapshot_years]
    ax.bar([str(y) for y in snapshot_years], counts, color="#1f77b4", alpha=0.7)
    ax.set_title("# of statistically significant backbone edges per snapshot year",
                 loc="left", fontweight="bold")
    ax.set_ylabel("# edges (disparity filter, α=0.01)")
    ax.grid(axis="y", alpha=0.25, lw=0.5)
    for x, c, w in zip(range(len(snapshot_years)), counts, weights):
        ax.text(x, c + 5, f"${w/1000:.1f}T",
                ha="center", fontsize=9, fontweight="bold", color="#555555")

    # Right: top 15 edges by weight in 2024 with their 2017 weight
    bb_24 = backbones[2024].copy()
    bb_24["pair"] = bb_24["source"] + "↔" + bb_24["target"]
    bb_17 = backbones[2017].copy()
    bb_17["pair"] = bb_17["source"] + "↔" + bb_17["target"]
    top_24 = bb_24.nlargest(15, "weight_busd").set_index("pair")
    # Merge 2017 values where present
    weights_17 = bb_17.set_index("pair")["weight_busd"]
    top_24["weight_2017"] = top_24.index.map(weights_17).fillna(0)

    ax = axes[1]
    y = np.arange(len(top_24))[::-1]
    ax.barh(y - 0.18, top_24["weight_busd"].values, height=0.36,
            color="#c10000", label="2024", alpha=0.85)
    ax.barh(y + 0.18, top_24["weight_2017"].values, height=0.36,
            color="#1f77b4", label="2017", alpha=0.85)
    ax.set_yticks(y); ax.set_yticklabels(top_24.index, fontsize=9)
    ax.set_xlabel("Bilateral flow (USD bn, both directions summed)")
    ax.set_title("Top 15 backbone edges in 2024 — and their 2017 weight",
                 loc="left", fontweight="bold")
    ax.legend(loc="lower right")
    ax.grid(axis="x", alpha=0.25, lw=0.5)

    fig.suptitle(
        "Disparity-filter backbone: the load-bearing edges of the trade network",
        fontsize=13, fontweight="bold", y=0.995
    )
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    out = FIG_DIR / "fig16_backbone_comparison.png"
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  → {out.relative_to(ROOT)}")


def main():
    print("[plot] →")
    fig13_metrics()
    fig14_attack()
    fig15_kcore_evolution()
    fig16_backbone_compare()


if __name__ == "__main__":
    main()
