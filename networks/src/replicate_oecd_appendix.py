"""
replicate_oecd_appendix.py
─────────────────────────────────────────────────────────────────────────────
PHASE 1 — Faithful replication of OECD Annex A

Source:
    OECD Trade Policy Paper No. 234
    "Measuring Distortions in International Markets:
     The Semiconductor Value Chain" (Ganne & Lundquist, 2019)
    Annex A. Technical Appendix, pp. 107–108

Rules (from OECD Semiconductor Concordance Replication Plan):
    DO:
      - replicate OECD categories exactly
      - preserve grouped HS codes (e.g. "848610 / 868640")
      - preserve HS4 aggregates (e.g. "8471", "8542")
      - preserve OECD step/role/segment hierarchy
      - preserve verbatim typos and trailing punctuation
      - preserve reference rows ("—")

    DO NOT:
      - expand grouped codes
      - harmonize HS revisions
      - silently correct OECD errors
      - infer missing codes
      - introduce custom strategic categories
      - estimate IO coefficients

Output:
    concordance/oecd_semiconductor_concordance_raw.csv

Schema:
    oecd_row_id     — row order in appendix (integer, sequential)
    hs_original     — exact HS entry as written in OECD appendix
    hs_level        — classification of hs_original format:
                        HS4         = 4-digit HS heading
                        HS6         = 6-digit HS code
                        grouped     = slash-separated multiple codes
                        nonstandard = malformed (5-digit, decimal notation)
                        reference   = cross-reference row, no HS code
    description     — OECD product description (verbatim)
    step            — OECD production step (1 / 2 / 3 / 4)
    role            — OECD row role (verbatim from appendix)
    segment         — upstream / middle / downstream
    ita_colour      — ITA colour from original document:
                        green  = initial ITA agreement
                        red    = ITA expansion
                        orange = other tech goods, initial ITA
                        blue   = other tech goods, ITA expansion
                        black  = not in ITA
    appendix_page   — page number in source document (107 or 108)
    reference_flag  — True if row is a cross-reference (no HS code)
    notes           — replication notes (typos, cross-refs, anomalies)
    source          — constant citation string

hs_level classification logic:
    Pattern              → hs_level
    4 digits             → HS4
    6 digits             → HS6
    slash-separated      → grouped
    5 digits             → nonstandard  (e.g. "85181")
    decimal notation     → nonstandard  (e.g. "9504.30")
    "—" reference rows   → reference
─────────────────────────────────────────────────────────────────────────────
"""

import pandas as pd
import os

SOURCE = "OECD Trade Policy Paper No. 234 (2019), Annex A, pp. 107-108"

# =============================================================================
# EXACT TRANSCRIPTION
# Tuple order: (oecd_row_id, hs_original, hs_level, description,
#               step, role, segment, ita_colour, appendix_page, notes)
#
# DO NOT modify hs_original or description fields without source verification.
# All corrections belong in the notes field only.
# =============================================================================

