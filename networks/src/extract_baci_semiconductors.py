"""
extract_baci_semiconductors.py
─────────────────────────────────────────────────────────────────────────────
PHASE 3 — Multi-Source Trade Data Extraction  (v1)

Sources:
    Primary (2017–2024):  CEPII BACI HS2017
    Extension (2024+):    UN Comtrade (descriptive only; not for DiD ID)

Inputs:
    data/interim/semiconductor_hs6_baci_filter_v1.csv
    data/raw/semiconductor_hs6_master_v1.csv
    data/baci/BACI_HS17_Y{year}_V{version}.csv
    data/baci/country_codes_V{version}.csv
    data/comtrade/comtrade_hs17_{year}.csv  (optional; see load_comtrade)

Outputs:
    data/interim/semiconductor_trade_panel_v1.csv
    data/interim/semiconductor_trade_us_imports_v1.csv
    data/interim/baci_coverage_report_v1.csv

─────────────────────────────────────────────────────────────────────────────
MULTI-SOURCE DESIGN
─────────────────────────────────────────────────────────────────────────────
Both loaders output an identical canonical schema before entering the
concordance merge logic. Source-specific fields are preserved under
source_* naming rather than baci_* naming.

Canonical schema (source-agnostic):
    t                  — year
    i                  — exporter ISO numeric 3-digit
    j                  — importer ISO numeric 3-digit
    k                  — HS6 working join key (zero-padded string)
    trade_value_kusd   — value in thousands USD (both sources normalized)
    q                  — quantity metric tons (may be null)
    source_hs6         — raw product code from source system (immutable)
    source_system      — "BACI" | "COMTRADE"
    source_version     — release identifier (e.g. "202401", "2024-06")
    hs_revision        — "HS2017" | "HS2012" etc.

Identifier hierarchy:
    source_row_id  = t_i_j_source_hs6        source trade flow identity
    panel_row_id   = source_row_id + "_" + merge_strategy + "_" + parent_row_id
                     true unique row key; survives multi-role concordance

Analytical universes:
    exact_core     — DiD / DDD primary treatment
    exact_broad    — broader exact-product robustness
    prefix_broad   — heading-level placebo

IMPORTANT: exact_core and prefix_broad rows for the same BACI flow coexist.
NEVER aggregate trade_value across both — that double-counts.
Use panel[panel["analysis_universe"] == "exact_core"] for main specs.

Identification sample note:
    2017–2024: BACI primary (harmonized mirror flows, ~1-2yr publication lag)
    2024+:     Comtrade extension (descriptive only; mirror reconciliation
               has not occurred; use with explicit caveat in paper)
─────────────────────────────────────────────────────────────────────────────
"""

import pandas as pd
import numpy as np
import os
import glob
from pathlib import Path

# =============================================================================
# CONFIGURATION
# =============================================================================

BASE         = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION      = "v1"
BACI_VERSION = "202401"

# Identification sample: BACI only
BACI_YEAR_START = 2017
BACI_YEAR_END   = 2024

# Extension sample: Comtrade (descriptive only)
COMTRADE_YEAR_START = 2025
COMTRADE_YEAR_END   = 2025
USE_COMTRADE_EXTENSION = False   # set True when Comtrade files are available


# BACI COUNTRY CODE NOTE
# BACI V202601 uses a CEPII/UN-style classification that deviates from
# ISO 3166-1 numeric codes. Do NOT substitute hardcoded ISO values.
# Always derive mappings from country_codes_V{version}.csv.
#
# Confirmed deviations in V202601:
#   842 = USA        (ISO standard: 840)
#   699 = India      (ISO standard: 356)
#   490 = Other Asia, nes  (residual — Taiwan-dominated in semiconductor trade)
#   Taiwan (TWN/158) not separately listed; appears via code 490
USA_CODE = 842   # BACI code, not ISO 840
CHN_CODE = 156   # standard; confirmed in country_codes_V202601.csv
EXTRACT_ALL_COUNTRIES = False

# =============================================================================
# PATHS
# =============================================================================

FILTER_PATH  = os.path.join(BASE, "data", "interim",
                             f"semiconductor_hs6_baci_filter_{VERSION}.csv")
MASTER_PATH  = os.path.join(BASE, "data", "raw",
                             f"semiconductor_hs6_master_{VERSION}.csv")
BACI_DIR     = os.path.join(BASE, "data", "baci")
COMTRADE_DIR = os.path.join(BASE, "data", "comtrade")
OUT_PANEL    = os.path.join(BASE, "data", "interim",
                             f"semiconductor_trade_panel_{VERSION}.csv")
OUT_PANEL_PQ = os.path.join(BASE, "data", "interim",
                             f"semiconductor_trade_panel_{VERSION}.parquet")
OUT_US       = os.path.join(BASE, "data", "interim",
                             f"semiconductor_trade_us_imports_{VERSION}.csv")
OUT_US_PQ    = os.path.join(BASE, "data", "interim",
                             f"semiconductor_trade_us_imports_{VERSION}.parquet")
OUT_COVERAGE = os.path.join(BASE, "data", "interim",
                             f"baci_coverage_report_{VERSION}.csv")

os.makedirs(os.path.join(BASE, "data", "interim"),  exist_ok=True)
os.makedirs(os.path.join(BASE, "data", "comtrade"), exist_ok=True)

# =============================================================================
# CANONICAL SCHEMA
# =============================================================================

CANONICAL_COLS = [
    "t", "i", "j", "k", "trade_value_kusd", "q",
    "source_hs6", "source_system", "source_version", "hs_revision",
]

EXPECTED_COLUMNS = CANONICAL_COLS + [
    # Identifiers
    "source_row_id", "panel_row_id",
    # Derived values
    "trade_value_usd", "ln_trade_value",
    # Concordance lineage
    "row_uid", "parent_row_id", "merge_strategy_applied",
    "matched_hs4_prefix", "description_clean", "step", "role",
    "semiconductor_layer", "ita_colour", "strategic_subset_flag",
    "expansion_type", "merge_strategy", "typo_remapped",
    # Granularity flags
    "is_exact_product", "is_prefix_expansion",
    # Country labels and ISO3
    "exporter_name", "importer_name",
    "exporter_iso3", "importer_iso3",
    # Network node identifiers (Phase 4 inputs)
    "country_stage_node", "country_product_node",
    # Treatment variables
    "post2018", "tariff_period", "trade_flow", "china_to_us",
    # Identification sample flag
    "identification_sample",
    # Source precedence
    "source_priority",
    # Analysis
    "analysis_universe",
    "safe_aggregate_flag",
    # Regression identifiers
    "pair_id",
    "pair_product_id",
    # Dataset provenance
    "dataset_version",
]

