"""
Long-run network metrics on the country-level BACI trade graph (1995–2024).

Computes per year:
  - Global structural metrics (density, modularity, assortativity, rich-club, etc.)
  - Country-level metrics for a watchlist (centralities, community ID)
  - Edge turnover (Jaccard vs previous year, weighted edge-correlation)

Outputs (CSV in BACI_HS92_V202601/):
  long_run_global_metrics.csv          one row per year
  long_run_country_metrics.csv         long: year × country × metric
  long_run_community_assignments.csv   year × country × community_id

Watchlist (S19 = Taiwan in BACI; no separate TWN code):
  CHN USA S19 KOR JPN DEU VNM MEX IND BRA AUS GBR FRA NLD CAN
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd
import networkx as nx

ROOT = Path(__file__).parent
BACI_DIR = ROOT / "BACI_HS92_V202601"
EDGES = BACI_DIR / "baci_edges_country.parquet"

OUT_GLOBAL  = BACI_DIR / "long_run_global_metrics.csv"
OUT_COUNTRY = BACI_DIR / "long_run_country_metrics.csv"
OUT_COMM    = BACI_DIR / "long_run_community_assignments.csv"

WATCHLIST = ["CHN","USA","S19","KOR","JPN","DEU","VNM","MEX","IND",
             "BRA","AUS","GBR","FRA","NLD","CAN"]

MIN_EDGE_BUSD = 0.001   # drop edges below $1M to remove noise (kusd → 1000 → 0.001 busd)
TOP_K_RICHCLUB = 20      # rich-club computed on top-20 hubs by total strength


def build_digraph(df: pd.DataFrame) -> nx.DiGraph:
    """Directed weighted graph. Weight is in USD billions."""
    edf = df[df["value_busd"] >= MIN_EDGE_BUSD]
    return nx.from_pandas_edgelist(
        edf, source="source", target="target", edge_attr="value_busd",
        create_using=nx.DiGraph(),
    )


def to_undirected_sum(G: nx.DiGraph) -> nx.Graph:
    """Symmetrise: edge weight = sum of both bilateral directions."""
    H = nx.Graph()
    H.add_nodes_from(G.nodes())
    for u, v, w in G.edges(data="value_busd"):
        if H.has_edge(u, v):
            H[u][v]["weight"] += w
        else:
            H.add_edge(u, v, weight=w)
    return H


def rich_club_top_k(H: nx.Graph, k: int = TOP_K_RICHCLUB) -> float:
    """Edge density within top-k by weighted strength."""
    strengths = sorted(H.degree(weight="weight"), key=lambda x: -x[1])
    top = [n for n, _ in strengths[:k]]
    sub = H.subgraph(top)
    n = sub.number_of_nodes()
    if n < 2:
        return float("nan")
    return sub.number_of_edges() / (n * (n - 1) / 2)


def jaccard_edge(prev: set, curr: set) -> float:
    if not prev:
        return float("nan")
    inter = len(prev & curr)
    union = len(prev | curr)
    return inter / union if union > 0 else float("nan")


def compute_year(year: int, year_df: pd.DataFrame, prev_edges: set | None):
    G = build_digraph(year_df)
    H = to_undirected_sum(G)

    n_nodes = G.number_of_nodes()
    n_edges = G.number_of_edges()
    density = nx.density(G)

    # Largest weakly connected component & diameter
    wccs = list(nx.weakly_connected_components(G))
    wcc_largest = max(wccs, key=len)
    wcc_frac = len(wcc_largest) / n_nodes
    G_wcc = nx.DiGraph(G.subgraph(wcc_largest))
    diameter = nx.diameter(G_wcc.to_undirected())

    # Strengths (weighted degrees)
    out_str = dict(G.out_degree(weight="value_busd"))
    in_str  = dict(G.in_degree(weight="value_busd"))
    total_out = sum(out_str.values()) or 1.0
    # HHI of out-strength (export concentration)
    hhi_out = float(sum((s / total_out) ** 2 for s in out_str.values()))

    # Avg weighted clustering (on undirected weighted graph)
    avg_clust = nx.average_clustering(H, weight="weight")

    # Modularity via Louvain on undirected weighted graph
    try:
        communities = nx.community.louvain_communities(H, weight="weight", seed=42)
        modularity = nx.community.modularity(H, communities, weight="weight")
        n_communities = len(communities)
        # Country → community ID
        comm_map = {}
        for cid, members in enumerate(sorted(communities, key=lambda c: -len(c))):
            for m in members:
                comm_map[m] = cid
    except Exception:
        modularity = float("nan"); n_communities = -1; comm_map = {}

    # Degree-degree assortativity (on directed: out-in)
    try:
        assort = nx.degree_assortativity_coefficient(G, x="out", y="in", weight="value_busd")
    except Exception:
        assort = float("nan")

    # Rich-club coefficient over top-K hubs
    rc_topk = rich_club_top_k(H, TOP_K_RICHCLUB)

    # Edge Jaccard vs prev year
    curr_edges = set(G.edges())
    jac = jaccard_edge(prev_edges, curr_edges) if prev_edges is not None else float("nan")

    # PageRank, eigenvector, betweenness (directed where possible)
    pr = nx.pagerank(G, weight="value_busd")
    try:
        evc = nx.eigenvector_centrality_numpy(G, weight="value_busd")
    except Exception:
        evc = {n: float("nan") for n in G.nodes()}
    # Betweenness on weighted graph: weight should be DISTANCE (small = strong link).
    # Use 1/value as distance proxy so high-trade edges are "short paths".
    G_dist = nx.DiGraph()
    G_dist.add_nodes_from(G.nodes())
    for u, v, w in G.edges(data="value_busd"):
        G_dist.add_edge(u, v, distance=1.0 / w)
    bc = nx.betweenness_centrality(G_dist, weight="distance", normalized=True)

    global_row = {
        "year":               year,
        "n_nodes":            n_nodes,
        "n_edges":            n_edges,
        "density":            density,
        "wcc_largest_frac":   wcc_frac,
        "diameter":           diameter,
        "avg_weighted_clust": avg_clust,
        "modularity_louvain": modularity,
        "n_communities":      n_communities,
        "assortativity_oi":   assort,
        "rich_club_top20":    rc_topk,
        "hhi_out_strength":   hhi_out,
        "jaccard_vs_prev":    jac,
        "total_trade_busd":   total_out,
    }

    # Country-level metrics for watchlist
    country_rows = []
    for c in WATCHLIST:
        if c not in G:
            country_rows.append({"year": year, "country": c,
                                 "in_degree": 0, "out_degree": 0,
                                 "in_strength_busd": 0.0, "out_strength_busd": 0.0,
                                 "pagerank": float("nan"),
                                 "eigenvector": float("nan"),
                                 "betweenness": float("nan"),
                                 "community_id": -1})
            continue
        country_rows.append({
            "year": year, "country": c,
            "in_degree":  G.in_degree(c),
            "out_degree": G.out_degree(c),
            "in_strength_busd":  in_str.get(c, 0.0),
            "out_strength_busd": out_str.get(c, 0.0),
            "pagerank":    pr.get(c, float("nan")),
            "eigenvector": evc.get(c, float("nan")),
            "betweenness": bc.get(c, float("nan")),
            "community_id": comm_map.get(c, -1),
        })

    # Community assignments (all countries — keep so we can analyse bloc evolution)
    comm_rows = [{"year": year, "country": c, "community_id": cid}
                 for c, cid in comm_map.items()]

    return global_row, country_rows, comm_rows, curr_edges


def run_long_run(
    edges: pd.DataFrame,
    out_global: Path,
    out_country: Path,
    out_comm: Path,
    label: str = "aggregate",
) -> None:
    """Run the long-run pipeline on any (year, source, target, value_busd) edge list."""
    required = {"year", "source", "target", "value_busd"}
    missing = required - set(edges.columns)
    assert not missing, f"edges missing columns: {missing}"

    print(f"[run:{label}] shape={edges.shape}  years={edges.year.min()}–{edges.year.max()}")
    global_records, country_records, comm_records = [], [], []
    prev_edges: set | None = None

    for year, ydf in edges.groupby("year"):
        t = time.time()
        gr, cr, mr, curr = compute_year(int(year), ydf, prev_edges)
        prev_edges = curr
        global_records.append(gr)
        country_records.extend(cr)
        comm_records.extend(mr)
        print(f"  {year}  n={gr['n_nodes']:>3}  e={gr['n_edges']:>6}  "
              f"dens={gr['density']:.3f}  mod={gr['modularity_louvain']:.3f}  "
              f"comm={gr['n_communities']:>2}  RC20={gr['rich_club_top20']:.3f}  "
              f"HHI={gr['hhi_out_strength']:.4f}  Jac={gr['jaccard_vs_prev']:.3f}  "
              f"dt={time.time()-t:4.1f}s")

    pd.DataFrame(global_records).to_csv(out_global, index=False, float_format="%.6f")
    pd.DataFrame(country_records).to_csv(out_country, index=False, float_format="%.6f")
    pd.DataFrame(comm_records).to_csv(out_comm, index=False)
    print(f"[saved] {out_global.name}  {out_country.name}  {out_comm.name}")


def main() -> None:
    print(f"[load] {EDGES.name}")
    edges = pd.read_parquet(EDGES)
    run_long_run(edges, OUT_GLOBAL, OUT_COUNTRY, OUT_COMM, label="aggregate")


if __name__ == "__main__":
    main()
