"""
normalize_hs_codes.py
─────────────────────────────────────────────────────────────────────────────
PHASE 2 — Normalization + HS Harmonization

Input:
    oecd_semiconductor_concordance_raw.csv  (Phase 1 archival layer)

Output:
    concordance/semiconductor_hs6_master.csv

Rules:
    - NEVER overwrite hs_original (archival string preserved in every row)
    - All corrections go into hs6_normalized only
    - parent_row_id links every output row back to its Phase 1 source row
    - hs_original lineage is preserved even for exploded children

Operations applied (in order):

    1. PASS-THROUGH   — HS6 rows: copy directly, clean description
    2. GROUPED SPLIT  — slash-separated codes: one row per code
    3. NONSTANDARD    — resolve 85181→851810, 9504.30→950430
    4. HS4 EXPAND     — tiered strategy:
         MUST EXPAND (Step 2 core outputs):
           8542 → use OECD-listed children from Phase 1 (rows 31-35)
           8533 → HS2017 HS6 schedule (7 codes)
           8534 → HS2017 HS6 schedule (1 code: 853400)
         SELECTIVE EXPAND (Step 3):
           8540 → HS2017 HS6 schedule (13 codes)
           8473 → HS2017 HS6 schedule (8 codes)
         HEADING FILTER (Steps 3-4, too diffuse to fully explode):
           8470, 8471, 8472, 8526, 8528, 9006, 9014, 9022,
           9027, 9028, 9029, 9030
           → retained as category-level BACI prefix filters
    5. REFERENCE ROWS — dropped from master (preserved in raw only)

Added columns (not in Phase 1):
    row_uid             — stable 12-char MD5 hash of row identity
                          key: parent_row_id | hs_original |
                               hs6_normalized | expansion_type
                          guarantees: unique per row, stable across runs,
                          survives sort/reindex operations.
                          Use as join key in Phase 3-5 regressions to avoid
                          many-to-many join ambiguity and enable exact lineage
                          tracing in collapsed country-year-product panels.
    hs6_normalized      — operational 6-digit code (string, zero-padded)
    hs4_filter          — for heading-filter rows: 4-digit prefix for BACI
    description_clean   — description stripped of trailing punctuation
    semiconductor_layer — core (Steps 1-2) | downstream (Steps 3-4)
    is_baci_matchable   — True if row has a valid hs6_normalized
    hs_revision_target  — "HS2017" (explicit for reviewer reproducibility)
    strategic_subset_flag — True for semiconductor-intensive core codes
    merge_strategy      — "exact_hs6" | "hs4_prefix" | "none"
                          prevents Phase 3 from inferring merge behavior
                          exact_hs6:  join on hs6_normalized directly
                          hs4_prefix: use hs4_filter as BACI prefix filter
                          none:       reference/unresolved rows, no merge
    expansion_type      — original | grouped_split | nonstandard_resolved |
                          hs4_expanded | hs4_already_listed | heading_filter
    normalization_note  — what was done in Phase 2 (empty = no change)

Key design decisions:
    - 8542 row (row 30) flagged hs4_already_listed: its HS6 children
      already exist in Phase 1 rows 31-35; no new rows generated
    - Grouped code 848610/868640 (row 8): 868640 preserved verbatim;
      normalization_note flags it as probable typo
    - HS4 heading-filter rows get hs6_normalized = null and
      hs4_filter = 4-digit prefix for BACI startswith() filtering

Output versioning:
    All output files carry a version suffix (_v1) to support parallel
    concordance generations from future OECD revisions, HS2022 migration,
    or alternative strategic subset definitions without overwriting.
    Version bump triggers:
      - HS revision change (HS2017 → HS2022)
      - OECD appendix revision
      - Strategic subset definition change
      - New tariff-linked subsets
─────────────────────────────────────────────────────────────────────────────
"""

import pandas as pd
import numpy as np
import os
import hashlib

# =============================================================================
# PATHS
# =============================================================================