ROWS = [

    # ── STEP 1  (p. 107) ─────────────────────────────────────────────────────

    (1,  "280461",           "HS6",         "Silicon high purity",
     1, "Raw Material", "upstream", "black", 107, ""),

    (2,  "284920",           "HS6",         "Silicon carbide",
     1, "Raw Material", "upstream", "black", 107, ""),

    (3,  "282560",           "HS6",         "Germanium",
     1, "Raw Material", "upstream", "black", 107, ""),

    (4,  "370130",           "HS6",         "Photographic plates and film",
     1, "Input", "upstream", "red", 107, ""),

    (5,  "370199",           "HS6",         "Photographic plates and film",
     1, "Input", "upstream", "red", 107, ""),

    (6,  "370790",           "HS6",         "Photographic goods",
     1, "Input", "upstream", "black", 107, ""),

    (7,  "811290",           "HS6",         "Gallium Arsenide",
     1, "Input", "upstream", "black", 107, ""),

    (8,  "848610 / 868640",  "grouped",     "Machines for the manufacture of semiconductor boules or wafers",
     1, "Equipment", "upstream", "red", 107,
     "868640 appears to be a typo in original; likely 848640. "
     "Preserved verbatim per Phase 1 rules. Do not correct in Phase 2 "
     "without source verification."),

    (9,  "848690",           "HS6",         "Parts and accessories",
     1, "Equipment", "upstream", "red", 107, ""),

    (10, "903082",           "HS6",         "Instrument for measuring or checking semiconductor wafers or devices",
     1, "Equipment", "upstream", "black", 107,
     "Also appears as Step 2 Input (row 21). OECD lists in both steps."),

    (11, "903141",           "HS6",         "Optical instruments for inspecting semiconductor wafers",
     1, "Equipment", "upstream", "black", 107,
     "Also appears as Step 2 Input (row 22). OECD lists in both steps."),

    (12, "381800",           "HS6",         "Silicon wafers",
     1, "Output", "upstream", "black", 107,
     "Step 1 Output = Step 2 Raw Material. Same HS6 appears in row 13."),


    # ── STEP 2  (p. 107) ─────────────────────────────────────────────────────

    (13, "381800",           "HS6",         "Silicon wafers",
     2, "Raw Material", "middle", "black", 107,
     "Step 2 Raw Material = Step 1 Output (row 12). Cross-reference preserved."),

    (14, "900120",           "HS6",         "Sheets of semiconductor",
     2, "Input", "middle", "red", 107, ""),

    (15, "900190",           "HS6",         "Lenses for semiconductor",
     2, "Input", "middle", "red", 107, ""),

    (16, "900219",           "HS6",         "Objective lenses,",
     2, "Input", "middle", "red", 107,
     "Trailing comma present in original OECD text. Preserved verbatim."),

    (17, "900220",           "HS6",         "Optical filters",
     2, "Input", "middle", "red", 107, ""),

    (18, "900290",           "HS6",         "Mirrors",
     2, "Input", "middle", "red", 107, ""),

    (19, "901210",           "HS6",         "Electron microscopes for semiconductor inspection",
     2, "Input", "middle", "red", 107,
     "Also appears grouped with 901290 in Step 3 Output 1 (row 49)."),

    (20, "901290",           "HS6",         "Parts of electron microscopes",
     2, "Input", "middle", "red", 107,
     "Also appears grouped with 901210 in Step 3 Output 1 (row 49)."),

    (21, "903082",           "HS6",         "Instruments for measuring semiconductor devices",
     2, "Input", "middle", "black", 107,
     "Also appears as Step 1 Equipment (row 10). OECD lists in both steps."),

    (22, "903141",           "HS6",         "Optical instruments inspecting semiconductor devices,",
     2, "Input", "middle", "black", 107,
     "Also appears as Step 1 Equipment (row 11). Trailing comma in original."),

    (23, "841459",           "HS6",         "Fans for cooling microprocessors,",
     2, "Equipment", "middle", "red", 107,
     "Trailing comma in original OECD text. Preserved verbatim."),

    (24, "841950",           "HS6",         "Heat exchange units",
     2, "Equipment", "middle", "red", 107, ""),

    (25, "842129",           "HS6",         "Liquid filtering or purifying machinery",
     2, "Equipment", "middle", "red", 107, ""),

    (26, "842139",           "HS6",         "Filtering or purifying machinery and apparatus",
     2, "Equipment", "middle", "red", 107, ""),

    (27, "842199",           "HS6",         "Parts of filtering for semiconductor manufacturing",
     2, "Equipment", "middle", "red", 107, ""),

    (28, "848620 / 848640",  "grouped",     "Machines for the manufacture of semiconductor",
     2, "Equipment", "middle", "red", 107,
     "848640 also appears in Step 1 Equipment row 8 (as 868640 — possible typo). "
     "OECD lists 848640 explicitly here, confirming 868640 in row 8 is likely erroneous."),

    (29, "848690",           "HS6",         "Parts and accessories",
     2, "Equipment", "middle", "red", 107,
     "Also appears in Step 1 Equipment (row 9)."),

    (30, "8542",             "HS4",         "Integrated circuits",
     2, "Output", "middle", "black", 107,
     "HS4 aggregate heading. Rows 31-35 are HS6 subdivisions listed separately below it."),

    (31, "854231",           "HS6",         "Processors and controllers,",
     2, "Output", "middle", "black", 107,
     "Subdivision of HS4 8542 (row 30). Trailing comma in original."),

    (32, "854232",           "HS6",         "Memories",
     2, "Output", "middle", "black", 107,
     "Subdivision of HS4 8542 (row 30)."),

    (33, "854233",           "HS6",         "Amplifiers",
     2, "Output", "middle", "black", 107,
     "Subdivision of HS4 8542 (row 30)."),

    (34, "854239",           "HS6",         "Others",
     2, "Output", "middle", "black", 107,
     "Subdivision of HS4 8542 (row 30)."),

    (35, "854290",           "HS6",         "Micro assemblies",
     2, "Output", "middle", "black", 107,
     "Subdivision of HS4 8542 (row 30)."),

    (36, "852351",           "HS6",         "Non-volatile storage",
     2, "Output", "middle", "red", 107, ""),

    (37, "852352",           "HS6",         "Smart cards",
     2, "Output", "middle", "black", 107, ""),

    (38, "852359",           "HS6",         "Solid-state storage",
     2, "Output", "middle", "red", 107, ""),

    (39, "853290",           "HS6",         "Passive: Electrical capacitors",
     2, "Output", "middle", "red", 107, ""),

    (40, "8533",             "HS4",         "Passive: Electrical resistors",
     2, "Output", "middle", "red", 107,
     "HS4 aggregate. Not expanded to HS6 in OECD appendix."),

    (41, "8534",             "HS4",         "Printed circuits",
     2, "Output", "middle", "red", 107,
     "HS4 aggregate. Not expanded to HS6 in OECD appendix."),


    # ── STEP 3  (p. 108) ─────────────────────────────────────────────────────

    (42, "—",                "reference",   "Semiconductors (see Outputs above)",
     3, "Material", "middle", "black", 108,
     "Cross-reference to Step 2 Outputs. No HS code. "
     "Preserves OECD production-system logic: Step 3 uses Step 2 outputs as material inputs."),

    (43, "8540",             "HS4",         "Tubes",
     3, "Input", "middle", "black", 108,
     "HS4 aggregate. Not expanded in OECD appendix."),

    (44, "854110",           "HS6",         "Electrical apparatus; diodes",
     3, "Input", "middle", "red", 108, ""),

    (45, "854121 / 854129",  "grouped",     "Electrical apparatus transistors",
     3, "Input", "middle", "red", 108, ""),

    (46, "851190",           "HS6",         "Automotive Ignition or starting equipment",
     3, "Output 1: Intermediate Industry", "middle", "black", 108, ""),

    (47, "852729",           "HS6",         "",
     3, "Output 1: Intermediate Industry", "middle", "black", 108,
     "No description visible in original for this row. Code only."),

    (48, "854430",           "HS6",         "",
     3, "Output 1: Intermediate Industry", "middle", "red", 108,
     "No description visible in original for this row. Code only."),

    (49, "901210 / 901290",  "grouped",     "Microscopes",
     3, "Output 1: Intermediate Industry", "middle", "orange", 108,
     "901210 and 901290 also appear individually as Step 2 Inputs (rows 19-20)."),

    (50, "901490",           "HS6",         "Navigational instruments",
     3, "Output 1: Intermediate Industry", "middle", "red", 108, ""),

    (51, "902490",           "HS6",         "Machines accessories for those testing hardness",
     3, "Output 1: Intermediate Industry", "middle", "red", 108, ""),

    (52, "902790",           "HS6",         "Microtomes",
     3, "Output 1: Intermediate Industry", "middle", "red", 108, ""),

    (53, "902890",           "HS6",         "Meters",
     3, "Output 1: Intermediate Industry", "middle", "red", 108, ""),

    (54, "902990",           "HS6",         "Meters and counters",
     3, "Output 1: Intermediate Industry", "middle", "black", 108, ""),

    (55, "903090",           "HS6",         "Instruments, for measuring electrical quantities",
     3, "Output 1: Intermediate Industry", "middle", "red", 108, ""),

    (56, "903190",           "HS6",         "",
     3, "Output 1: Intermediate Industry", "middle", "black", 108,
     "Continuation of row 55 in original layout. No separate description printed."),

    (57, "903290",           "HS6",         "Regulating or controlling instruments",
     3, "Output 1: Intermediate Industry", "middle", "black", 108, ""),

    (58, "903300",           "HS6",         "",
     3, "Output 1: Intermediate Industry", "middle", "black", 108,
     "Continuation of row 57 in original layout. No separate description printed."),

    (59, "8473",             "HS4",         "Machinery; parts and accessories",
     3, "Output 2: Intermediate Consumer", "middle", "orange", 108,
     "HS4 aggregate. Not expanded in OECD appendix."),

    (60, "851761",           "HS6",         "Base stations",
     3, "Output 2: Intermediate Consumer", "middle", "black", 108, ""),

    (61, "851762 / 851769",  "grouped",     "Communication apparatus",
     3, "Output 2: Intermediate Consumer", "middle", "black", 108, ""),

    (62, "851890",           "HS6",         "Microphones, headphones, earphones, amplifier",
     3, "Output 2: Intermediate Consumer", "middle", "black", 108, ""),

    (63, "852290",           "HS6",         "Sound or video recording apparatus",
     3, "Output 2: Intermediate Consumer", "middle", "black", 108, ""),

    (64, "852990",           "HS6",         "Transmission apparatus",
     3, "Output 2: Intermediate Consumer", "middle", "black", 108, ""),

    (65, "900690",           "HS6",         "Photographic flashlight apparatus",
     3, "Output 2: Intermediate Consumer", "middle", "black", 108, ""),


    # ── STEP 4  (p. 108) ─────────────────────────────────────────────────────

    (66, "—",                "reference",   "(See Outputs 1 and 2 above)",
     4, "Inputs 1 and 2", "downstream", "black", 108,
     "Cross-reference only. No HS code. "
     "Preserves OECD production-system logic: Step 4 inputs = Step 3 outputs."),

    (67, "8470",             "HS4",         "Calculating machines",
     4, "Output 1: Final Industry", "downstream", "orange", 108,
     "Under OECD sub-heading 'Computers and office'."),

    (68, "8471",             "HS4",         "Automatic data processing machines",
     4, "Output 1: Final Industry", "downstream", "orange", 108,
     "Under OECD sub-heading 'Computers and office'."),

    (69, "8472",             "HS4",         "Office machines; not elsewhere classified",
     4, "Output 1: Final Industry", "downstream", "orange", 108,
     "Under OECD sub-heading 'Computers and office'."),

    (70, "8526",             "HS4",         "Radar apparatus, radio navigational",
     4, "Output 1: Final Industry", "downstream", "black", 108,
     "Under OECD sub-heading 'Industrial equipment'."),

    (71, "9014",             "HS4",         "Navigational instruments",
     4, "Output 1: Final Industry", "downstream", "black", 108,
     "Under OECD sub-heading 'Industrial equipment'."),

    (72, "9022",             "HS4",         "",
     4, "Output 1: Final Industry", "downstream", "black", 108,
     "No description in original for this row. Code only. "
     "HS4 9022 = apparatus based on alpha, beta, gamma rays, X-rays etc."),

    (73, "9027",             "HS4",         "Gas or smoke analysis apparatus, for physical or chemical analysis",
     4, "Output 1: Final Industry", "downstream", "black", 108, ""),

    (74, "9028",             "HS4",         "Meters; gas, supply",
     4, "Output 1: Final Industry", "downstream", "black", 108, ""),

    (75, "9029",             "HS4",         "Meters and counters",
     4, "Output 1: Final Industry", "downstream", "black", 108, ""),

    (76, "9030",             "HS4",         "Instruments for measuring or detecting ionising radiations",
     4, "Output 1: Final Industry", "downstream", "black", 108, ""),

    (77, "851712",           "HS6",         "Telephones for cellular networks or for other wireless networks",
     4, "Output 2: Final Consumer", "downstream", "red", 108, ""),

    (78, "851718",           "HS6",         "Telephone sets n.e.c. in item no. 8517.1",
     4, "Output 2: Final Consumer", "downstream", "red", 108, ""),

    (79, "851770",           "HS6",         "Apparatus for the transmission or reception of voice, images or other data, via 851770",
     4, "Output 2: Final Consumer", "downstream", "black", 108,
     "Description in original includes the HS code '851770' inline. Preserved verbatim."),

    (80, "85181",            "nonstandard", "Microphones and stands therefor",
     4, "Output 2: Final Consumer", "downstream", "black", 108,
     "5-digit entry in original OECD document. Not valid HS6. "
     "Probable intended code: 851810. Classified nonstandard per Phase 1 rules. "
     "Do not correct in this file; resolve in Phase 2 normalize_hs_codes.py."),

    (81, "852580",           "HS6",         "Transmission apparatus for radio-broadcasting or television,",
     4, "Output 2: Final Consumer", "downstream", "black", 108,
     "Trailing comma in original. Preserved verbatim."),

    (82, "8528",             "HS4",         "Monitors and projectors, not incorporating television reception apparatus;",
     4, "Output 2: Final Consumer", "downstream", "black", 108,
     "Trailing semicolon in original. Preserved verbatim. HS4 aggregate."),

    (83, "9006",             "HS4",         "Cameras, photographic",
     4, "Output 2: Final Consumer", "downstream", "black", 108,
     "HS4 aggregate. Not expanded in OECD appendix."),

    (84, "9504.30",          "nonstandard", "Games; video game consoles and machines",
     4, "Output 2: Final Consumer", "downstream", "blue", 108,
     "Decimal notation in original OECD document. Not canonical HS6 format. "
     "Probable intended code: 950430. Classified nonstandard per Phase 1 rules. "
     "Do not correct in this file; resolve in Phase 2 normalize_hs_codes.py."),

    (85, "950450",           "HS6",         "",
     4, "Output 2: Final Consumer", "downstream", "blue", 108,
     "No description in original for this row. Code only. "
     "Continuation of row 84 product category (video game consoles and machines)."),
]