# =============================================================================
# HELPERS
# =============================================================================

def safe_sum(x):
    """Sum a series, returning NaN if ALL values are missing.
    Prevents q aggregation from silently converting all-NaN groups to 0.0.
    NaN = no quantity reported (distinct from 0 = reported zero quantity).
    """
    return x.sum() if x.notna().any() else np.nan


def load_iso3_map(country_codes_path=None):
    """
    Build ISO numeric → ISO3 mapping.
    Tries BACI country codes file first; falls back to hardcoded key-partner map.
    """
    if country_codes_path and os.path.exists(country_codes_path):
        df = pd.read_csv(country_codes_path)
        # BACI country files vary in column naming
        code_col = "country_code" if "country_code" in df.columns else df.columns[0]
        iso3_col = next((c for c in df.columns
                         if "iso3" in c.lower() or "iso_3" in c.lower()), None)
        if iso3_col:
            return dict(zip(df[code_col].astype(int), df[iso3_col]))

    # Hardcoded fallback — BACI V202601 country codes (NOT ISO 3166-1 numeric)
    # Key deviations: USA=842 (ISO:840), India=699 (ISO:356)
    # Taiwan (158) absent from BACI V202601 — flows appear via code 490
    return {
        4: "AFG", 8: "ALB", 12: "DZA", 24: "AGO", 32: "ARG",
        36: "AUS", 40: "AUT", 50: "BGD", 56: "BEL", 64: "BTN",
        76: "BRA", 100: "BGR", 116: "KHM", 124: "CAN", 144: "LKA",
        152: "CHL", 156: "CHN", 170: "COL", 191: "HRV",
        196: "CYP", 203: "CZE", 208: "DNK", 231: "ETH", 233: "EST",
        246: "FIN", 250: "FRA", 276: "DEU", 300: "GRC", 344: "HKG",
        348: "HUN", 356: "IND", 360: "IDN", 372: "IRL", 376: "ISR",
        380: "ITA", 392: "JPN", 398: "KAZ", 404: "KEN", 408: "PRK",
        410: "KOR", 418: "LAO", 428: "LVA", 440: "LTU", 442: "LUX",
        446: "MAC", 458: "MYS", 484: "MEX", 490: "S19", 504: "MAR",
        528: "NLD", 554: "NZL", 566: "NGA", 578: "NOR", 586: "PAK",
        604: "PER", 608: "PHL", 616: "POL", 620: "PRT", 642: "ROU",
        643: "RUS", 682: "SAU", 699: "IND", 702: "SGP", 703: "SVK",
        704: "VNM", 705: "SVN", 710: "ZAF", 724: "ESP", 752: "SWE",
        756: "CHE", 764: "THA", 792: "TUR", 804: "UKR", 826: "GBR",
        842: "USA", 858: "URY", 414: "KWT", 784: "ARE", 634: "QAT",
    }




def standardize_trade_schema(df, source_system, source_version, hs_revision):
    """
    Enforce canonical schema on output of any source loader.
    Validates required columns, normalizes types, adds provenance.
    Both load_baci() and load_comtrade() must pass through this.
    """
    required = {"t", "i", "j", "k", "trade_value_kusd", "q",
                "source_hs6"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"standardize_trade_schema: missing columns {missing}")

    df = df.copy()
    df["k"]          = df["k"].astype(str).str.zfill(6)
    df["source_hs6"] = df["source_hs6"].astype(str).str.zfill(6)
    df["i"]          = df["i"].astype("int32")
    df["j"]          = df["j"].astype("int32")
    df["t"]          = df["t"].astype("int16")
    df["trade_value_kusd"] = pd.to_numeric(df["trade_value_kusd"],
                                            errors="coerce").fillna(0.0)
    df["q"]                = pd.to_numeric(df.get("q", np.nan),
                                            errors="coerce")
    df["source_system"]  = source_system
    df["source_version"] = source_version
    df["hs_revision"]    = hs_revision

    return df[CANONICAL_COLS]


