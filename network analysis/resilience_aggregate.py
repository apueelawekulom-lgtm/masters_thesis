"""
Aggregate network resilience analysis, 1995-2024.

Four classical network-theoretic measures:
  1. k-core decomposition       — backbone size and country composition over time
  2. Algebraic connectivity λ₂  — single-scalar structural robustness
  3. Targeted-attack robustness  — giant component decay under hub removal
  4. Disparity-filter backbone   — load-bearing edges (Serrano et al. 2009)

Plus: hub-removal cascade simulation — direct shock-propagation test.

Computational notes:
  - We use the directed weighted graph for centrality and attack simulation.
  - For k-core and λ₂ we symmetrise (sum of bilateral weights), threshold
    edges at $50M to remove noise, and use the resulting unweighted graph.
  - For disparity-filter backbone we follow Serrano, Boguñá & Vespignani
    (PNAS 2009): keep edges whose weight is statistically significant
    given the local node weight distribution.

Outputs (BACI_HS92_V202601/):
  resilience_global_metrics.csv      one row per year: λ₂, max_k_core, etc.
  resilience_kcore_members.csv       year × country × innermost_k_shell membership
  resilience_attack_curves.csv       year × removed_k × giant_component_frac
  resilience_backbone_{2017,2024}.csv  surviving edges per snapshot

Figures (figures/):
  fig13_resilience_metrics.png       λ₂, max k, top-k membership share, density
  fig14_attack_robustness.png        attack curves for snapshot years
  fig15_kcore_evolution.png          country participation in innermost shell over time
  fig16_backbone_comparison.png      backbone summary 2017 vs 2024
"""

from __future__ import annotations

import time
from pathlib import Path
from collections import defaultdict
from scipy import sparse
from scipy.sparse.linalg import eigsh

import numpy as np
import pandas as pd
import networkx as nx

ROOT = Path(__file__).parent
BACI_DIR = ROOT / "BACI_HS92_V202601"
EDGES = BACI_DIR / "baci_edges_country.parquet"

OUT_METRICS    = BACI_DIR / "resilience_global_metrics.csv"
OUT_KCORE      = BACI_DIR / "resilience_kcore_members.csv"
OUT_ATTACK     = BACI_DIR / "resilience_attack_curves.csv"
OUT_BACKBONE_F = BACI_DIR / "resilience_backbone_{year}.csv"

EDGE_THRESHOLD_BUSD = 0.05   # $50M: drop tiny flows for k-core / λ₂ computation (aggregate default)
SNAPSHOT_YEARS = [2008, 2017, 2019, 2021, 2024]
ATTACK_STEPS = 30


# ─── helpers ──────────────────────────────────────────────────────────────
def build_dg(df_y: pd.DataFrame) -> nx.DiGraph:
    """Directed weighted graph for a single year."""
    edf = df_y[df_y["value_busd"] >= 0.001]  # drop sub-$1M
    return nx.from_pandas_edgelist(
        edf, source="source", target="target", edge_attr="value_busd",
        create_using=nx.DiGraph(),
    )


def symmetric_thresholded(G: nx.DiGraph, threshold_busd: float) -> nx.Graph:
    """Undirected, edge weight = sum of bidirectional, dropped if below threshold."""
    H = nx.Graph()
    H.add_nodes_from(G.nodes())
    for u, v, w in G.edges(data="value_busd"):
        if H.has_edge(u, v):
            H[u][v]["weight"] += w
        else:
            H.add_edge(u, v, weight=w)
    drop = [(u, v) for u, v, d in H.edges(data=True) if d["weight"] < threshold_busd]
    H.remove_edges_from(drop)
    H.remove_nodes_from([n for n in list(H.nodes()) if H.degree(n) == 0])
    return H


def algebraic_connectivity(H: nx.Graph) -> float:
    """λ₂ of unweighted Laplacian — robustness scalar (higher = harder to disconnect).
    Dense computation since networks here are ~200 nodes."""
    if H.number_of_nodes() < 3:
        return float("nan")
    comps = list(nx.connected_components(H))
    largest = max(comps, key=len)
    sub = H.subgraph(largest)
    L = nx.laplacian_matrix(sub).astype(float).toarray()
    eigs = np.linalg.eigvalsh(L)  # ascending order
    return float(eigs[1])  # λ₁ ≈ 0, λ₂ = Fiedler value


def k_core_decomposition(H: nx.Graph) -> tuple[int, dict[str, int]]:
    """Return (max core number, mapping country → core number)."""
    core = nx.core_number(H)
    if not core:
        return 0, {}
    return max(core.values()), core


def targeted_attack_curve(G: nx.DiGraph, n_steps: int = 30) -> list[float]:
    """Remove top-k countries by out-strength sequentially; track giant component fraction."""
    out_str = sorted(G.out_degree(weight="value_busd"), key=lambda x: -x[1])
    order = [n for n, _ in out_str]
    H = G.to_undirected()
    n_total = H.number_of_nodes()
    curve = []
    for k in range(min(n_steps, len(order)) + 1):
        to_remove = order[:k]
        sub = H.copy()
        sub.remove_nodes_from(to_remove)
        if sub.number_of_nodes() == 0:
            curve.append(0.0)
            continue
        comps = list(nx.connected_components(sub))
        gc = max(comps, key=len)
        curve.append(len(gc) / n_total)
    return curve