BASE   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW    = os.path.join(BASE, "data", "raw", "oecd_semiconductor_concordance_raw.csv")

# Version suffix — increment when concordance definition changes materially
# (HS revision, OECD update, strategic subset redefinition)
VERSION = "v1"

MASTER    = os.path.join(BASE, "data", "raw",     f"semiconductor_hs6_master_{VERSION}.csv")
BACI_FILT = os.path.join(BASE, "data", "interim", f"semiconductor_hs6_baci_filter_{VERSION}.csv")

# =============================================================================
# HS4 EXPANSION TABLES  (HS2017, aligned with BACI HS2017 release)
# Source: WCO Harmonized System 2017 schedule
# =============================================================================

# 8542 — already listed as HS6 children in Phase 1; no expansion needed
# Row 30 will be flagged hs4_already_listed

HS4_EXPAND = {

    # MUST EXPAND — Step 2 core outputs
    "8533": [
        ("853310", "Fixed carbon resistors, composition or film types"),
        ("853321", "Fixed resistors, power handling capacity <= 20W"),
        ("853329", "Fixed resistors, power handling capacity > 20W"),
        ("853331", "Wirewound variable resistors, power handling capacity <= 20W"),
        ("853339", "Wirewound variable resistors, power handling capacity > 20W"),
        ("853340", "Other variable resistors incl. rheostats and potentiometers"),
        ("853390", "Parts of electrical resistors"),
    ],
    "8534": [
        ("853400", "Printed circuits"),
    ],

    # SELECTIVE EXPAND — Step 3 intermediate inputs
    "8540": [
        ("854011", "Cathode-ray television picture tubes, colour"),
        ("854012", "Cathode-ray television picture tubes, black and white"),
        ("854020", "Television camera tubes; image converters and intensifiers"),
        ("854040", "Data/graphic display tubes, colour"),
        ("854050", "Data/graphic display tubes, black and white or other monochrome"),
        ("854060", "Other cathode-ray tubes"),
        ("854071", "Magnetrons"),
        ("854072", "Klystrons"),
        ("854079", "Other microwave tubes; transmitter tubes"),
        ("854081", "Receiver or amplifier valves and tubes, not CRT"),
        ("854089", "Other thermionic, cold cathode or photocathode tubes"),
        ("854091", "Parts of cathode-ray tubes"),
        ("854099", "Other parts of thermionic/cold cathode/photocathode tubes"),
    ],
    "8473": [
        ("847310", "Parts and accessories of calculating machines of 8469 or 8470"),
        ("847321", "Storage units for automatic data processing machines"),
        ("847329", "Other parts and accessories of ADP machines"),
        ("847330", "Keyboards for ADP machines"),
        ("847340", "Other input or output units for ADP machines"),
        ("847350", "Processing units for ADP (other than 847141/847149)"),
        ("847380", "Other units for automatic data processing machines"),
        ("847390", "Other parts and accessories for machines of headings 8469-8472"),
    ],
}

# HEADING FILTERS — Steps 3-4, too diffuse to fully explode
# Retained as 4-digit prefix filters for BACI startswith() queries
HEADING_FILTERS = {
    "8470": "Calculating machines and pocket-size data recording machines",
    "8471": "Automatic data processing machines (computers)",
    "8472": "Other office machines",
    "8526": "Radar apparatus, radio navigational aid apparatus",
    "8528": "Monitors and projectors; television reception apparatus",
    "9006": "Photographic cameras",
    "9014": "Direction finding compasses; other navigational instruments",
    "9022": "Apparatus based on X-rays, alpha, beta or gamma radiation",
    "9027": "Instruments and apparatus for physical or chemical analysis",
    "9028": "Gas, liquid or electricity supply or production meters",
    "9029": "Revolution counters, production counters, taximeters",
    "9030": "Oscilloscopes; instruments for measuring/detecting ionising radiations",
}