def load_baci(baci_dir, year, baci_version, exact_codes, prefix_codes,
              us_only=True, usa_code=842, chunksize=500_000):
    """
    Load one BACI HS2017 year file; filter to semiconductor universe.
    """
    # Try direct path first
    filepath = os.path.join(baci_dir, f"BACI_HS17_Y{year}_V{baci_version}.csv")
    
    # If not found, try year-specific subdirectory
    if not os.path.exists(filepath):
        year_dir = os.path.join(baci_dir, f"BACI_HS17_Y{year}_V{baci_version}")
        if os.path.exists(year_dir):
            filepath = os.path.join(year_dir, f"BACI_HS17_Y{year}_V{baci_version}.csv")
    
    # Fallback to glob pattern (recursive search in nested folders)
    if not os.path.exists(filepath):
        matches = glob.glob(
            os.path.join(baci_dir, f"**/BACI_HS17_Y{year}_V*.csv"),
            recursive=True
        )
        if not matches:
            return None
        filepath = sorted(matches)[-1]
        used_version = Path(filepath).stem.split("_V")[-1]
    else:
        used_version = baci_version

    print(f"  {year} [BACI V{used_version}]...", end=" ", flush=True)
    chunks_exact  = []
    chunks_prefix = []

    for chunk in pd.read_csv(
            filepath, chunksize=chunksize,
            dtype={"k": str, "i": "int32", "j": "int32",
                   "t": "int16", "v": float, "q": float}):

        chunk["k"]          = chunk["k"].str.zfill(6)
        chunk["source_hs6"] = chunk["k"]
        chunk               = chunk.rename(columns={"v": "trade_value_kusd"})

        # Filter to semiconductor codes FIRST (before country filter)
        chunk["hs4"] = chunk["k"].str[:4]
        is_exact  = chunk["k"].isin(exact_codes)
        is_prefix = chunk["hs4"].isin(prefix_codes)
        chunk = chunk[is_exact | is_prefix].copy()
        if len(chunk) == 0:
            continue

        # THEN filter to US imports
        if us_only:
            chunk = chunk[chunk["j"] == usa_code]
        if len(chunk) == 0:
            continue

        # Assign merge strategy
        ex = chunk[chunk["k"].isin(exact_codes)].copy()
        if len(ex):
            ex["merge_strategy_applied"] = "exact_hs6"
            ex["matched_hs4_prefix"]     = None
            chunks_exact.append(ex)

        pf = chunk[chunk["hs4"].isin(prefix_codes)].copy()
        if len(pf):
            pf["matched_hs4_prefix"]     = pf["hs4"]
            pf["merge_strategy_applied"] = "hs4_prefix"
            chunks_prefix.append(pf.drop(columns=["hs4"]))

    if not chunks_exact and not chunks_prefix:
        print("0 rows")
        return pd.DataFrame(columns=CANONICAL_COLS + [
            "merge_strategy_applied", "matched_hs4_prefix"])

    parts = (
        ([pd.concat(chunks_exact,  ignore_index=True)] if chunks_exact  else []) +
        ([pd.concat(chunks_prefix, ignore_index=True)] if chunks_prefix else [])
    )
    result = pd.concat(parts, ignore_index=True)

    before = len(result)
    result = result.drop_duplicates(
        subset=["t", "i", "j", "k", "matched_hs4_prefix"]
    ).reset_index(drop=True)
    dropped = before - len(result)

    n_ex = (result["merge_strategy_applied"] == "exact_hs6").sum()
    n_pf = (result["merge_strategy_applied"] == "hs4_prefix").sum()
    print(f"{len(result):>8,} rows  "
          f"(exact={n_ex:,}  prefix={n_pf:,}  dedup_dropped={dropped}  "
          f"exporters={result['i'].nunique()})")

    strategy_cols = result[["merge_strategy_applied","matched_hs4_prefix"]].copy()
    canonical     = standardize_trade_schema(
        result, "BACI", used_version, "HS2017")
    return pd.concat([canonical, strategy_cols], axis=1)


def load_comtrade(comtrade_dir, year, exact_codes, prefix_codes,
                  us_only=True, usa_code=842, chunksize=500_000):
    """
    Load UN Comtrade bulk download file for one year.
    Returns canonical schema DataFrame.

    Comtrade specifics vs BACI:
        primaryValue  = trade value in USD (NOT thousands → divide by 1000)
        netWgt        = weight in kg (NOT metric tons → divide by 1000)
        reporterCode  = reporting country (ISO numeric)
        partnerCode   = partner country (ISO numeric)
        cmdCode       = HS product code
        flowCode      = "M" (imports) | "X" (exports)
        Mirror flows NOT reconciled — use reporter=importer for imports

    Directionality note:
        For US imports: filter reporterCode == usa_code AND flowCode == "M"
        Do NOT invert reporter/partner for consistency with BACI (i=exporter,
        j=importer). Set i=partnerCode, j=reporterCode after filtering.

    File naming convention (adjust to your downloaded format):
        comtrade_hs17_{year}.csv
        OR comtrade_hs17_{year}.parquet

    HS revision note:
        Comtrade may report in HS2017 or HS2022 depending on country/year.
        Check the classificationCode column; filter to "H5" (HS2017) or
        "H6" (HS2022) and apply crosswalk if needed.
    """
    fname_csv     = os.path.join(comtrade_dir, f"comtrade_hs17_{year}.csv")
    fname_parquet = os.path.join(comtrade_dir, f"comtrade_hs17_{year}.parquet")

    if os.path.exists(fname_parquet):
        raw = pd.read_parquet(fname_parquet)
        filepath = fname_parquet
    elif os.path.exists(fname_csv):
        raw = pd.read_csv(fname_csv, dtype={"cmdCode": str}, chunksize=chunksize)
        filepath = fname_csv
    else:
        print(f"  {year} [Comtrade]: file not found — skipping")
        return None

    print(f"  {year} [Comtrade]...", end=" ", flush=True)

    def process_comtrade_chunk(chunk):
        chunk = chunk.copy()

        # Standardize column names across Comtrade API versions
        col_map = {
            "reporterCode": "reporterCode",
            "reporter_code": "reporterCode",
            "partnerCode":  "partnerCode",
            "partner_code": "partnerCode",
            "cmdCode":      "cmdCode",
            "cmd_code":     "cmdCode",
            "primaryValue": "primaryValue",
            "primary_value":"primaryValue",
            "netWgt":       "netWgt",
            "net_wgt":      "netWgt",
            "flowCode":     "flowCode",
            "flow_code":    "flowCode",
            "period":       "t",
        }
        chunk = chunk.rename(columns={
            k: v for k, v in col_map.items() if k in chunk.columns})

        # Filter: imports only + US as reporter (if us_only)
        chunk = chunk[chunk["flowCode"].isin(["M", "Import", "imports"])]
        if us_only:
            chunk = chunk[chunk["reporterCode"].astype(int) == usa_code]
        if len(chunk) == 0:
            return pd.DataFrame()

        chunk["cmdCode"] = chunk["cmdCode"].astype(str).str.zfill(6)

        # Mandatory HS revision filter — prevents HS2022 rows contaminating
        # a HS2017-concordance pipeline. A single leaked row corrupts:
        # concordance joins, tariff joins, network centrality, time continuity.
        # H5 = HS2017, H6 = HS2022 in Comtrade classificationCode convention
        ALLOWED_HS_REVISIONS = {"H5"}   # update if pipeline migrates to HS2022
        if "classificationCode" in chunk.columns:
            before_rev = len(chunk)
            chunk = chunk[chunk["classificationCode"].isin(ALLOWED_HS_REVISIONS)]
            dropped_rev = before_rev - len(chunk)
            if dropped_rev:
                print(f"\n  [HS filter] dropped {dropped_rev} non-HS2017 rows "
                      f"(classificationCode not in {ALLOWED_HS_REVISIONS})")
            if len(chunk) == 0:
                return pd.DataFrame()   # all rows were wrong revision

        # Filter to semiconductor universe
        is_exact  = chunk["cmdCode"].isin(exact_codes)
        chunk["hs4"] = chunk["cmdCode"].str[:4]
        is_prefix = chunk["hs4"].isin(prefix_codes)
        chunk = chunk[is_exact | is_prefix].copy()
        if len(chunk) == 0:
            return pd.DataFrame()

        # Assign merge strategy
        chunk["merge_strategy_applied"] = np.where(
            chunk["cmdCode"].isin(exact_codes), "exact_hs6", "hs4_prefix")
        chunk["matched_hs4_prefix"] = np.where(
            chunk["merge_strategy_applied"] == "hs4_prefix",
            chunk["hs4"], None)

        # Normalize to canonical BACI-aligned fields
        # i = exporter (partner), j = importer (reporter)
        chunk["i"]          = chunk["partnerCode"].astype("int32")
        chunk["j"]          = chunk["reporterCode"].astype("int32")
        chunk["k"]          = chunk["cmdCode"]
        chunk["source_hs6"] = chunk["cmdCode"]
        # primaryValue is USD; convert to thousands
        chunk["trade_value_kusd"] = (
            pd.to_numeric(chunk["primaryValue"], errors="coerce") / 1000
        ).fillna(0.0)
        # netWgt is kg; convert to metric tons
        chunk["q"] = pd.to_numeric(chunk.get("netWgt", np.nan),
                                    errors="coerce") / 1000

        keep = ["t", "i", "j", "k", "trade_value_kusd", "q",
                "source_hs6", "merge_strategy_applied", "matched_hs4_prefix"]
        return chunk[[c for c in keep if c in chunk.columns]]

    # Handle chunked or full reads
    if isinstance(raw, pd.io.parsers.TextFileReader):
        parts = [process_comtrade_chunk(c) for c in raw]
        result = pd.concat([p for p in parts if len(p)], ignore_index=True)
    else:
        result = process_comtrade_chunk(raw)

    if len(result) == 0:
        print("0 rows")
        return None

    result = result.drop_duplicates(
        subset=["t", "i", "j", "k", "matched_hs4_prefix"]
    ).reset_index(drop=True)

    # Comtrade bulk files sometimes contain subannual records, revisions,
    # or transport-mode splits. Aggregate to annual before returning
    # to match BACI's annual structure and avoid arbitrary row retention.
    agg_cols = ["t", "i", "j", "k", "source_hs6",
                "merge_strategy_applied", "matched_hs4_prefix"]
    result = (result
              .groupby(agg_cols, dropna=False)
              .agg(trade_value_kusd=("trade_value_kusd", "sum"),
                   q=("q", safe_sum))
              .reset_index())

    print(f"{len(result):>8,} rows  "
          f"(exporters={result['i'].nunique()}, after annual aggregation)")

    strategy_cols = result[["merge_strategy_applied","matched_hs4_prefix"]].copy()
    canonical     = standardize_trade_schema(
        result, "COMTRADE", "bulk", "HS2017")
    return pd.concat([canonical, strategy_cols], axis=1)

