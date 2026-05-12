"""
Demonstrate the added value of BEC/Rauch/semi stratification vs aggregate trade.

CAVEAT to acknowledge in writeups:
  These are GROSS-FLOW partitions, not value-added decompositions. A flow
  labelled "consumption" (e.g., VNM→USA laptop) embeds intermediates from
  third countries (e.g., Korean chips). We cannot trace value-added with
  BACI alone — that requires input-output tables (TiVA/ICIO).

  What stratification DOES show: where in the value-chain stage policy and
  market shocks are landing, which countries are stage-specialised, and how
  composition shifts hide inside an "aggregate-stable" picture.

Figures (in figures/):
  fig6_composition_stacked.png       Trade composition stack 1995-2024
  fig7_specialization_heatmap.png    Top 20 exporters × stage shares (2024)
  fig8_share_divergence_panels.png   Per-country share trajectories — aggregate vs stages
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
    "figure.dpi": 110,
    "savefig.dpi": 200,
    "font.size": 10,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "legend.frameon": False,
})

# Colour palette consistent with the BEC viz script
STAGE_COLOR = {
    "intermediate": "#d62728",
    "capital":      "#1f77b4",
    "consumption":  "#2ca02c",
    "semiconductor":"#9467bd",
    "aggregate":    "#222222",
}
TRADE_WAR = (2018, 2019)


def load_edges_with_stage() -> pd.DataFrame:
    """Long-format (year × source × target × stage) with stages: aggregate,
    intermediate, capital, consumption, semiconductor."""
    a = pd.read_parquet(BACI_DIR / "baci_edges_country.parquet")[
        ["year","source","target","value_busd"]
    ].assign(stage="aggregate")

    b = pd.read_parquet(BACI_DIR / "baci_edges_country_by_bec.parquet")[
        ["year","source","target","bec_stage","value_busd"]
    ].rename(columns={"bec_stage": "stage"})

    s = pd.read_parquet(BACI_DIR / "baci_edges_country_semiconductors.parquet")[
        ["year","source","target","value_busd"]
    ].assign(stage="semiconductor")

    return pd.concat([a, b, s], ignore_index=True)


# ── Figure 6: composition stack over time ────────────────────────────────
def fig6_composition_stack(df: pd.DataFrame):
    # Total trade per stage per year
    g = df[df["stage"].isin(["intermediate","capital","consumption"])].groupby(
        ["year","stage"])["value_busd"].sum().unstack(fill_value=0)
    g = g[["intermediate","capital","consumption"]]
    g_total = g.sum(axis=1)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    # Left: absolute USD bn
    ax1.stackplot(g.index, g.T.values, labels=g.columns,
                  colors=[STAGE_COLOR[c] for c in g.columns], alpha=0.85)
    ax1.set_title("Global trade composition — absolute values",
                  loc="left", fontweight="bold")
    ax1.set_xlabel("Year"); ax1.set_ylabel("Trade value (USD bn)")
    ax1.axvspan(*TRADE_WAR, color="#ffa500", alpha=0.18, zorder=10)
    ax1.text(TRADE_WAR[0]+0.3, ax1.get_ylim()[1]*0.97, "Trade war",
             color="#b86200", fontsize=9, fontweight="bold")
    ax1.legend(loc="upper left", fontsize=9)
    ax1.grid(axis="y", alpha=0.25, lw=0.5)
    ax1.xaxis.set_major_locator(MultipleLocator(5))

    # Right: % composition
    g_pct = (g.div(g_total, axis=0) * 100)
    ax2.stackplot(g_pct.index, g_pct.T.values, labels=g_pct.columns,
                  colors=[STAGE_COLOR[c] for c in g_pct.columns], alpha=0.85)
    ax2.set_title("Global trade composition — share (%)",
                  loc="left", fontweight="bold")
    ax2.set_xlabel("Year"); ax2.set_ylabel("Share of total (%)")
    ax2.set_ylim(0, 100)
    ax2.axvspan(*TRADE_WAR, color="#ffa500", alpha=0.18, zorder=10)
    ax2.text(TRADE_WAR[0]+0.3, 97, "Trade war",
             color="#b86200", fontsize=9, fontweight="bold")
    ax2.legend(loc="lower right", fontsize=9)
    ax2.grid(axis="y", alpha=0.25, lw=0.5)
    ax2.xaxis.set_major_locator(MultipleLocator(5))

    fig.suptitle("Trade composition is remarkably stable; aggregate hides where shocks land",
                 fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    out = FIG_DIR / "fig6_composition_stacked.png"
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  → {out.relative_to(ROOT)}")


# ── Figure 7: specialization heatmap ─────────────────────────────────────
def fig7_specialization_heatmap(df: pd.DataFrame):
    """For top 20 exporters in 2024 by aggregate, show their share of each
    sub-network. Plus a delta panel (stage share − aggregate share)."""
    year = 2024
    # Country share (% of global) by stage in 2024
    by_src = df[df.year == year].groupby(["stage","source"])["value_busd"].sum().reset_index()
    by_src["total"] = by_src.groupby("stage")["value_busd"].transform("sum")
    by_src["share_pct"] = 100 * by_src["value_busd"] / by_src["total"]

    # Top 20 exporters by aggregate share
    top = by_src[by_src.stage == "aggregate"].nlargest(20, "share_pct")["source"].tolist()

    stages = ["aggregate","intermediate","capital","consumption","semiconductor"]
    grid = (by_src[by_src.source.isin(top)]
            .pivot_table(index="source", columns="stage", values="share_pct", fill_value=0)
            .reindex(index=top, columns=stages))

    # Delta: stage share − aggregate share. Aggregate column is 0 by construction.
    delta = grid.sub(grid["aggregate"], axis=0)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 9))

    # Left: levels
    im1 = ax1.imshow(grid.values, aspect="auto", cmap="viridis")
    ax1.set_xticks(range(len(stages))); ax1.set_xticklabels(
        [s.capitalize() if s != "semiconductor" else "Semi." for s in stages],
        rotation=0)
    ax1.set_yticks(range(len(top))); ax1.set_yticklabels(top)
    ax1.set_title("Country export shares by network (%) — 2024",
                  loc="left", fontweight="bold")
    for i in range(len(top)):
        for j in range(len(stages)):
            v = grid.values[i, j]
            color = "white" if v < grid.values.max() * 0.55 else "black"
            ax1.text(j, i, f"{v:.1f}", ha="center", va="center",
                     color=color, fontsize=8.5)
    fig.colorbar(im1, ax=ax1, label="Share of global out-strength (%)", shrink=0.85)

    # Right: deviations from aggregate share
    vmax = float(np.max(np.abs(delta.values))) or 1.0
    im2 = ax2.imshow(delta.values, aspect="auto", cmap="RdBu_r", vmin=-vmax, vmax=vmax)
    ax2.set_xticks(range(len(stages))); ax2.set_xticklabels(
        [s.capitalize() if s != "semiconductor" else "Semi." for s in stages],
        rotation=0)
    ax2.set_yticks(range(len(top))); ax2.set_yticklabels(top)
    ax2.set_title("Stage specialisation = share(stage) − share(aggregate)",
                  loc="left", fontweight="bold")
    for i in range(len(top)):
        for j in range(len(stages)):
            v = delta.values[i, j]
            color = "white" if abs(v) > vmax * 0.55 else "black"
            ax2.text(j, i, f"{v:+.1f}", ha="center", va="center",
                     color=color, fontsize=8.5)
    fig.colorbar(im2, ax=ax2, label="pp deviation from aggregate share", shrink=0.85)

    fig.suptitle(
        "Aggregate trade share hides sharp stage specialisation\n"
        "Where rows colour differently across columns → aggregate misses the story",
        fontsize=12, fontweight="bold"
    )
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    out = FIG_DIR / "fig7_specialization_heatmap.png"
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  → {out.relative_to(ROOT)}")


# ── Figure 8: per-country share trajectories ─────────────────────────────
def fig8_share_panels(df: pd.DataFrame):
    """For four focal countries, show their share of each network 2010-2024.
    Demonstrates where aggregate trajectory differs from stage trajectories."""
    focal = ["CHN", "USA", "VNM", "MEX", "DEU", "S19"]
    titles = {"CHN":"China","USA":"USA","VNM":"Vietnam","MEX":"Mexico",
              "DEU":"Germany","S19":"Taiwan (S19)"}

    # Compute share% per (year, stage, country)
    g = df.groupby(["year","stage","source"])["value_busd"].sum().reset_index()
    g["total"] = g.groupby(["year","stage"])["value_busd"].transform("sum")
    g["share_pct"] = 100 * g["value_busd"] / g["total"]
    g = g[g.source.isin(focal) & g.year.between(2010, 2024)]

    fig, axes = plt.subplots(3, 2, figsize=(13, 12))
    stages_to_plot = ["aggregate","intermediate","capital","consumption","semiconductor"]
    for ax, country in zip(axes.flat, focal):
        for stage in stages_to_plot:
            sub = g[(g.source == country) & (g.stage == stage)].sort_values("year")
            ax.plot(sub["year"], sub["share_pct"],
                    color=STAGE_COLOR[stage],
                    lw=2.4 if stage == "aggregate" else 1.8,
                    ls="--" if stage == "semiconductor" else "-",
                    label=stage.capitalize(),
                    zorder=5 if stage == "aggregate" else 3)
        ax.set_title(titles.get(country, country), loc="left", fontweight="bold")
        ax.set_xlabel("Year"); ax.set_ylabel("Share of network (%)")
        ax.axvspan(*TRADE_WAR, color="#ffa500", alpha=0.18, zorder=0)
        ax.axvline(2020, color="#999999", ls=":", lw=0.8, alpha=0.6)
        ax.grid(axis="y", alpha=0.25, lw=0.5)
        ax.xaxis.set_major_locator(MultipleLocator(2))

    h, l = axes[0, 0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=5, bbox_to_anchor=(0.5, -0.005),
               frameon=False, fontsize=10)
    fig.suptitle("Country export shares by network — where aggregate misleads",
                 fontsize=13, fontweight="bold", y=0.995)
    fig.tight_layout(rect=[0, 0.025, 1, 0.97])
    out = FIG_DIR / "fig8_share_divergence_panels.png"
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  → {out.relative_to(ROOT)}")


def main():
    df = load_edges_with_stage()
    print(f"[load] {df.shape} rows, stages = {sorted(df['stage'].unique())}")
    print("[plot] figures →")
    fig6_composition_stack(df)
    fig7_specialization_heatmap(df)
    fig8_share_panels(df)


if __name__ == "__main__":
    main()