# NONSTANDARD RESOLUTIONS
NONSTANDARD_MAP = {
    "85181":   ("851810", "5-digit truncation in OECD original; resolved to 851810 (microphones)"),
    "9504.30": ("950430", "Decimal notation in OECD original; resolved to 950430 (coin-operated games)"),
}

# =============================================================================
# LOAD PHASE 1
# =============================================================================

raw = pd.read_csv(RAW)
raw["oecd_row_id"] = raw["oecd_row_id"].astype(int)

# Base columns to carry forward from Phase 1
BASE_COLS = [
    "oecd_row_id", "hs_original", "description",
    "step", "role", "segment", "ita_colour",
    "appendix_page", "reference_flag", "notes", "source"
]

# =============================================================================
# PROCESSING
# =============================================================================

output_rows = []

def semiconductor_layer(step):
    return "core" if step <= 2 else "downstream"

def clean_description(s):
    """Strip trailing commas, semicolons, and whitespace."""
    if not isinstance(s, str):
        return ""
    return s.strip().rstrip(",;").strip()

def make_row(phase1_row, hs6_norm, expansion_type, norm_note="",
             hs4_filter=None, description_override=None):
    """Build one output row dict."""
    desc = description_override if description_override else phase1_row["description"]
    return {
        "parent_row_id":     phase1_row["oecd_row_id"],
        "hs_original":       phase1_row["hs_original"],
        "hs6_normalized":    hs6_norm,
        "hs4_filter":        hs4_filter,
        "description":       desc,
        "description_clean": clean_description(desc),
        "step":              phase1_row["step"],
        "role":              phase1_row["role"],
        "segment":           phase1_row["segment"],
        "semiconductor_layer": semiconductor_layer(phase1_row["step"]),
        "ita_colour":        phase1_row["ita_colour"],
        "appendix_page":     phase1_row["appendix_page"],
        "reference_flag":    phase1_row["reference_flag"],
        "expansion_type":    expansion_type,
        "normalization_note": norm_note,
        "phase1_notes":      phase1_row["notes"],
        "source":            phase1_row["source"],
    }

for _, row in raw.iterrows():

    level = row["hs_level"]
    orig  = str(row["hs_original"]).strip()

    # ── Drop reference rows (no HS code; preserved in raw only) ──────────────
    if row["reference_flag"] == True or level == "reference":
        continue

    # ── HS6 pass-through ──────────────────────────────────────────────────────
    if level == "HS6":
        output_rows.append(make_row(row, orig, "original"))

    # ── Grouped split ─────────────────────────────────────────────────────────
    elif level == "grouped":
        parts = [p.strip() for p in orig.split("/")]
        for code in parts:
            note = ""
            if code == "868640":
                note = ("Probable OECD typo (row 8). "
                        "848640 confirmed in row 28. Preserved verbatim.")
            output_rows.append(make_row(
                row, code, "grouped_split",
                norm_note=note or f"Split from grouped entry '{orig}'"
            ))

    # ── Nonstandard resolution ────────────────────────────────────────────────
    elif level == "nonstandard":
        if orig in NONSTANDARD_MAP:
            norm_code, note = NONSTANDARD_MAP[orig]
            output_rows.append(make_row(row, norm_code, "nonstandard_resolved",
                                        norm_note=note))
        else:
            output_rows.append(make_row(row, None, "nonstandard_unresolved",
                                        norm_note=f"No resolution defined for '{orig}'"))

    # ── HS4 headings ──────────────────────────────────────────────────────────
    elif level == "HS4":
        hs4 = orig.strip()

        # 8542: children already in Phase 1 as HS6 rows; flag and skip expansion
        if hs4 == "8542":
            output_rows.append(make_row(
                row, None, "hs4_already_listed",
                hs4_filter=hs4,
                norm_note="HS6 children (854231-854290) already present "
                          "as Phase 1 rows 31-35. No new rows generated."
            ))

        # Must-expand + selective-expand
        elif hs4 in HS4_EXPAND:
            # Keep a heading summary row for the HS4 itself
            output_rows.append(make_row(
                row, None, "hs4_expanded",
                hs4_filter=hs4,
                norm_note=f"HS4 heading; {len(HS4_EXPAND[hs4])} HS6 "
                          f"children generated below."
            ))
            # Generate one row per HS6 child
            for hs6_code, hs6_desc in HS4_EXPAND[hs4]:
                output_rows.append(make_row(
                    row, hs6_code, "hs4_expanded",
                    norm_note=f"Expanded from HS4 {hs4} (parent row {row['oecd_row_id']})",
                    description_override=hs6_desc
                ))

        # Heading filters — too diffuse, keep as prefix filter
        elif hs4 in HEADING_FILTERS:
            output_rows.append(make_row(
                row, None, "heading_filter",
                hs4_filter=hs4,
                norm_note=f"Retained as category-level BACI prefix filter. "
                          f"Use df[df.hs6.str.startswith('{hs4}')] to filter."
            ))

        else:
            output_rows.append(make_row(
                row, None, "hs4_unhandled",
                hs4_filter=hs4,
                norm_note=f"HS4 '{hs4}' not in expansion or filter tables."
            ))