# =============================================================================
# STEP 1 — LOAD PHASE 2 OUTPUTS
# =============================================================================

print("=" * 70)
print("PHASE 3 — Multi-Source Semiconductor Trade Extraction")
print(f"Version: {VERSION}  |  HS: HS2017  |  BACI: V{BACI_VERSION}")
print("=" * 70)

filter_df = pd.read_csv(FILTER_PATH, dtype={"hs6_normalized": str})
filter_df["hs6_normalized"] = filter_df["hs6_normalized"].str.zfill(6)
master_df = pd.read_csv(MASTER_PATH,
                        dtype={"hs6_normalized": str, "hs4_filter": str})
print(f"\nFilter: {len(filter_df)} codes  |  Master: {len(master_df)} rows")

# =============================================================================
# STEP 2 — BUILD MERGE TABLES
# =============================================================================

exact_df = master_df[master_df["merge_strategy"] == "exact_hs6"].copy()
exact_df["hs6_normalized"] = exact_df["hs6_normalized"].str.zfill(6)

TYPO_MAP = {"868640": "848640"}
exact_df["hs6_baci"]      = exact_df["hs6_normalized"].replace(TYPO_MAP)
exact_df["typo_remapped"] = exact_df["hs6_normalized"] != exact_df["hs6_baci"]

typo_rows = exact_df[exact_df["typo_remapped"]]
if len(typo_rows):
    print(f"\nTypo remapping: {len(typo_rows)} code(s)")
    for _, r in typo_rows.iterrows():
        print(f"  {r['hs6_normalized']} → {r['hs6_baci']}  "
              f"(parent_row_id={r['parent_row_id']})")

dup_381800 = exact_df[exact_df["hs6_baci"] == "381800"]
if len(dup_381800) > 1:
    exact_df = exact_df[
        ~((exact_df["hs6_baci"] == "381800") & (exact_df["step"] == 1))
    ].reset_index(drop=True)
    print("381800: Step 1 row removed; Step 2 retained")

exact_df = (exact_df
            .sort_values("typo_remapped")
            .drop_duplicates(subset="hs6_baci", keep="first")
            .reset_index(drop=True))

exact_codes = set(exact_df["hs6_baci"].tolist())
assert exact_df["hs6_baci"].is_unique, "exact_df not unique"
print(f"\nexact_hs6 codes:  {len(exact_codes)}")

prefix_df = master_df[
    (master_df["merge_strategy"] == "hs4_prefix") &
    (master_df["expansion_type"] != "hs4_already_listed")
].copy()
prefix_df["hs4_filter"] = prefix_df["hs4_filter"].astype(str)
prefix_codes = set(prefix_df["hs4_filter"].tolist())
assert prefix_df["hs4_filter"].is_unique, "prefix_df not unique"

for p in prefix_codes:
    if len(p) != 4 or not p.isdigit():
        raise ValueError(f"Non-4-digit prefix: '{p}'")
