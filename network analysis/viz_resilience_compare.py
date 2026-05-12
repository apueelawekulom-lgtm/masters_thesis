"""
Compare network resilience across aggregate vs BEC stages vs semiconductors.

Figures (figures/):
  fig17_resilience_compare_metrics.png   λ₂, max_k, top_kshell, bridges by subnetwork
  fig18_resilience_compare_attack.png    attack-decay curves 2017 vs 2024, per subnetwork
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

# Subnetwork → (suffix, style)
SUBNETS = {
    "aggregate":     dict(suffix="",                  color="#222222", lw=2.4, ls="-",  label="Aggregate"),
    "intermediate":  dict(suffix="_bec_intermediate", color="#d62728", lw=2.0, ls="-",  label="Intermediate"),
    "capital":       dict(suffix="_bec_capital",      color="#1f77b4", lw=2.0, ls="-",  label="Capital"),
    "consumption":   dict(suffix="_bec_consumption",  color="#2ca02c", lw=2.0, ls="-",  label="Consumption"),
    "semiconductor": dict(suffix="_semi",             color="#9467bd", lw=2.2, ls="--", label="Semiconductors (HS 8541+8542)"),
}


def load_metrics() -> pd.DataFrame:
    parts = []
    for name, cfg in SUBNETS.items():
        d = pd.read_csv(BACI_DIR / f"resilience_global_metrics{cfg['suffix']}.csv")
        d["network"] = name
        parts.append(d)
    return pd.concat(parts, ignore_index=True)


def load_attack() -> pd.DataFrame:
    parts = []
    for name, cfg in SUBNETS.items():
        d = pd.read_csv(BACI_DIR / f"resilience_attack_curves{cfg['suffix']}.csv")
        d["network"] = name
        parts.append(d)
    return pd.concat(parts, ignore_index=True)


def shade(ax):
    if WINDOW[0] <= 2008 <= WINDOW[1]:
        ax.axvspan(2008, 2009, color="#888888", alpha=0.10)
    ax.axvspan(*TRADE_WAR, color="#ffa500", alpha=0.18)
    ax.axvline(COVID, color="#999999", ls=":", lw=0.8, alpha=0.6)


def plot_metric(ax, df: pd.DataFrame, metric: str, title: str, ylabel: str, log: bool = False):
    for name, cfg in SUBNETS.items():
        sub = df[df.network == name].sort_values("year")
        style = {k: v for k, v in cfg.items() if k != "suffix"}
        ax.plot(sub.year, sub[metric], **style)
    if log:
        ax.set_yscale("log")
    ax.set_xlim(WINDOW[0]-0.3, WINDOW[1]+0.3)
    ax.set_xlabel("Year"); ax.set_ylabel(ylabel)
    ax.set_title(title, loc="left", fontweight="bold")
    ax.xaxis.set_major_locator(MultipleLocator(5))
    ax.grid(axis="y", alpha=0.25, lw=0.5)
    shade(ax)


def fig17_compare(df: pd.DataFrame):
    fig, axes = plt.subplots(2, 2, figsize=(13, 8.5))
    plot_metric(axes[0,0], df, "lambda2",        "Algebraic connectivity (λ₂) — log scale",  "λ₂", log=True)
    plot_metric(axes[0,1], df, "max_k_core",     "Max k-core (backbone depth)",              "max k")
    plot_metric(axes[1,0], df, "top_kshell_size","Top k-shell size (innermost-core membership)", "# countries")
    plot_metric(axes[1,1], df, "n_bridges",      "Bridge edges (single-point-of-failure links)", "# bridges")
    h, l = axes[0,0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=5, bbox_to_anchor=(0.5, -0.005), fontsize=9.5)
    fig.suptitle(
        "Network resilience by subnetwork, 1995–2024 — semiconductors are dramatically less robust",
        fontsize=13, fontweight="bold", y=0.995
    )
    fig.tight_layout(rect=[0, 0.025, 1, 0.97])
    out = FIG_DIR / "fig17_resilience_compare_metrics.png"
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  → {out.relative_to(ROOT)}")


def fig18_attack_compare(att: pd.DataFrame):
    """Two panels: attack curves for 2017 vs 2024 across subnetworks."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    for ax, yr in zip(axes, [2017, 2024]):
        for name, cfg in SUBNETS.items():
            sub = att[(att.network == name) & (att.year == yr)].sort_values("k_removed")
            if len(sub) == 0:
                continue
            style = {k: v for k, v in cfg.items() if k != "suffix"}
            ax.plot(sub.k_removed, sub.gc_frac, marker="o", markersize=4, **style)
        ax.set_xlim(-0.5, 30.5); ax.set_ylim(0, 1.05)
        ax.set_xlabel("# of top-out-strength countries removed")
        ax.set_ylabel("Giant component / total nodes")
        ax.set_title(f"Targeted-attack robustness — {yr}", loc="left", fontweight="bold")
        ax.grid(axis="y", alpha=0.25, lw=0.5)
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=5, bbox_to_anchor=(0.5, -0.02), fontsize=9.5)
    fig.suptitle(
        "Curves that drop faster are more vulnerable to losing top exporters",
        fontsize=12, y=0.995
    )
    fig.tight_layout(rect=[0, 0.03, 1, 0.96])
    out = FIG_DIR / "fig18_resilience_compare_attack.png"
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  → {out.relative_to(ROOT)}")


def comparison_table(df: pd.DataFrame):
    """Print 2017 vs 2024 metrics across subnetworks."""
    print("\n" + "="*100)
    print(" Resilience metrics — 2017 vs 2024 — across subnetworks")
    print("="*100)
    for net in SUBNETS:
        d17 = df[(df.network == net) & (df.year == 2017)].iloc[0]
        d24 = df[(df.network == net) & (df.year == 2024)].iloc[0]
        print(f"\n--- {SUBNETS[net]['label']} ---")
        print(f"  {'metric':<25} {'2017':>10} {'2024':>10} {'Δ':>10}")
        for col, lab in [("n_nodes_thr","# nodes (thresholded)"),
                         ("n_edges_thr","# edges (thresholded)"),
                         ("density_thr","density"),
                         ("lambda2","λ₂"),
                         ("max_k_core","max k-core"),
                         ("top_kshell_size","top k-shell size"),
                         ("n_bridges","# bridges")]:
            v17 = d17[col]; v24 = d24[col]
            fmt = "{:>10.4f}" if isinstance(v17, float) else "{:>10.1f}"
            print(f"  {lab:<25} {fmt.format(v17)} {fmt.format(v24)} {fmt.format(v24-v17)}")


def main():
    df = load_metrics()
    att = load_attack()
    print(f"[load] metrics={df.shape}  attack={att.shape}")
    comparison_table(df)
    print("\n[plot] →")
    fig17_compare(df)
    fig18_attack_compare(att)


if __name__ == "__main__":
    main()