# =============================================================================
# BUILD MASTER DATAFRAME + DERIVED ANALYTICAL FLAGS
# =============================================================================

# is_baci_matchable: True only if row has a valid hs6_normalized
# Avoids repeated .notna() filtering in Phase 3+
# heading_filter and hs4_already_listed rows are NOT directly mergeable
master_df_pre = pd.DataFrame(output_rows)
master_df_pre["is_baci_matchable"] = master_df_pre["hs6_normalized"].notna()

# hs_revision_target: explicit HS revision used for all normalization
# Critical for reviewer reproducibility and BACI version selection
master_df_pre["hs_revision_target"] = "HS2017"

# strategic_subset_flag: identifies the semiconductor-intensive core
# used for identification strategy (tariffs, export controls, rerouting)
#
# Criteria for True:
#   - Steps 1-2 (core semiconductor manufacturing chain): always True
#   - Step 3 outputs that are semiconductor-specific instruments/comms
#     (901210, 901290, 901490, 903082, 903141, 851761, 851762, 851769): True
#   - 8473 expanded codes: False — too broad (ADP peripherals may dilute)
#   - Step 3-4 broad electronics (8470, 8471, 8472, 8528, 9006): False
#   - Step 4 telecoms (851712, 851718, 851770, 851810): True
#     (directly tariffed in 2018 Section 301 lists)
#
# This is a first-pass definition. Refine in Phase 4/5 using
# semiconductor intensity from OECD TiVA value-added decomposition.

STRATEGIC_CORE_HS6 = {
    # Step 3 semiconductor-specific instruments and comms
    "901210", "901290", "901490", "903082", "903141",
    "851761", "851762", "851769",
    # Step 4 telecoms (Section 301 tariff targets)
    "851712", "851718", "851770", "851810",
    # Step 3 intermediate industry instruments
    "902490", "902790", "902890", "902990",
    "903090", "903190", "903290", "903300",
}

STRATEGIC_EXCLUDE_EXPANSION_TYPES = {
    "heading_filter",       # too broad to flag as strategic
    "hs4_already_listed",   # heading row, not a code
}

STRATEGIC_EXCLUDE_HS6_PREFIXES = {
    "8473",  # ADP peripherals — too broad
    "8540",  # legacy vacuum tubes — low semiconductor intensity
}

def assign_strategic_flag(row):
    # Reference / heading rows: never strategic
    if row["expansion_type"] in STRATEGIC_EXCLUDE_EXPANSION_TYPES:
        return False
    if not row["is_baci_matchable"]:
        return False
    hs6 = str(row["hs6_normalized"]) if row["hs6_normalized"] else ""
    # Exclude broad expansions
    for prefix in STRATEGIC_EXCLUDE_HS6_PREFIXES:
        if hs6.startswith(prefix):
            return False
    # Steps 1-2: always strategic
    if row["step"] <= 2:
        return True
    # Steps 3-4: only explicitly listed codes
    if hs6 in STRATEGIC_CORE_HS6:
        return True
    return False