for p1 in prefix_codes:
    for p2 in prefix_codes:
        if p1 != p2 and p2.startswith(p1):
            raise ValueError(f"Overlapping prefixes: '{p1}' '{p2}'")

print(f"hs4_prefix codes: {len(prefix_codes)}")
print("All pre-extraction checks passed ✓")

# =============================================================================
# STEP 3 — LOCATE FILES
# =============================================================================

baci_files = {}
for year in range(BACI_YEAR_START, BACI_YEAR_END + 1):
    # Your actual structure: BACI_HS17_V{version}/ folder contains all year files
    p = os.path.join(BACI_DIR, f"BACI_HS17_V{BACI_VERSION}",
                     f"BACI_HS17_Y{year}_V{BACI_VERSION}.csv")
    if os.path.exists(p):
        baci_files[year] = p
    else:
        # Fallback to recursive glob search
        m = glob.glob(os.path.join(BACI_DIR, f"**/BACI_HS17_Y{year}_V*.csv"),
                     recursive=True)
        if m:
            baci_files[year] = sorted(m)[-1]

print(f"\nBACI files:     {len(baci_files)}/{BACI_YEAR_END - BACI_YEAR_START + 1}"
      f"  ({BACI_YEAR_START}–{BACI_YEAR_END}, identification sample)")

# [DEBUG] Check code format compatibility
print("\n[DEBUG] Checking code format compatibility...")
print(f"  Sample exact_codes: {list(exact_codes)[:5]}")
print(f"  Sample prefix_codes: {list(prefix_codes)[:5]}")

if baci_files:
    sample_baci = pd.read_csv(
        list(baci_files.values())[0],
        nrows=1000,
        dtype={"k": str}
    )
    sample_baci["k"] = sample_baci["k"].str.zfill(6)
    print(f"\n  BACI sample k values (first 10):")
    print(f"    {sample_baci['k'].unique()[:10]}")
    print(f"  Intersection with exact_codes: {len(set(sample_baci['k']) & exact_codes)}")
    print(f"  Intersection with prefix_codes: {len([x for x in sample_baci['k'].unique() if x[:4] in prefix_codes])}")

print(f"\nBACI files:     {len(baci_files)}/{BACI_YEAR_END - BACI_YEAR_START + 1}"
      f"  ({BACI_YEAR_START}–{BACI_YEAR_END}, identification sample)")

comtrade_files = {}
if USE_COMTRADE_EXTENSION:
    for year in range(COMTRADE_YEAR_START, COMTRADE_YEAR_END + 1):
        for ext in [".parquet", ".csv"]:
            p = os.path.join(COMTRADE_DIR, f"comtrade_hs17_{year}{ext}")
            if os.path.exists(p):
                comtrade_files[year] = p
                break
    print(f"Comtrade files: {len(comtrade_files)}/{COMTRADE_YEAR_END - COMTRADE_YEAR_START + 1}"
          f"  ({COMTRADE_YEAR_START}–{COMTRADE_YEAR_END}, extension sample)")
else:
    print(f"Comtrade:       disabled (USE_COMTRADE_EXTENSION=False)")

if not baci_files and not comtrade_files:
    print("\n" + "!" * 70)
    print("NO SOURCE FILES FOUND — DRY-RUN mode")
    print("!" * 70)
    print(f"\nBACI download:     https://www.cepii.fr/CEPII/en/bdd_modele/"
          f"bdd_modele_item.asp?id=37")
    print(f"Comtrade download: https://comtradeplus.un.org/")
    DRY_RUN = True
else:
    DRY_RUN = False

ctry_files = glob.glob(
    os.path.join(BACI_DIR, "**", "country_codes_V*.csv"),
    recursive=True)
countries  = None
if ctry_files:
    countries = pd.read_csv(sorted(ctry_files)[-1])
    if "country_code" not in countries.columns:
        countries.columns = ["country_code"] + list(countries.columns[1:])
    countries["country_code"] = countries["country_code"].astype(int)
    print(f"\nCountry codes: {len(countries)}")
else:
    print("\nCountry codes: not found")

# =============================================================================
# STEP 4 — EXTRACT
# =============================================================================

panels = []

if not DRY_RUN:
    if baci_files:
        mode = "US imports" if not EXTRACT_ALL_COUNTRIES else "all bilateral"
        print(f"\nExtracting BACI ({mode}):")
        for year in sorted(baci_files):
            df_y = load_baci(
                BACI_DIR, year, BACI_VERSION,
                exact_codes, prefix_codes,
                us_only=not EXTRACT_ALL_COUNTRIES,
                usa_code=USA_CODE
            )
            if df_y is not None and len(df_y):
                panels.append(df_y)

    if comtrade_files and USE_COMTRADE_EXTENSION:
        print(f"\nExtracting Comtrade extension ({mode}):")
        for year in sorted(comtrade_files):
            df_y = load_comtrade(
                COMTRADE_DIR, year,
                exact_codes, prefix_codes,
                us_only=not EXTRACT_ALL_COUNTRIES,
                usa_code=USA_CODE
            )
            if df_y is not None and len(df_y):
                panels.append(df_y)

if panels:
    panel = pd.concat(panels, ignore_index=True)
    print(f"\nCombined panel: {len(panel):,} rows  |  "
          f"Years: {panel['t'].min()}–{panel['t'].max()}  |  "
          f"Sources: {panel['source_system'].value_counts().to_dict()}")
else:
    print("\nDRY-RUN: empty panel with full expected schema.")
    panel = pd.DataFrame(columns=EXPECTED_COLUMNS)

# Create source_row_id HERE — before Step 5 dedup which depends on it
# source_system is appended to disambiguate BACI vs Comtrade same-flow rows
if len(panel) and "source_hs6" in panel.columns:
    panel["source_row_id"] = (
        panel["t"].astype(str)          + "_" +
        panel["i"].astype(str)          + "_" +
        panel["j"].astype(str)          + "_" +
        panel["source_hs6"].astype(str) + "_" +
        panel["source_system"]
    )
else:
    panel["source_row_id"] = pd.Series(dtype=str)

# =============================================================================
# STEP 5 — MERGE CONCORDANCE METADATA
# =============================================================================