# =============================================================================
# BUILD DATAFRAME
# =============================================================================

COLUMNS = [
    "oecd_row_id", "hs_original", "hs_level", "description",
    "step", "role", "segment", "ita_colour", "appendix_page", "notes"
]

df = pd.DataFrame(ROWS, columns=COLUMNS)

# Derive reference_flag explicitly (recommendation #5)
df["reference_flag"] = df["hs_level"] == "reference"

# Add source citation
df["source"] = SOURCE

# =============================================================================
# VALIDATION
# =============================================================================

print("=" * 70)
print("PHASE 1 — OECD Annex A Faithful Replication")
print("=" * 70)
print(f"\nSource: {SOURCE}")
print(f"\nTotal rows transcribed: {len(df)}")

hl = df["hs_level"].value_counts()
for level in ["HS6","HS4","grouped","nonstandard","reference"]:
    n = hl.get(level, 0)
    print(f"  {level:<14}: {n:2d} rows")

print("\nBy step and page:")
for step, page in [(1,107),(2,107),(3,108),(4,108)]:
    sub = df[df["step"]==step]
    hs6  = (sub["hs_level"]=="HS6").sum()
    hs4  = (sub["hs_level"]=="HS4").sum()
    grp  = (sub["hs_level"]=="grouped").sum()
    ns   = (sub["hs_level"]=="nonstandard").sum()
    ref  = (sub["hs_level"]=="reference").sum()
    print(f"  Step {step} (p.{page}): {len(sub):2d} rows  "
          f"[HS6={hs6} HS4={hs4} grouped={grp} nonstandard={ns} ref={ref}]")

