# Masters Thesis — TSI Semiconductor Analysis

**Applying the HS6 Transformation Stage Indicator (TSI) to semiconductor value chains: operationalisation, hypotheses, and econometric design.**

> This repo uses a three-chapter structure. Each chapter owns its own data, notebooks, and outputs. Raw data is never modified in place.

---

## Table of contents

1. [Project structure](#1-project-structure)
2. [First-time setup](#2-first-time-setup)
3. [Data conventions — read this before adding any files](#3-data-conventions)
4. [Chapter overview](#4-chapter-overview)
5. [Notebook naming convention](#5-notebook-naming-convention)
6. [Working on the project — daily workflow](#6-working-on-the-project)
7. [Branch and pull request rules](#7-branch-and-pull-request-rules)
8. [What never goes in Git](#8-what-never-goes-in-git)
9. [Key file locations quick reference](#9-key-file-locations-quick-reference)
10. [Contact and resources](#10-contact-and-resources)

---

## 1. Project structure

```
masters_thesis/
│
├── data/                        ← shared raw BACI downloads (all chapters read from here)
│   ├── raw/                     ← original files — NEVER edit these
│   ├── interim/                 ← partially cleaned cross-chapter data
│   └── processed/               ← final merged panel used across chapters
│
├── econometrics/                ← Chapter 3: stage-selective decoupling regressions
│   ├── data/
│   │   ├── raw/                 ← USITC Section 301 tariff lists, Chinese retaliation schedules
│   │   ├── interim/             ← concordances, crosswalks
│   │   └── processed/           ← regression-ready panels
│   ├── notebooks/               ← Jupyter notebooks (see naming convention below)
│   ├── src/                     ← reusable .py scripts imported by notebooks
│   └── outputs/
│       ├── tables/              ← regression tables (.tex, .csv)
│       └── figures/
│
├── networks/                    ← Chapter 4: semiconductor trade network analysis
│   ├── data/
│   │   ├── raw/                 ← bilateral edge lists from BACI
│   │   ├── interim/
│   │   └── processed/           ← filtered network panels
│   ├── notebooks/
│   ├── src/
│   └── outputs/
│       ├── figures/             ← network visualisations
│       └── centrality/          ← centrality_metrics.csv etc.
│
├── nli/                         ← Chapter 2: TSI classifier (NLI pipeline)
│   ├── data/
│   │   ├── raw/                 ← WCO HS6 official descriptions
│   │   ├── interim/
│   │   └── processed/           ← tsi_final.csv lives here ← ALL chapters use this
│   ├── notebooks/
│   ├── src/                     ← Qwen3 NLI classifier pipeline
│   └── outputs/
│       ├── tsi_labels/          ← tsi_raw_scores.csv, bec_confusion_matrix
│       └── figures/
│
├── references/                  ← papers, annotation tools, WCO docs, guidelines
├── reports/                     ← final dissertation figures and tables
│   └── figures/
│
├── config/                      ← shared configuration
│   └── paths.yaml               ← ALL file paths live here — update this, not your notebooks
│
├── src/                         ← shared utility functions used across chapters
│
├── .gitignore                   ← blocks data, .venv, caches, PDFs, .DS_Store
├── pyproject.toml               ← Python dependencies
├── uv.lock                      ← dependency lockfile
└── README.md                    ← you are here
```

---

## 2. First-time setup

### Prerequisites

- Python 3.11+ installed
- Git installed (`git --version` to check)
- [uv](https://wolke.img.univie.ac.at/documentation/general/mkdocs/uv-cheatsheet.pdf) installed for package management

### Clone and install

```bash
# 1. Clone the repo
git clone https://github.com/apueelawekulom-lgtm/masters_thesis.git
cd masters_thesis

# 2. Create the virtual environment and install dependencies
uv sync

# 3. Activate the environment
source .venv/bin/activate        # Mac / Linux
.venv\Scripts\activate           # Windows
```

### Verify your setup

```bash
python -c "import pandas; import torch; print('Setup OK')"
```

### Register the Jupyter kernel

```bash
python -m ipykernel install --user --name masters_thesis --display-name "Masters Thesis"
jupyter lab
```

> When opening a notebook, select the **Masters Thesis** kernel — not the default Python 3 kernel. This ensures you use the project's exact package versions.

---

## 3. Data conventions

> **The single most important rule: raw data is read-only. You never edit files in any `data/raw/` folder.**

### Where data lives

| Data type | Location | Notes |
|-----------|----------|-------|
| BACI trade flows (all chapters) | `data/raw/` | Shared source — download once |
| Section 301 tariff lists | `econometrics/data/raw/` | USITC concorded to HS6 |
| BIS export control lists | `econometrics/data/raw/` | 2022–2023 rules |
| WCO HS6 descriptions | `nli/data/raw/` | Input to TSI classifier |
| TSI labels (final) | `nli/data/processed/tsi_final.csv` | **Used by all three chapters** |
| Network edge lists | `networks/data/raw/` | Filtered from BACI |
| Regression-ready panels | `econometrics/data/processed/` | Output of concordance scripts |

### The flow: raw → interim → processed

```
data/raw/          ← original files, never touched
    ↓
data/interim/      ← cleaning and concordance scripts write here
    ↓
data/processed/    ← final analysis-ready files notebooks read from
```

### How to reference file paths in notebooks

Never hardcode paths. Always load from `config/paths.yaml`:

```python
import yaml
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # adjust depth for your notebook location
with open(ROOT / "config/paths.yaml") as f:
    PATHS = yaml.safe_load(f)

# Example usage
import pandas as pd
tsi = pd.read_csv(ROOT / PATHS["nli"]["tsi_final"])
baci = pd.read_parquet(ROOT / PATHS["shared"]["processed"] / "baci_semis.parquet")
```

This means if a folder is ever renamed, you update `paths.yaml` once and every notebook picks it up.

### Data is not in Git

All `data/` folders are blocked by `.gitignore`. **Share data via the project shared drive or a direct download link** — never commit CSV, parquet, or Excel files to the repo. GitHub has a 100 MB file limit and large files will break the repo.

---

## 4. Chapter overview

### NLI — TSI classifier (do this first)

Produces `tsi_final.csv` which all other chapters depend on.

- Input: WCO HS6 official descriptions (`nli/data/raw/`)
- Method: zero-shot NLI using Qwen3-Embedding over five TSI stage hypotheses
- Output: `nli/data/processed/tsi_final.csv` — columns: `hs6 | tsi_stage | entropy | main_spec`
- Validation: BEC confusion matrix (`nli/outputs/tsi_labels/bec_confusion_matrix.xlsx`)

### Econometrics — stage-selective decoupling

Tests whether US–China tariff effects differed across TSI stages S1–S5.

- Input: BACI bilateral flows + Section 301 tariff lists + `tsi_final.csv`
- Method: TWFE regression with stage × tariff interactions, event-study design
- Output: regression tables in `econometrics/outputs/tables/`

### Networks — semiconductor trade network

Maps the bilateral trade network by stage, tracks China's centrality pre/post tariffs.

- Input: BACI bilateral flows + `tsi_final.csv`
- Method: NetworkX directed weighted graphs, betweenness centrality, stage-layer views
- Output: network figures in `networks/outputs/figures/`

---

## 5. Notebook naming convention

All notebooks follow this format:

```
[number]-[initials]-[description].ipynb
```

Examples:
```
01-ae-tsi-classifier-validation.ipynb
02-ae-baci-extract-semiconductor-universe.ipynb
01-ae-baseline-regression.ipynb
```

- Number keeps notebooks in logical order within each chapter
- Initials prevent naming clashes when multiple people work in the same folder
- Description is lowercase, hyphen-separated, under 40 characters

> **Clear all cell outputs before committing a notebook.** In VS Code: `Ctrl/Cmd+Shift+P` → "Jupyter: Clear All Outputs". Large output diffs make it impossible to review what actually changed in code review.

---

## 6. Working on the project — daily workflow

```bash
# 1. Always pull before starting work
git pull

# 2. Create a branch for your work
git switch -c feature/your-description

# 3. Activate the environment
source .venv/bin/activate

# 4. Do your work, commit often with clear messages
git add econometrics/notebooks/01-ae-baseline.ipynb
git commit -m "add pre-trend test for Section 301 List 1"

# 5. Push and open a pull request
git push -u origin feature/your-description
```

### Commit message examples

```
# Good
add TSI stage labels for HS Chapter 85
fix entropy threshold for HS 8486 equipment codes
refactor BACI filter to use polars for speed
update paths.yaml with new processed panel location

# Bad
stuff
fix
wip
asdfg
```

---

## 7. Branch and pull request rules

- **Never commit directly to `main`**
- Every piece of work goes on its own branch: `feature/`, `fix/`, `data/`, `analysis/`
- Open a pull request when your branch is ready — tag a teammate for review
- PRs require at least one approval before merging
- Write a clear PR description explaining what changed and why

---

## 8. What never goes in Git

The `.gitignore` blocks these automatically, but it helps to know why:

| Blocked | Reason |
|---------|--------|
| `data/` | Files are too large (BACI is ~5GB). Share via shared drive. |
| `*.csv`, `*.parquet`, `*.xlsx` | Data files — same reason |
| `.venv/` | Virtual environment — each person runs `uv sync` to recreate it |
| `__pycache__/`, `*.pyc` | Python bytecode — auto-generated, not code |
| `.DS_Store` | Mac metadata — not relevant to the project |
| `.Rhistory`, `.RData` | R workspace files — can be hundreds of MB |
| `.ipynb_checkpoints/` | Jupyter autosave backups |
| `*.pdf` | Reference PDFs are in `references/` locally but not tracked |
| `.env` | Environment variables / API keys — never commit these |

If you accidentally stage something blocked, untrack it with:

```bash
git rm --cached path/to/file
git commit -m "untrack accidentally staged file"
```

---

## 9. Key file locations quick reference

| What you need | Where it is |
|--------------|-------------|
| All file paths | `config/paths.yaml` |
| TSI stage labels | `nli/data/processed/tsi_final.csv` |
| TSI classifier code | `nli/src/` |
| BACI loader script | `econometrics/src/baci_loader.py` |
| GVC depth scripts | `econometrics/src/gvc_depth.py`, `sectors.py` |
| Annotation guidelines | `references/Annotations/GVC Annotation Guidelines Updated.docx` |
| Annotation tool | `references/Annotations/GVC Annotation Tool w Saving.html` |
| HS revision reference | `references/HS2022 conversion...pdf` |
| Project plan | `Master_Plan.md` |
| Dependencies | `pyproject.toml` |

---

## 10. Contact and resources

### Course resources

- [Git cheat sheet](https://git-scm.com/cheat-sheet)
- [uv cheat sheet](https://wolke.img.univie.ac.at/documentation/general/mkdocs/uv-cheatsheet.pdf)
- [Cookiecutter Data Science](https://cookiecutter-data-science.drivendata.org) — project structure reference
- Mueller, Rauh & Seimon (2024) — "Introducing a global dataset on conflict forecasts and news topics." *Data & Policy, 6, e17.*

### Data sources

- [BACI trade data](https://www.cepii.fr/CEPII/en/bdd_modele/bdd_modele_item.asp?id=37) — free registration at CEPII
- [USITC Section 301 tariff lists](https://www.usitc.gov)
- [WCO HS nomenclature](https://www.wcoomd.org)
- [UN BEC Rev.5 correspondence](https://unstats.un.org)

### If something breaks

1. Check you are on the right branch: `git branch`
2. Check your environment is active: `which python` should point to `.venv/bin/python`
3. Check paths are loading from `config/paths.yaml`, not hardcoded
4. Open an issue on GitHub with the error message and which notebook/script produced it# masters_thesis
Measuring GVC's using NLP and Machine Learning Methods