print("\nMerging concordance metadata...")

META_EXACT  = ["hs6_baci", "row_uid", "description_clean", "step", "role",
               "semiconductor_layer", "ita_colour", "strategic_subset_flag",
               "expansion_type", "merge_strategy", "parent_row_id",
               "typo_remapped"]
META_PREFIX = ["hs4_filter", "row_uid", "description_clean", "step", "role",
               "semiconductor_layer", "ita_colour", "strategic_subset_flag",
               "expansion_type", "merge_strategy", "parent_row_id"]

if len(panel) and "k" in panel.columns:
    exact_meta  = exact_df[META_EXACT].rename(columns={"hs6_baci": "k"})
    prefix_meta = (prefix_df[META_PREFIX]
                   .rename(columns={"hs4_filter": "matched_hs4_prefix"}))
    prefix_meta["typo_remapped"] = False

    assert exact_meta["k"].is_unique,                       "exact_meta fan-out"
    assert prefix_meta["matched_hs4_prefix"].is_unique,     "prefix_meta fan-out"

    panel_exact = (panel[panel["merge_strategy_applied"] == "exact_hs6"]
                   .merge(exact_meta, on="k", how="left"))
    panel_exact["typo_remapped"] = (panel_exact["typo_remapped"]
                                    .fillna(False).astype(bool))

    panel_prefix = (panel[panel["merge_strategy_applied"] == "hs4_prefix"]
                    .merge(prefix_meta, on="matched_hs4_prefix", how="left"))

    panel = pd.concat([panel_exact, panel_prefix], ignore_index=True)

    before = len(panel)
    panel  = panel.drop_duplicates(
        # Source-native identity: respects source-level row semantics
        # Safer than (t,i,j,k,...) which collapses Comtrade sub-annual records
        subset=["source_row_id", "parent_row_id", "merge_strategy_applied"]
    ).reset_index(drop=True)
    if (before - len(panel)):
        print(f"  Post-merge dedup: dropped {before-len(panel)} rows")

    unmatched = panel[panel["step"].isna()]["k"].unique()
    if len(unmatched):
        print(f"  WARNING: {len(unmatched)} unmatched codes: {unmatched}")
    else:
        print("  All codes matched ✓")

# =============================================================================
# STEP 6 — ENRICH
# =============================================================================

if len(panel) and "t" in panel.columns:
    if countries is not None:
        nc   = (countries.columns[1]
                if "country_name_abbreviation" not in countries.columns
                else "country_name_abbreviation")
        ctry = countries.set_index("country_code")[nc].to_dict()
        panel["exporter_name"] = panel["i"].map(ctry)
        panel["importer_name"] = panel["j"].map(ctry)
    else:
        panel["exporter_name"] = None
        panel["importer_name"] = None

    # ISO3 country codes — needed for graph viz, regression output, publication tables
    ctry_files_all = glob.glob(
        os.path.join(BACI_DIR, "**", "country_codes_V*.csv"),
        recursive=True)
    iso3_map = load_iso3_map(sorted(ctry_files_all)[-1] if ctry_files_all else None)
    panel["exporter_iso3"] = panel["i"].map(iso3_map).fillna("UNK")
    panel["importer_iso3"] = panel["j"].map(iso3_map).fillna("UNK")

    panel["trade_value_usd"] = panel["trade_value_kusd"] * 1000
    panel["ln_trade_value"]  = np.log1p(panel["trade_value_usd"])

    panel["is_exact_product"]   = panel["merge_strategy_applied"] == "exact_hs6"
    panel["is_prefix_expansion"]= panel["merge_strategy_applied"] == "hs4_prefix"

    def tariff_period(y):
        if   y < 2018: return "0_pre_tariff"
        elif y <= 2020: return "1_episode1_301"
        elif y <= 2023: return "2_consolidation"
        else:           return "3_episode2_lead_up"

    panel["tariff_period"] = panel["t"].apply(tariff_period)
    panel["post2018"]      = (panel["t"] >= 2018).astype(int)
    panel["trade_flow"]    = np.where(
        panel["j"] == USA_CODE, "US_import", "other")
    panel["china_to_us"]   = (
        (panel["i"] == CHN_CODE) & (panel["j"] == USA_CODE))

    # Identification sample flag — critical for empirical strategy
    panel["identification_sample"] = (
        panel["source_system"] == "BACI"
    )

    # Source priority — formalizes precedence for dedup, overlap years,
    # revision reconciliation, and network snapshots
    # 1 = BACI (harmonized mirrors, primary)
    # 2 = Comtrade (reporter perspective, extension only)
    panel["source_priority"] = np.where(
        panel["source_system"] == "BACI", 1, 2
    )

    # panel_row_id created HERE (after metadata merge) because it depends on
    # parent_row_id which only exists post-concordance merge in Step 5
    panel["panel_row_id"] = (
        panel["source_row_id"] + "_" +
        panel["merge_strategy_applied"] + "_" +
        panel["parent_row_id"].astype(str)
    )

    panel["analysis_universe"] = np.select(
        [
            panel["is_exact_product"] &  panel["strategic_subset_flag"],
            panel["is_exact_product"] & ~panel["strategic_subset_flag"],
            panel["is_prefix_expansion"],
        ],
        ["exact_core", "exact_broad", "prefix_broad"],
        default="unclassified"
    )
    assert not (panel["analysis_universe"] == "unclassified").any(), \
        "Unclassified rows in analysis_universe"

    # Safe aggregation shortcut — prevents accidental cross-universe summation
    # Use this flag whenever computing descriptive trade totals
    panel["safe_aggregate_flag"] = (
        panel["analysis_universe"] == "exact_core"
    )

    # Regression convenience identifiers
    panel["pair_id"] = (
        panel["i"].astype(str) + "_" + panel["j"].astype(str))
    panel["pair_product_id"] = (
        panel["pair_id"] + "_" + panel["k"])

    # Network-ready node identifiers — direct input for Phase 4 adjacency matrices
    # country_stage_node:   exporter + chain layer  → upstream/downstream dependency
    # country_product_node: exporter + HS6           → product-level centrality
    # NOTE on S19: exporter_iso3 = "S19" for BACI code 490 ("Other Asia, nes")
    # Substantial IC flows (854231-854239) suggest Taiwan-dominated residual.
    # Use DISPLAY_LABELS["S19"] = "Other Asia (Taiwan-dominated)" in figures only.
    # Raw "S19" preserved unchanged in analytical dataset and regressions.
    panel["country_stage_node"]   = (
        panel["exporter_iso3"] + "_" + panel["semiconductor_layer"].astype(str))
    panel["country_product_node"] = (
        panel["exporter_iso3"] + "_" + panel["k"])

    panel["dataset_version"] = VERSION

    # Categorical dtypes — reduces memory significantly at BACI scale
    for col in ["source_system", "tariff_period", "analysis_universe",
                "merge_strategy_applied", "trade_flow", "hs_revision"]:
        if col in panel.columns:
            panel[col] = panel[col].astype("category")