print("\nBy segment:")
for seg in ["upstream","middle","downstream"]:
    print(f"  {seg:<12}: {(df['segment']==seg).sum():2d} rows")

print("\nITA colour (excludes reference rows):")
print(df[~df["reference_flag"]]["ita_colour"].value_counts().to_string())

print("\nNonstandard entries requiring Phase 2 resolution:")
ns = df[df["hs_level"]=="nonstandard"][["oecd_row_id","hs_original","description","notes"]]
for _, r in ns.iterrows():
    print(f"  Row {r['oecd_row_id']:2d}: '{r['hs_original']}' — {r['description']}")
    print(f"          {r['notes'][:80]}")

print("\nCross-step duplicate hs_original entries:")
dupes = (df[df["hs_level"].isin(["HS6","HS4","grouped"])]
         .groupby("hs_original")["step"].apply(list))
for code, steps in dupes[dupes.map(len) > 1].items():
    print(f"  {code}: steps {steps}")

print("\nRows with empty descriptions:")
empty = df[(df["description"]=="") & (~df["reference_flag"])]
for _, r in empty.iterrows():
    print(f"  Row {r['oecd_row_id']:2d}: {r['hs_original']} — {r['notes'][:60]}")

# =============================================================================
# EXPORT
# =============================================================================

out_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "raw", "oecd_semiconductor_concordance_raw.csv"
)

# Column order for output
col_order = [
    "oecd_row_id", "hs_original", "hs_level", "description",
    "step", "role", "segment", "ita_colour",
    "appendix_page", "reference_flag", "notes", "source"
]
df[col_order].to_csv(out_path, index=False)

print(f"\nExported: {out_path}")
print(f"  Rows: {len(df)} | Columns: {len(col_order)}")
print("\nPhase 1 complete.")
print("Next: Phase 2 → normalize_hs_codes.py → semiconductor_hs6_master.csv")