master_df_pre["strategic_subset_flag"] = master_df_pre.apply(
    assign_strategic_flag, axis=1
)

# merge_strategy: explicit merge instruction for Phase 3
# Prevents Phase 3 from inferring merge behavior procedurally.
#   exact_hs6  — row has hs6_normalized; join directly on product code
#   hs4_prefix — row has hs4_filter only; use as BACI startswith() filter
#   none       — reference row or unresolved nonstandard; skip in merge
master_df_pre["merge_strategy"] = np.where(
    master_df_pre["hs6_normalized"].notna(),
    "exact_hs6",
    np.where(
        master_df_pre["hs4_filter"].notna(),
        "hs4_prefix",
        "none"
    )
)

# Replace output_rows processing with master_df_pre
master = master_df_pre.copy()

# Ensure hs6_normalized is a zero-padded 6-char string where present
def pad_hs6(x):
    if pd.isna(x) or x is None:
        return None
    s = str(x).strip()
    if len(s) == 6 and s.isdigit():
        return s.zfill(6)
    return s  # preserve as-is if non-standard (e.g. 868640 typo)

master["hs6_normalized"] = master["hs6_normalized"].apply(pad_hs6)

# =============================================================================
# ROW UID
# =============================================================================
# Stable 12-char MD5 hash of row identity.
# Computed AFTER pad_hs6 so hs6_normalized is in its final normalised form.
# None values are serialised as the literal string "null" for hash stability.
#
# Hash key components:
#   parent_row_id  — links back to Phase 1 archival row
#   hs_original    — OECD verbatim entry (includes typos, groupings)
#   hs6_normalized — operational code (None → "null" for heading/ref rows)
#   expansion_type — how this row was generated (original/grouped_split/etc.)
#
# Guarantees:
#   - Unique per row in this version of the concordance
#   - Stable across re-runs (same inputs → same uid)
#   - Survives sort/reindex/merge operations
#   - Use as join key in Phase 3-5 to avoid many-to-many ambiguity

def make_row_uid(row):
    hs6 = str(row["hs6_normalized"]) if pd.notna(row["hs6_normalized"]) else "null"
    key = (
        f"{row['parent_row_id']}|"
        f"{row['hs_original']}|"
        f"{hs6}|"
        f"{row['expansion_type']}"
    )
    return hashlib.md5(key.encode()).hexdigest()[:12]

master["row_uid"] = master.apply(make_row_uid, axis=1)

# =============================================================================
# VALIDATION
# =============================================================================

print("=" * 70)
print("PHASE 2 — Normalization Output")
print("=" * 70)
print(f"\nPhase 1 input rows:  {len(raw)}")
print(f"  Reference rows dropped: {raw['reference_flag'].sum()}")
print(f"Master output rows:  {len(master)}")

print("\nBy expansion_type:")
for et, n in master["expansion_type"].value_counts().items():
    print(f"  {et:<28}: {n:3d} rows")

print("\nBy semiconductor_layer:")
for layer, n in master["semiconductor_layer"].value_counts().items():
    print(f"  {layer:<12}: {n:3d} rows")

print("\nBy step:")
for step in [1, 2, 3, 4]:
    sub = master[master["step"] == step]
    hs6 = sub["hs6_normalized"].notna().sum()
    filt = (sub["expansion_type"] == "heading_filter").sum()
    print(f"  Step {step}: {len(sub):3d} rows  "
          f"({hs6} with hs6_normalized, {filt} heading filters)")