# =============================================================================
# STEP 7 — INTEGRITY CHECKS
# =============================================================================

if len(panel) and "k" in panel.columns:
    print("\nRunning integrity checks...")

    assert panel["source_system"].notna().all(),     "source_system has nulls"
    assert panel["source_row_id"].notna().all(),     "source_row_id has nulls"
    assert panel["panel_row_id"].notna().all(),      "panel_row_id has nulls"
    assert panel["panel_row_id"].is_unique,          "panel_row_id not unique"
    assert panel["trade_value_kusd"].ge(0).all(),    "Negative trade_value_kusd"
    assert panel["trade_value_usd"].notna().all(),   "trade_value_usd has nulls"
    assert panel["ln_trade_value"].notna().all(),    "ln_trade_value has nulls"
    assert (panel["trade_value_usd"] >= panel["trade_value_kusd"]).all(), \
        "Unit conversion inverted"
    assert panel["k"].str.len().eq(6).all(),         "Non-6-digit k codes"
    assert panel["row_uid"].notna().all(),            "row_uid has nulls"
    assert not (panel["is_exact_product"] & panel["is_prefix_expansion"]).any(), \
        "Row is both exact and prefix"
    assert not (panel["analysis_universe"] == "unclassified").any(), \
        "Unclassified analysis_universe"
    assert set(panel["analysis_universe"].unique()) <= {
        "exact_core", "exact_broad", "prefix_broad"}, \
        "Unexpected analysis_universe category"
    assert panel["pair_product_id"].notna().all(),   "pair_product_id has nulls"
    assert panel["dataset_version"].eq(VERSION).all(), "dataset_version mismatch"
    # Redundant with is_unique but explicit — guards against future refactors
    assert panel.groupby("panel_row_id").size().max() == 1, \
        "panel_row_id duplicates found"

    print("  source_system not-null     ✓")
    print("  source_row_id not-null     ✓")
    print("  panel_row_id unique        ✓")
    print("  trade_value_kusd >= 0      ✓")
    print("  trade_value_usd not-null   ✓")
    print("  ln_trade_value not-null    ✓")
    print("  unit conversion valid      ✓")
    print("  k is 6-digit               ✓")
    print("  row_uid not-null           ✓")
    print("  exact/prefix mutually excl ✓")
    print("  analysis_universe valid    ✓")
    print("  analysis_universe no drift ✓")
    print("  pair_product_id not-null   ✓")
    print("  dataset_version matches    ✓")
    print("  panel_row_id no dupes      ✓")

# =============================================================================
# STEP 8 — COVERAGE REPORT
# =============================================================================

print("\nBuilding coverage report...")
cov_rows = []

for code in sorted(exact_codes):
    m_rows = exact_df[exact_df["hs6_baci"] == code]
    if not len(m_rows):
        continue
    m = m_rows.iloc[0]
    sub = (panel[(panel["k"] == code) & panel["is_exact_product"]]
           if len(panel) and "k" in panel.columns else pd.DataFrame())
    by_src = sub.groupby("source_system")["trade_value_kusd"].sum().to_dict() \
             if len(sub) else {}
    cov_rows.append({
        "universe":            "exact_hs6",
        "code":                code,
        "description_clean":   m.get("description_clean", ""),
        "step":                m.get("step", ""),
        "semiconductor_layer": m.get("semiconductor_layer", ""),
        "strategic_subset_flag": m.get("strategic_subset_flag", False),
        "ita_colour":          m.get("ita_colour", ""),
        "typo_remapped":       m.get("typo_remapped", False),
        "in_baci":             bool(by_src.get("BACI", 0)),
        "in_comtrade":         bool(by_src.get("COMTRADE", 0)),
        "n_years":             len(sub["t"].unique()) if len(sub) else 0,
        "total_value_kusd_baci":     round(by_src.get("BACI", 0.0), 0),
        "total_value_kusd_comtrade": round(by_src.get("COMTRADE", 0.0), 0),
        "n_hs6_children": None,
    })

for prefix in sorted(prefix_codes):
    m_rows = prefix_df[prefix_df["hs4_filter"] == prefix]
    if not len(m_rows):
        continue
    m = m_rows.iloc[0]
    sub = (panel[(panel["matched_hs4_prefix"] == prefix) &
                 panel["is_prefix_expansion"]]
           if len(panel) and "matched_hs4_prefix" in panel.columns
           else pd.DataFrame())
    by_src = sub.groupby("source_system")["trade_value_kusd"].sum().to_dict() \
             if len(sub) else {}
    cov_rows.append({
        "universe":            "hs4_prefix",
        "code":                prefix,
        "description_clean":   m.get("description_clean", ""),
        "step":                m.get("step", ""),
        "semiconductor_layer": m.get("semiconductor_layer", ""),
        "strategic_subset_flag": m.get("strategic_subset_flag", False),
        "ita_colour":          m.get("ita_colour", ""),
        "typo_remapped":       False,
        "in_baci":             bool(by_src.get("BACI", 0)),
        "in_comtrade":         bool(by_src.get("COMTRADE", 0)),
        "n_years":             len(sub["t"].unique()) if len(sub) else 0,
        "total_value_kusd_baci":     round(by_src.get("BACI", 0.0), 0),
        "total_value_kusd_comtrade": round(by_src.get("COMTRADE", 0.0), 0),
        "n_hs6_children":      sub["k"].nunique() if len(sub) else 0,
    })

