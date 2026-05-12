"""
Visualisations comparing the aggregate trade network against the BEC-stratified
sub-networks (intermediate / capital / consumption).

Produces four PNG figures in figures/:
  fig1_network_metrics_levels.png   — density, modularity, HHI, n_edges (2010-2024)
  fig2_network_metrics_indexed.png  — same metrics, indexed to 2017=100
  fig3_country_panels.png           — CHN share, USA betweenness, VNM PageRank, MEX PageRank
  fig4_long_run_context.png         — same metrics over 1995-2024 (for context)

Shock markers: GFC 2008-09 (shaded grey), trade war 2018-19 (shaded amber),
COVID 2020 (dashed vertical), Trump-II 2025 (annotation only — beyond data).
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

# ── Style ──────────────────────────────────────────────────────────────────
plt.rcParams.update({
    "figure.dpi": 110,
    "savefig.dpi": 200,
    "font.size": 10,
    "axes.labelsize": 11,
    "axes.titlesize": 12,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "legend.frameon": False,
    "legend.fontsize": 9,
})

NET_STYLE = {
    "aggregate":     dict(color="#222222", lw=2.4, ls="-",  zorder=5, label="Aggregate"),
    "intermediate":  dict(color="#d62728", lw=2.0, ls="-",  zorder=4, label="Intermediate"),
    "capital":       dict(color="#1f77b4", lw=2.0, ls="-",  zorder=3, label="Capital"),
    "consumption":   dict(color="#2ca02c", lw=2.0, ls="-",  zorder=2, label="Consumption"),
    "semiconductor": dict(color="#9467bd", lw=2.2, ls="--", zorder=6, label="Semiconductors (HS 8541+8542)"),
}
NETS = list(NET_STYLE.keys())

# Shock annotations
TRADE_WAR = (2018, 2019)
GFC       = (2008, 2009)
COVID     = 2020

WINDOW_SHOCK = (2010, 2024)
WINDOW_FULL  = (1995, 2024)


def load_global() -> pd.DataFrame:
    """Stack the 5 global-metric CSVs into a long dataframe."""
    files = {
        "aggregate":     "long_run_global_metrics.csv",
        "intermediate":  "long_run_global_metrics_bec_intermediate.csv",
        "capital":       "long_run_global_metrics_bec_capital.csv",
        "consumption":   "long_run_global_metrics_bec_consumption.csv",
        "semiconductor": "long_run_global_metrics_semi.csv",
    }
    parts = []
    for net, f in files.items():
        d = pd.read_csv(BACI_DIR / f)
        d["net"] = net
        parts.append(d)
    return pd.concat(parts, ignore_index=True)


def load_country() -> pd.DataFrame:
    files = {
        "aggregate":     "long_run_country_metrics.csv",
        "intermediate":  "long_run_country_metrics_bec_intermediate.csv",
        "capital":       "long_run_country_metrics_bec_capital.csv",
        "consumption":   "long_run_country_metrics_bec_consumption.csv",
        "semiconductor": "long_run_country_metrics_semi.csv",
    }
    parts = []
    for net, f in files.items():
        d = pd.read_csv(BACI_DIR / f)
        d["net"] = net
        parts.append(d)
    return pd.concat(parts, ignore_index=True)


def shade_shocks(ax, window=WINDOW_SHOCK):
    """Shade GFC, trade war; mark COVID with dashed line."""
    x0, x1 = window
    # GFC
    if x0 <= GFC[1]:
        ax.axvspan(max(GFC[0], x0), min(GFC[1], x1),
                   color="#888888", alpha=0.10, zorder=0)
        ax.text(GFC[0] + 0.5, ax.get_ylim()[1], "GFC",
                fontsize=8, color="#666666", ha="left", va="top")
    # Trade war
    ax.axvspan(TRADE_WAR[0], TRADE_WAR[1],
               color="#ffa500", alpha=0.15, zorder=0)
    ax.text(TRADE_WAR[0] + 0.5, ax.get_ylim()[1], "Trade war",
            fontsize=8, color="#b86200", ha="left", va="top",
            fontweight="bold")
    # COVID
    ax.axvline(COVID, color="#888888", ls="--", lw=1.0, alpha=0.6, zorder=1)
    ax.text(COVID + 0.05, ax.get_ylim()[0] + 0.02*(ax.get_ylim()[1]-ax.get_ylim()[0]),
            "COVID", fontsize=8, color="#666666", ha="left", va="bottom",
            rotation=90)


def plot_metric_lines(ax, g: pd.DataFrame, metric: str, window=WINDOW_SHOCK,
                      indexed_to: int | None = None, ylabel: str | None = None):
    x0, x1 = window
    for net in NETS:
        sub = g[(g.net == net) & (g.year >= x0) & (g.year <= x1)].sort_values("year")
        y = sub[metric].values
        if indexed_to is not None:
            base = g[(g.net == net) & (g.year == indexed_to)][metric].iloc[0]
            y = 100.0 * y / base
        ax.plot(sub["year"], y, **NET_STYLE[net])
    ax.set_xlim(x0 - 0.3, x1 + 0.3)
    ax.set_xlabel("Year")
    if ylabel is not None:
        ax.set_ylabel(ylabel)
    ax.xaxis.set_major_locator(MultipleLocator(2))
    ax.grid(axis="y", alpha=0.25, lw=0.5)


def fig1_levels(g: pd.DataFrame):
    fig, axes = plt.subplots(2, 2, figsize=(13, 8.5))
    panels = [
        ("density",            "Network density",            "Density (directed edges / N(N-1))"),
        ("modularity_louvain", "Modularity (Louvain)",       "Modularity coefficient"),
        ("hhi_out_strength",   "Export concentration (HHI)", "Out-strength HHI"),
        ("n_edges",            "Active bilateral links",     "# of directed edges"),
    ]
    for ax, (metric, title, ylab) in zip(axes.flat, panels):
        plot_metric_lines(ax, g, metric, ylabel=ylab)
        ax.set_title(title, loc="left", fontweight="bold")
        shade_shocks(ax)

    h, l = axes.flat[0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=5, bbox_to_anchor=(0.5, -0.005),
               frameon=False, fontsize=10)
    fig.suptitle("Network structure by BEC stage, 2010–2024",
                 fontsize=14, fontweight="bold", y=0.995)
    fig.tight_layout(rect=[0, 0.03, 1, 0.97])
    out = FIG_DIR / "fig1_network_metrics_levels.png"
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  → {out.relative_to(ROOT)}")


def fig2_indexed(g: pd.DataFrame):
    fig, axes = plt.subplots(2, 2, figsize=(13, 8.5))
    panels = [
        ("density",            "Network density"),
        ("modularity_louvain", "Modularity (Louvain)"),
        ("hhi_out_strength",   "Export concentration (HHI)"),
        ("total_trade_busd",   "Total trade (USD bn)"),
    ]
    for ax, (metric, title) in zip(axes.flat, panels):
        plot_metric_lines(ax, g, metric, indexed_to=2017,
                          ylabel="Index (2017 = 100)")
        ax.set_title(title, loc="left", fontweight="bold")
        ax.axhline(100, color="#999999", ls=":", lw=0.8, alpha=0.6, zorder=0)
        shade_shocks(ax)

    h, l = axes.flat[0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=5, bbox_to_anchor=(0.5, -0.005),
               frameon=False, fontsize=10)
    fig.suptitle("Change relative to 2017 baseline, by BEC stage",
                 fontsize=14, fontweight="bold", y=0.995)
    fig.tight_layout(rect=[0, 0.03, 1, 0.97])
    out = FIG_DIR / "fig2_network_metrics_indexed.png"
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  → {out.relative_to(ROOT)}")


def _plot_country_pagerank(ax, c: pd.DataFrame, country: str, title: str):
    for net in NETS:
        m = c[(c.country == country) & (c.net == net)]
        m = m[(m.year >= WINDOW_SHOCK[0]) & (m.year <= WINDOW_SHOCK[1])].sort_values("year")
        ax.plot(m["year"], m["pagerank"], **NET_STYLE[net])
    ax.set_title(title, loc="left", fontweight="bold")
    ax.set_xlabel("Year"); ax.set_ylabel("PageRank")
    ax.set_xlim(WINDOW_SHOCK[0]-0.3, WINDOW_SHOCK[1]+0.3)
    ax.xaxis.set_major_locator(MultipleLocator(2))
    ax.grid(axis="y", alpha=0.25, lw=0.5)
    shade_shocks(ax)


def fig3_country_panels(g: pd.DataFrame, c: pd.DataFrame):
    """Country-level trajectories for six key players, 2010–2024."""
    fig, axes = plt.subplots(3, 2, figsize=(13, 12.5))

    # Panel A: CHN out-strength share of global
    ax = axes[0, 0]
    for net in NETS:
        m = c[(c.country == "CHN") & (c.net == net)].merge(
            g[g.net == net][["year", "total_trade_busd"]], on="year", how="left"
        )
        m["share_pct"] = 100 * m["out_strength_busd"] / m["total_trade_busd"]
        m = m[(m.year >= WINDOW_SHOCK[0]) & (m.year <= WINDOW_SHOCK[1])].sort_values("year")
        ax.plot(m["year"], m["share_pct"], **NET_STYLE[net])
    ax.set_title("China — share of global out-strength (%)", loc="left", fontweight="bold")
    ax.set_xlabel("Year"); ax.set_ylabel("China's export share (%)")
    ax.set_xlim(WINDOW_SHOCK[0]-0.3, WINDOW_SHOCK[1]+0.3)
    ax.xaxis.set_major_locator(MultipleLocator(2))
    ax.grid(axis="y", alpha=0.25, lw=0.5)
    shade_shocks(ax)

    # Panel B: USA betweenness centrality
    ax = axes[0, 1]
    for net in NETS:
        m = c[(c.country == "USA") & (c.net == net)]
        m = m[(m.year >= WINDOW_SHOCK[0]) & (m.year <= WINDOW_SHOCK[1])].sort_values("year")
        ax.plot(m["year"], m["betweenness"], **NET_STYLE[net])
    ax.set_title("USA — betweenness centrality", loc="left", fontweight="bold")
    ax.set_xlabel("Year"); ax.set_ylabel("Betweenness (weighted)")
    ax.set_xlim(WINDOW_SHOCK[0]-0.3, WINDOW_SHOCK[1]+0.3)
    ax.xaxis.set_major_locator(MultipleLocator(2))
    ax.grid(axis="y", alpha=0.25, lw=0.5)
    shade_shocks(ax)

    # Panels C-F: PageRank for connector / hub countries
    _plot_country_pagerank(axes[1, 0], c, "VNM", "Vietnam — PageRank centrality")
    _plot_country_pagerank(axes[1, 1], c, "MEX", "Mexico — PageRank centrality")
    _plot_country_pagerank(axes[2, 0], c, "KOR", "Korea — PageRank centrality")
    _plot_country_pagerank(axes[2, 1], c, "S19", "Taiwan (S19) — PageRank centrality")

    h, l = axes[0, 0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=5, bbox_to_anchor=(0.5, -0.005),
               frameon=False, fontsize=10)
    fig.suptitle("Country-level repositioning by BEC stage, 2010–2024",
                 fontsize=14, fontweight="bold", y=0.995)
    fig.tight_layout(rect=[0, 0.025, 1, 0.97])
    out = FIG_DIR / "fig3_country_panels.png"
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  → {out.relative_to(ROOT)}")


def fig4_full_history(g: pd.DataFrame):
    """Long-run context 1995-2024 for the two flagship metrics."""
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.6))
    for ax, metric, title, ylab in [
        (axes[0], "density",            "Network density",      "Density"),
        (axes[1], "modularity_louvain", "Modularity (Louvain)", "Modularity"),
    ]:
        plot_metric_lines(ax, g, metric, window=WINDOW_FULL, ylabel=ylab)
        ax.set_title(title, loc="left", fontweight="bold")
        ax.xaxis.set_major_locator(MultipleLocator(5))
        shade_shocks(ax, window=WINDOW_FULL)

    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=5, bbox_to_anchor=(0.5, -0.02),
               frameon=False, fontsize=10)
    fig.suptitle("Long-run context: 30 years of trade-network structure",
                 fontsize=14, fontweight="bold", y=0.995)
    fig.tight_layout(rect=[0, 0.05, 1, 0.96])
    out = FIG_DIR / "fig4_long_run_context.png"
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  → {out.relative_to(ROOT)}")


def fig5_semi_focus(g: pd.DataFrame, c: pd.DataFrame):
    """Dedicated figure for the semiconductor sub-network.

    Six panels: structural metrics (density, modularity, HHI) and the four
    key country players for chips (CHN, USA, S19/Taiwan, KOR).
    Window 2010-2024.
    """
    fig, axes = plt.subplots(3, 2, figsize=(13, 12.5))

    # Panel A: HHI of out-strength
    ax = axes[0, 0]
    for net in NETS:
        sub = g[(g.net == net) & (g.year >= WINDOW_SHOCK[0]) & (g.year <= WINDOW_SHOCK[1])].sort_values("year")
        ax.plot(sub["year"], sub["hhi_out_strength"], **NET_STYLE[net])
    ax.set_title("Export concentration (HHI) — chips much higher than other networks",
                 loc="left", fontweight="bold", fontsize=11)
    ax.set_xlabel("Year"); ax.set_ylabel("HHI of out-strength")
    ax.set_xlim(WINDOW_SHOCK[0]-0.3, WINDOW_SHOCK[1]+0.3)
    ax.xaxis.set_major_locator(MultipleLocator(2))
    ax.grid(axis="y", alpha=0.25, lw=0.5)
    shade_shocks(ax)

    # Panel B: Modularity
    ax = axes[0, 1]
    for net in NETS:
        sub = g[(g.net == net) & (g.year >= WINDOW_SHOCK[0]) & (g.year <= WINDOW_SHOCK[1])].sort_values("year")
        ax.plot(sub["year"], sub["modularity_louvain"], **NET_STYLE[net])
    ax.set_title("Modularity — chips less bloc-y than aggregate or intermediates",
                 loc="left", fontweight="bold", fontsize=11)
    ax.set_xlabel("Year"); ax.set_ylabel("Modularity (Louvain)")
    ax.set_xlim(WINDOW_SHOCK[0]-0.3, WINDOW_SHOCK[1]+0.3)
    ax.xaxis.set_major_locator(MultipleLocator(2))
    ax.grid(axis="y", alpha=0.25, lw=0.5)
    shade_shocks(ax)

    # Panel C: CHN out-strength share
    ax = axes[1, 0]
    for net in NETS:
        m = c[(c.country == "CHN") & (c.net == net)].merge(
            g[g.net == net][["year","total_trade_busd"]], on="year", how="left"
        )
        m["share_pct"] = 100 * m["out_strength_busd"] / m["total_trade_busd"]
        m = m[(m.year >= WINDOW_SHOCK[0]) & (m.year <= WINDOW_SHOCK[1])].sort_values("year")
        ax.plot(m["year"], m["share_pct"], **NET_STYLE[net])
    ax.set_title("China — share of total trade by stage", loc="left", fontweight="bold")
    ax.set_xlabel("Year"); ax.set_ylabel("China's export share (%)")
    ax.set_xlim(WINDOW_SHOCK[0]-0.3, WINDOW_SHOCK[1]+0.3)
    ax.xaxis.set_major_locator(MultipleLocator(2))
    ax.grid(axis="y", alpha=0.25, lw=0.5)
    shade_shocks(ax)

    # Panel D: USA betweenness
    ax = axes[1, 1]
    for net in NETS:
        m = c[(c.country == "USA") & (c.net == net)]
        m = m[(m.year >= WINDOW_SHOCK[0]) & (m.year <= WINDOW_SHOCK[1])].sort_values("year")
        ax.plot(m["year"], m["betweenness"], **NET_STYLE[net])
    ax.set_title("USA — betweenness centrality", loc="left", fontweight="bold")
    ax.set_xlabel("Year"); ax.set_ylabel("Betweenness")
    ax.set_xlim(WINDOW_SHOCK[0]-0.3, WINDOW_SHOCK[1]+0.3)
    ax.xaxis.set_major_locator(MultipleLocator(2))
    ax.grid(axis="y", alpha=0.25, lw=0.5)
    shade_shocks(ax)

    # Panel E: Taiwan (S19) PageRank
    _plot_country_pagerank(axes[2, 0], c, "S19", "Taiwan (S19) — PageRank")

    # Panel F: Korea PageRank
    _plot_country_pagerank(axes[2, 1], c, "KOR", "Korea — PageRank")

    h, l = axes[0, 0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=5, bbox_to_anchor=(0.5, -0.005),
               frameon=False, fontsize=10)
    fig.suptitle("Semiconductor (HS 8541+8542) network vs aggregate and BEC stages, 2010–2024",
                 fontsize=14, fontweight="bold", y=0.995)
    fig.tight_layout(rect=[0, 0.025, 1, 0.97])
    out = FIG_DIR / "fig5_semiconductors.png"
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  → {out.relative_to(ROOT)}")


def main():
    g = load_global()
    c = load_country()
    print(f"[load] global={g.shape}  country={c.shape}")
    print("[plot] figures →")
    fig1_levels(g)
    fig2_indexed(g)
    fig3_country_panels(g, c)
    fig4_full_history(g)
    fig5_semi_focus(g, c)


if __name__ == "__main__":
    main()
