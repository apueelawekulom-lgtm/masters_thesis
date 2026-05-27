"""
Minimal usage example showing how sectors.py, baci_loader.py, and
gvc_depth.py fit together. Drop into 01_GVC_Measure.ipynb as cells, or
adapt as a standalone script.

Replace the placeholder paths with your actual locations:
    BACI_DIR     -> directory with BACI_HS17_Y*_V*.csv yearly files
    HS6_ISIC     -> HS6 -> ISIC4 concordance CSV (UN Stats / WITS)
    HS6_BEC      -> HS6 -> BEC concordance CSV (UN Stats)
    FVA_SHARE    -> TiVA-derived FVA shares at ISIC4 (your scrape output)
    UPSTREAMNESS -> Antras-Chor upstreamness at ISIC4 (published series)
"""

from pathlib import Path
import logging

import pandas as pd

from baci_loader import load_baci_panel, summarise_panel
from sectors import label_sector, SECTORS
from gvc_depth import (
    GVCDepthConfig,
    build_gvc_depth,
    variance_decomposition,
    face_validity_check,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# ---------------------------------------------------------------
# 1. Configure paths
# ---------------------------------------------------------------
DATA_DIR = Path("./data")
BACI_DIR = DATA_DIR / "baci"
HS6_ISIC = DATA_DIR / "concordances" / "hs17_to_isic4.csv"
HS6_BEC = DATA_DIR / "concordances" / "hs17_to_bec4.csv"
FVA_SHARE = DATA_DIR / "tiva" / "fva_share_isic4.csv"
UPSTREAMNESS = DATA_DIR / "upstreamness" / "antras_chor_isic4.csv"
PANEL_OUT = DATA_DIR / "derived" / "baci_us_imports_4sectors.parquet"

# ---------------------------------------------------------------
# 2. Load BACI panel for US imports across the four sectors
# ---------------------------------------------------------------
panel = load_baci_panel(
    baci_dir=BACI_DIR,
    years=range(2017, 2025),
    importer_iso3="USA",
    sector_filter=True,
    output_path=PANEL_OUT,
)

print(summarise_panel(panel))

# ---------------------------------------------------------------
# 3. Label each row with its sector
# ---------------------------------------------------------------
panel["sector"] = label_sector(panel["k"])
print(panel.groupby("sector", observed=True)["v"].sum())

# ---------------------------------------------------------------
# 4. Build the GVC depth measure for the HS6 universe in the panel
# ---------------------------------------------------------------
hs6_universe = panel["k"].drop_duplicates()
gvc = build_gvc_depth(
    hs6_codes=hs6_universe,
    hs6_isic_path=HS6_ISIC,
    hs6_bec_path=HS6_BEC,
    fva_share_path=FVA_SHARE,
    upstreamness_path=UPSTREAMNESS,
    config=GVCDepthConfig(
        weights=(1 / 3, 1 / 3, 1 / 3),
        fva_country="CHN",  # use China FVA as the reference
        fva_year=2020,      # latest TiVA year you have
        upstreamness_country="USA",
    ),
)

print(gvc.head())

# ---------------------------------------------------------------
# 5. Diagnostics
# ---------------------------------------------------------------
# Sector-aligned series
sector_per_hs6 = pd.Series(
    label_sector(pd.Series(gvc.index)),
    index=gvc.index,
    name="sector",
)

# Variance decomposition: how much variance is within vs between sectors?
print("\nVariance decomposition of GVC depth across the 4 sectors:")
print(variance_decomposition(gvc, sector_per_hs6))

# Face validity: do canonical HS6 codes order in the expected way?
print("\nFace validity check on canonical HS6 codes:")
print(face_validity_check(gvc))

# ---------------------------------------------------------------
# 6. Merge GVC depth back onto the trade panel
# ---------------------------------------------------------------
panel = panel.merge(
    gvc[["fva_share", "upstreamness", "gvc_depth_z", "gvc_tier"]],
    left_on="k",
    right_index=True,
    how="left",
)

# Save the enriched panel
enriched_path = DATA_DIR / "derived" / "baci_us_imports_4sectors_with_gvc.parquet"
panel.to_parquet(enriched_path, index=False)
print(f"\nEnriched panel written to {enriched_path}")