coverage = pd.DataFrame(cov_rows)
if len(coverage):
    print(f"  exact_hs6  in_baci: "
          f"{coverage[coverage['universe']=='exact_hs6']['in_baci'].sum()}"
          f"/{(coverage['universe']=='exact_hs6').sum()}")
    print(f"  hs4_prefix in_baci: "
          f"{coverage[coverage['universe']=='hs4_prefix']['in_baci'].sum()}"
          f"/{(coverage['universe']=='hs4_prefix').sum()}")

# =============================================================================
# STEP 9 — SUMMARY
# =============================================================================

if len(panel) > 0 and "trade_value_kusd" in panel.columns:
    print("\n" + "=" * 70)
    print("EXTRACTION SUMMARY  (exact_core universe; avoids double-counting)")
    print("=" * 70)

    p_id = panel[panel["analysis_universe"] == "exact_core"]

    print(f"\nIdentification sample (BACI only):")
    p_baci = p_id[p_id["source_system"] == "BACI"]
    print(f"  {len(p_baci):,} rows  |  ${p_baci['trade_value_kusd'].sum()/1e6:,.1f}B  "
          f"|  {p_baci['t'].min() if len(p_baci) else 'N/A'}–"
          f"{p_baci['t'].max() if len(p_baci) else 'N/A'}")

    p_ct = p_id[p_id["source_system"] == "COMTRADE"]
    if len(p_ct):
        print(f"Extension sample (Comtrade, descriptive only):")
        print(f"  {len(p_ct):,} rows  |  ${p_ct['trade_value_kusd'].sum()/1e6:,.1f}B  "
              f"|  {p_ct['t'].min()}–{p_ct['t'].max()}")

    print("\nBy tariff period (BACI identification sample):")
    for p, grp in p_baci.groupby("tariff_period"):
        val = grp["trade_value_kusd"].sum()
        print(f"  {p:<28} ${val/1e6:>10,.1f}B  ({len(grp):,} rows)")

    print("\nChina → US (BACI):")
    for p, val in p_baci[p_baci["china_to_us"]].groupby(
            "tariff_period")["trade_value_kusd"].sum().items():
        print(f"  {p:<28} ${val/1e6:,.1f}B")

    # ── Diagnostic 1: Top exporters by total value ───────────────────────────
    print("\nTop exporters to US — exact_core (all years):")
    top_exp = (p_baci.groupby(["i","exporter_iso3"])["trade_value_kusd"]
               .sum().sort_values(ascending=False).head(15))
    total_ex = p_baci["trade_value_kusd"].sum()
    for (code, iso3), val in top_exp.items():
        share = val / total_ex * 100
        print(f"  {int(code):4d}  {str(iso3):<6}  ${val/1e6:>7.1f}B  ({share:4.1f}%)")

    # ── Diagnostic 2: Top exporters for key IC products ──────────────────────
    for k_code, k_desc in [("854231","Processors/controllers"),
                            ("854232","Memories"),
                            ("854239","Other ICs")]:
        sub_k = p_baci[p_baci["k"] == k_code]
        if not len(sub_k):
            continue
        print(f"\nTop exporters — {k_code} ({k_desc}):")
        top_k = (sub_k.groupby(["i","exporter_iso3"])["trade_value_kusd"]
                 .sum().sort_values(ascending=False).head(8))
        tot_k = sub_k["trade_value_kusd"].sum()
        for (code, iso3), val in top_k.items():
            print(f"  {int(code):4d}  {str(iso3):<6}  ${val/1e6:>7.1f}B  "
                  f"({val/tot_k*100:4.1f}%)")

    # ── Diagnostic 3: S19 share of exact_core imports ────────────────────────
    print("\nS19 (Other Asia, Taiwan-dominated) share of exact_core by year:")
    s19_yr  = (p_baci[p_baci["exporter_iso3"]=="S19"]
               .groupby("t")["trade_value_kusd"].sum())
    tot_yr  = p_baci.groupby("t")["trade_value_kusd"].sum()
    share_yr = (s19_yr / tot_yr * 100).round(1)
    for yr in sorted(tot_yr.index):
        s19_v = s19_yr.get(yr, 0)
        tot_v = tot_yr[yr]
        sh    = share_yr.get(yr, 0)
        print(f"  {yr}  total=${tot_v/1e6:6.1f}B  "
              f"S19=${s19_v/1e6:6.1f}B  share={sh:.1f}%")

# =============================================================================
# STEP 10 — EXPORT
# =============================================================================

panel.to_csv(OUT_PANEL, index=False)
panel.to_parquet(OUT_PANEL_PQ, index=False)
print(f"\nExported: {os.path.basename(OUT_PANEL)}  ({len(panel):,} rows)")
print(f"Exported: {os.path.basename(OUT_PANEL_PQ)}  (parquet; faster for Phase 4)")

if EXTRACT_ALL_COUNTRIES and len(panel) and "j" in panel.columns:
    us = panel[panel["j"] == USA_CODE]
    us.to_csv(OUT_US, index=False)
    us.to_parquet(OUT_US_PQ, index=False)
    print(f"Exported: {os.path.basename(OUT_US)}  ({len(us):,} rows)")
    print(f"Exported: {os.path.basename(OUT_US_PQ)}")
else:
    panel.to_csv(OUT_US, index=False)
    panel.to_parquet(OUT_US_PQ, index=False)
    print(f"Exported: {os.path.basename(OUT_US)}  (same as panel)")
    print(f"Exported: {os.path.basename(OUT_US_PQ)}")

coverage.to_csv(OUT_COVERAGE, index=False)
print(f"Exported: {os.path.basename(OUT_COVERAGE)}  "
      f"({len(coverage)} codes: "
      f"{(coverage['universe']=='exact_hs6').sum()} exact + "
      f"{(coverage['universe']=='hs4_prefix').sum()} prefix)")

print(f"\nVersion: {VERSION}  |  HS: HS2017  |  BACI: V{BACI_VERSION}")
print("Phase 3 complete.")
print("Next: Phase 4 → build_io_network.py")