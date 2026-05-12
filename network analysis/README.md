# Network Analysis — Trade-War Restructuring & GVC Resilience

Preliminary network analysis of the global trade network around the US–China
trade war (2018–2019) and its aftermath, focusing on:
1. Whether and how US imports of tariffed products diverted away from China toward
   "connector" countries (friend-shoring).
2. Whether the structural resilience of the global trade network changed
   during the trade-war era — at the aggregate level and at the product-stage level.

**A 21-page write-up of the full analysis is in
[`thesis_preliminary_analysis.pdf`](thesis_preliminary_analysis.pdf). Read that
first** — it explains the design, walks through each phase, and includes all
limitations and definitions of network-theoretic terms.

---

## What's in here

### Pipeline / build scripts (run in this order)

| Script | What it does |
|---|---|
| `build_baci_artifacts.py` | Stream the 30 per-year BACI parquets into one combined panel + country edges (`baci_combined.parquet`, `baci_edges_country.parquet`). |
| `build_plaid_edges.py` | Merge PLAID at HS4, produce BEC / Rauch / microchip stratified edge lists. |
| `build_tariff_master.py` | Pivot the FGKK `z_usch_w` tariff data; merge with PLAID. |
| `build_tariff_edges.py` | Partition BACI flows by tariff treatment status (binary + 4-bucket). |
| `build_semi_edges.py` | Narrow HS 8541+8542 semiconductor filter. |

### Analysis scripts

| Script | What it does |
|---|---|
| `long_run_network_metrics.py` | Core: annual density, modularity, Louvain communities, centralities, HHI, Jaccard. Exposes `run_long_run()`. |
| `long_run_metrics_by_bec.py` | Same on intermediate / capital / consumption subnetworks. |
| `long_run_metrics_semi.py` | Same on the narrow semiconductor subnetwork. |
| `long_run_metrics_tariff.py` | Same on tariff strata (treated / untreated, 4 buckets). |
| `long_run_metrics_microchip.py` | (Legacy) on PLAID's broad microchip flag. Superseded by `long_run_metrics_semi.py`. |
| `resilience_aggregate.py` | Network resilience pipeline (k-core, λ₂, targeted attack, disparity-filter backbone). Exposes `run_resilience()`. |
| `resilience_by_subnetwork.py` | Same on each BEC stage and on the semiconductor subnetwork. |
| `tables_friendshoring.py` | Produces the two friend-shoring summary tables in `tables/`. |

### Visualization scripts

| Script | Output figures |
|---|---|
| `viz_bec_comparison.py` | `fig1`–`fig5` (BEC stratification, country panels, semi focus). |
| `viz_added_value.py` | `fig6`–`fig8` (composition stack, specialization heatmap, share divergence). |
| `viz_tariff_strata.py` | `fig9`–`fig10` (tariff-stratum metrics, country panels). |
| `viz_friendshoring_hs6.py` | `fig11`–`fig12` (aggregate-vs-BEC, connector source mix). |
| `viz_resilience.py` | `fig13`–`fig16` (aggregate resilience). |
| `viz_resilience_compare.py` | `fig17`–`fig18` (resilience compare across subnetworks). |

### Exploratory notebooks

- `baci_analysis.ipynb` — initial BACI inspection and pipeline draft.
- `baci_network_analysis.ipynb` — first-pass network metrics.

### Other

- `fdva_network.py` — OECD TiVA FDVA network visualization (single-year, cached).
- `thesis_preliminary_analysis.tex` / `.pdf` — full 21-page write-up.
- `figures/` — 18 figures referenced in the write-up.
- `tables/` — friend-shoring summary tables (CSV).

---

## How to reproduce

**The raw data is not in this repo** (the BACI per-year files + the combined
parquet exceed GitHub's file-size limits). To reproduce:

1. **Download BACI HS92 V202601** from CEPII
   ([download page](https://www.cepii.fr/CEPII/en/bdd_modele/bdd_modele_item.asp?id=37)).
   Put the 30 per-year CSVs in `BACI_HS92_V202601/` **alongside the scripts**
   (the scripts use `Path(__file__).parent / "BACI_HS92_V202601"`).

2. **Place PLAID v0.1** (the five `PLAID_v0.1_*_H6.csv` files) in
   `PLAID Indicator/` alongside the scripts.

3. **Place the FGKK 2023 tariff files** `chn_hs6_tariffs_weighted.dta` and
   `z_usch_w.dta` in `Tariffs US:CHina/` alongside the scripts.

4. **Build the artifacts** (one-time, ~10 minutes total):
   ```bash
   python build_baci_artifacts.py
   python build_plaid_edges.py
   python build_tariff_master.py
   python build_tariff_edges.py
   python build_semi_edges.py
   ```

5. **Run any analysis or visualization script**:
   ```bash
   python long_run_network_metrics.py
   python long_run_metrics_by_bec.py
   python resilience_aggregate.py
   python viz_bec_comparison.py
   # ... etc.
   ```

Tested with Python 3.13 (Anaconda). Required packages: `pandas`, `pyarrow`,
`networkx`, `matplotlib`, `scipy`. No additional packages beyond a standard
scientific-Python stack.

---

## Methodological caveat (important)

Trade flows in BACI are **gross**, not value-added. When this analysis
partitions trade by BEC stage (intermediate / capital / consumption) and
calls the intermediate subnetwork the "GVC-flavoured" view, it is a
**product-stage partition of gross trade**, not a value-added decomposition.

A finished Vietnamese laptop shipped to the USA shows as $200 of Vietnam→USA
trade. If half that laptop's value-added is in fact a Korean chip embedded in
it, BACI cannot tell us — that requires OECD TiVA / ICIO. The PDF write-up
discusses this in detail and is explicit about what can and cannot be
defensibly concluded.

---

## Key findings (one-paragraph summary)

The aggregate trade network is remarkably structurally robust and was not
degraded by the trade war by any classical resilience measure. **But the
aggregate hides stage-dependent fragility**: the semiconductor subnetwork is
an order of magnitude more fragile than the aggregate, and the capital-goods
subnetwork is the second-most-fragile. US imports of tariffed products did
shift away from China (−$24B, −6.1 pp aggregate share, 2017→2024), with the
gains absorbed by Mexico, Korea, Vietnam, and Taiwan. The friend-shoring
signature differs by country: **Vietnam looks transshipment-flavoured**
(China's share of Vietnam's intermediate imports of tariffed products grew
from 30% to 43%); **Mexico looks more relocation-flavoured** (intermediate
base remains US/EU-anchored, China share rose only modestly).

See the PDF for the full argument and the per-stage breakdowns.