def disparity_filter_backbone(H: nx.Graph, alpha: float = 0.01) -> nx.Graph:
    """Serrano, Boguñá, Vespignani (PNAS 2009): extract statistically significant backbone.

    For each edge (i,j) and node i of degree k_i, the null hypothesis is that
    the weight share p_ij = w_ij / s_i is drawn uniformly from the simplex.
    The p-value of observing p_ij is (1 - p_ij)^(k_i-1). Keep edges with
    p < alpha on at least one side.
    """
    keep = set()
    for n in H.nodes():
        nbrs = list(H.neighbors(n))
        if len(nbrs) < 2:  # nodes of degree 1 keep their single tie
            for m in nbrs:
                keep.add(frozenset((n, m)))
            continue
        s = sum(H[n][m]["weight"] for m in nbrs)
        k = len(nbrs)
        for m in nbrs:
            p_ij = H[n][m]["weight"] / s
            p_val = (1 - p_ij) ** (k - 1)
            if p_val < alpha:
                keep.add(frozenset((n, m)))
    B = nx.Graph()
    B.add_nodes_from(H.nodes())
    for fs in keep:
        u, v = tuple(fs)
        if H.has_edge(u, v):
            B.add_edge(u, v, weight=H[u][v]["weight"])
    return B


# ─── reusable runner ──────────────────────────────────────────────────────
def run_resilience(
    edges: pd.DataFrame,
    threshold_busd: float,
    out_dir: Path,
    suffix: str = "",
    snapshot_years: list[int] = SNAPSHOT_YEARS,
    attack_steps: int = ATTACK_STEPS,
    label: str = "aggregate",
) -> None:
    """Run the full resilience pipeline on a (year, source, target, value_busd) edge list.

    Outputs in out_dir:
      resilience_global_metrics{suffix}.csv
      resilience_kcore_members{suffix}.csv
      resilience_attack_curves{suffix}.csv
      resilience_backbone_{year}{suffix}.csv
    """
    print(f"\n[run:{label}] shape={edges.shape}  threshold=${threshold_busd*1000:.1f}M  "
          f"years={edges.year.min()}–{edges.year.max()}")
    global_records = []
    kcore_records  = []
    attack_records = []
    backbones      = {}

    for year, ydf in edges.groupby("year"):
        t = time.time()
        G = build_dg(ydf)
        H = symmetric_thresholded(G, threshold_busd)

        lam2  = algebraic_connectivity(H)
        kmax, core_map = k_core_decomposition(H)
        top_shell_members = sorted([n for n, c in core_map.items() if c == kmax])
        top_shell_size = len(top_shell_members)

        ac = targeted_attack_curve(G, n_steps=attack_steps) if int(year) in snapshot_years else []

        n_ts, e_ts = H.number_of_nodes(), H.number_of_edges()
        dens_thr = (2 * e_ts) / (n_ts * (n_ts - 1)) if n_ts > 1 else 0.0
        bridges = list(nx.bridges(H)) if H.number_of_edges() > 0 else []

        global_records.append({
            "year": int(year),
            "n_nodes_thr": n_ts, "n_edges_thr": e_ts, "density_thr": dens_thr,
            "lambda2": lam2, "max_k_core": kmax,
            "top_kshell_size": top_shell_size, "n_bridges": len(bridges),
        })
        for n, c in core_map.items():
            kcore_records.append({"year": int(year), "country": n,
                                  "core_number": c, "in_top_kshell": int(c == kmax)})
        if int(year) in snapshot_years:
            for k, frac in enumerate(ac):
                attack_records.append({"year": int(year), "k_removed": k, "gc_frac": frac})
            backbones[int(year)] = disparity_filter_backbone(H, alpha=0.01)

        print(f"  {int(year)} n_thr={n_ts:3} e_thr={e_ts:5} λ₂={lam2:.4f} "
              f"max_k={kmax:3} top_kshell={top_shell_size:3} bridges={len(bridges):3} "
              f"dt={time.time()-t:4.1f}s")

    pd.DataFrame(global_records).to_csv(out_dir / f"resilience_global_metrics{suffix}.csv",
                                        index=False, float_format="%.6f")
    pd.DataFrame(kcore_records).to_csv(out_dir / f"resilience_kcore_members{suffix}.csv",
                                       index=False)
    pd.DataFrame(attack_records).to_csv(out_dir / f"resilience_attack_curves{suffix}.csv",
                                        index=False, float_format="%.4f")
    for yr, B in backbones.items():
        rows = [{"source": u, "target": v, "weight_busd": d["weight"]}
                for u, v, d in B.edges(data=True)]
        pd.DataFrame(rows).to_csv(out_dir / f"resilience_backbone_{yr}{suffix}.csv",
                                  index=False, float_format="%.4f")
    print(f"[saved] resilience_*{suffix}.csv  ({len(backbones)} backbones)")


# ─── main loop (aggregate default) ────────────────────────────────────────
def main():
    edges = pd.read_parquet(EDGES)
    print(f"[load] {EDGES.name}  shape={edges.shape}")
    run_resilience(edges, EDGE_THRESHOLD_BUSD, BACI_DIR, suffix="", label="aggregate")


if __name__ == "__main__":
    main()