# HS6 universe for BACI merge
hs6_universe = master[master["hs6_normalized"].notna()]["hs6_normalized"].unique()
print(f"\nUnique hs6_normalized codes (BACI-matchable): {len(hs6_universe)}")
print(f"is_baci_matchable breakdown:")
print(f"  True  (directly mergeable): {master['is_baci_matchable'].sum():3d}")
print(f"  False (heading/ref/other):  {(~master['is_baci_matchable']).sum():3d}")
print(f"\nhs_revision_target: {master['hs_revision_target'].unique().tolist()}")
print(f"\nstrategic_subset_flag breakdown:")
print(f"  True  (semiconductor core):  {master['strategic_subset_flag'].sum():3d}")
print(f"  False (broad/peripheral):    {(~master['strategic_subset_flag']).sum():3d}")
print(f"\nStrategic subset by step:")
for step in [1,2,3,4]:
    sub = master[master["step"]==step]
    n_strat = sub["strategic_subset_flag"].sum()
    n_total = sub["is_baci_matchable"].sum()
    print(f"  Step {step}: {n_strat:2d}/{n_total:2d} matchable codes flagged strategic")

print(f"\nmerge_strategy breakdown:")
for strat, n in master["merge_strategy"].value_counts().items():
    print(f"  {strat:<12}: {n:3d} rows")

# Heading filters
hf = master[master["expansion_type"] == "heading_filter"]
if len(hf):
    print(f"\nHeading filters (hs4_filter prefixes for BACI): {len(hf)}")
    for _, r in hf.iterrows():
        print(f"  {r['hs4_filter']}  Step {r['step']}  {r['description_clean'][:50]}")

# Flag 868640 typo row
typo = master[master["hs6_normalized"] == "868640"]
if len(typo):
    print(f"\nWARNING: 868640 (probable typo for 848640) included as-is.")
    print("  Resolve manually in Phase 3 before BACI merge.")

# Nonstandard resolutions
ns = master[master["expansion_type"] == "nonstandard_resolved"]
print(f"\nNonstandard resolutions ({len(ns)}):")
for _, r in ns.iterrows():
    print(f"  '{r['hs_original']}' → {r['hs6_normalized']}  ({r['normalization_note'][:60]})")

# Check lineage — every row traces back to Phase 1
assert master["parent_row_id"].notna().all(), "ERROR: Missing parent_row_id"
print(f"\nLineage check: all {len(master)} rows have parent_row_id ✓")

# Check row_uid uniqueness — must be collision-free
n_uid    = master["row_uid"].nunique()
n_rows   = len(master)
assert n_uid == n_rows, f"ERROR: row_uid collision — {n_uid} unique / {n_rows} rows"
print(f"row_uid check:  {n_uid} unique hashes, 0 collisions ✓")

# =============================================================================
# EXPORT
# =============================================================================

COL_ORDER = [
    "row_uid",
    "parent_row_id",
    "hs_original",
    "hs6_normalized",
    "hs4_filter",
    "description",
    "description_clean",
    "step",
    "role",
    "segment",
    "semiconductor_layer",
    "ita_colour",
    "appendix_page",
    "reference_flag",
    "is_baci_matchable",
    "hs_revision_target",
    "strategic_subset_flag",
    "merge_strategy",
    "expansion_type",
    "normalization_note",
    "phase1_notes",
    "source",
]

master[COL_ORDER].to_csv(MASTER, index=False)
print(f"\nExported: {MASTER}")
print(f"  Rows: {len(master)} | Columns: {len(COL_ORDER)} | Version: {VERSION}")

# Also export a clean HS6-only filter list for BACI
hs6_list = (master[master["hs6_normalized"].notna()]
            [["row_uid", "hs6_normalized", "description_clean", "step",
              "role", "semiconductor_layer", "ita_colour",
              "expansion_type", "merge_strategy", "parent_row_id"]]
            .drop_duplicates(subset="hs6_normalized")
            .sort_values(["step", "hs6_normalized"])
            .reset_index(drop=True))

hs6_list.to_csv(BACI_FILT, index=False)
print(f"Exported: {BACI_FILT}")
print(f"  Unique HS6 codes ready for BACI: {len(hs6_list)} | Version: {VERSION}")

print("\nPhase 2 complete.")
print("Next: Phase 3 → extract_baci_semiconductors.py")