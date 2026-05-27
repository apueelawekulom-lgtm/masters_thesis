"""
GVC Annotation Batch Assignment
================================
Splits the diagnostic output CSV into annotation batches for 4 annotators.

Structure:
- 30-product overlap set (everyone annotates — used for inter-annotator agreement)
- 170 remaining products split into 4 domain-mixed batches (~42-43 each)
- Each annotator does: overlap (30) + private batch (~42) = ~72 products total

Input:  gvc_d4_d5_diagnostic_results.csv  (from Colab diagnostic run)
Output: annotation_overlap.csv            (all 4 annotators do this)
        annotation_batch_A.csv            (Apuela)
        annotation_batch_B.csv            (Rhea)
        annotation_batch_C.csv            (Michelle)
        annotation_batch_D.csv            (Olivia)
        annotation_summary.txt            (overview of each batch)

Usage:
    python create_annotation_batches.py
    python create_annotation_batches.py --input my_results.csv
"""

import pandas as pd
import numpy as np
import argparse
import os
from pathlib import Path

# ── Configuration ─────────────────────────────────────────────────────────────

ANNOTATORS = {
    'A': 'Apuela',
    'B': 'Rhea',
    'C': 'Michelle',
    'D': 'Olivia',
}

N_OVERLAP = 30          # products everyone annotates
RANDOM_SEED = 42

# Anchor products — known expected stages, highest priority for overlap set
# These are the products from our anchor validation (HS17 codes)
ANCHOR_CODES = {
    # D4 anchors
    '260111': 1,  # Iron ores — S1
    '260600': 1,  # Aluminium ores — S1
    '720110': 2,  # Pig iron — S2
    '760110': 2,  # Aluminium unwrought — S2
    '740311': 2,  # Copper cathodes — S2
    '720915': 3,  # Cold-rolled steel sheet — S3
    '760612': 3,  # Aluminium plates — S3
    '730511': 3,  # Steel line pipe — S3
    '848210': 4,  # Ball bearings — S4
    '848140': 4,  # Safety valves — S4
    '731815': 4,  # Screws and bolts — S4
    '830110': 5,  # Padlocks — S5
    '820719': 5,  # Rock drilling tools — S5
    # D5 anchors
    '853400': 3,  # Printed circuits — S3
    '850131': 4,  # DC electric motors — S4
    '854231': 4,  # Processors — S4
    '848310': 4,  # Transmission shafts — S4
    '870321': 5,  # Passenger vehicles — S5
    '851712': 5,  # Smartphones — S5
    '845011': 5,  # Washing machines — S5
    '841821': 5,  # Refrigerators — S5
    '880240': 5,  # Aeroplanes — S5
}

# ── Helper functions ───────────────────────────────────────────────────────────

def load_diagnostic(path):
    """Load and validate the diagnostic CSV."""
    df = pd.read_csv(path, dtype={'subheading': str, 'chapter': str})

    # Standardise column names
    col_map = {
        'code': 'subheading',
        'description': 'subheading_text',
        'subheading_text': 'subheading_text',
    }
    df.rename(columns={k: v for k, v in col_map.items() if k in df.columns}, inplace=True)

    # Ensure subheading is zero-padded 6-digit string
    df['subheading'] = df['subheading'].astype(str).str.zfill(6)

    required = ['subheading', 'subheading_text', 'domain', 'nli_uncertainty']
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns in diagnostic CSV: {missing}")

    print(f"Loaded {len(df)} products from {path}")
    print(f"  D4: {(df['domain']=='D4').sum()}  D5: {(df['domain']=='D5').sum()}")
    return df


def select_overlap_set(df, n=30):
    """
    Select the overlap set that all annotators will label.

    Priority order:
    1. Anchor products (known expected stages) — always included if present
    2. Highest uncertainty products (most informative for active learning)
    3. Fill remainder with stratified sample across domains and NLI classes

    Returns (overlap_df, remaining_df)
    """
    # Step 1: anchors present in the dataset
    anchor_mask = df['subheading'].isin(ANCHOR_CODES.keys())
    anchors_in_df = df[anchor_mask].copy()
    anchors_in_df['expected_stage'] = anchors_in_df['subheading'].map(ANCHOR_CODES)
    anchors_in_df['overlap_reason'] = 'anchor'

    print(f"\nAnchor products found in dataset: {len(anchors_in_df)}")

    # Step 2: highest uncertainty products from non-anchor set
    non_anchor = df[~anchor_mask].copy()
    non_anchor['expected_stage'] = None
    non_anchor['overlap_reason'] = 'high_uncertainty'

    n_high_unc = max(0, n - len(anchors_in_df))
    high_unc = non_anchor.nlargest(n_high_unc, 'nli_uncertainty')

    # Step 3: combine
    overlap = pd.concat([anchors_in_df, high_unc], ignore_index=True)

    # If still short (shouldn't happen with 200 products), fill with random
    if len(overlap) < n:
        remaining_pool = non_anchor[~non_anchor['subheading'].isin(overlap['subheading'])]
        filler = remaining_pool.sample(n=min(n-len(overlap), len(remaining_pool)),
                                       random_state=RANDOM_SEED)
        filler['overlap_reason'] = 'filler'
        overlap = pd.concat([overlap, filler], ignore_index=True)

    overlap = overlap.head(n)
    remaining = df[~df['subheading'].isin(overlap['subheading'])].copy()

    print(f"Overlap set: {len(overlap)} products")
    print(f"  Anchors: {(overlap['overlap_reason']=='anchor').sum()}")
    print(f"  High uncertainty: {(overlap['overlap_reason']=='high_uncertainty').sum()}")
    print(f"Remaining for private batches: {len(remaining)}")

    return overlap, remaining


def create_batches(remaining, n_batches=4):
    """
    Split remaining products into n_batches domain-mixed batches.

    Strategy:
    - Stratify by domain (D4/D5) and nli_uncertainty band (high/med/low)
    - Round-robin assignment within each stratum to ensure even distribution
    - Sort each batch by uncertainty descending (most informative first)
    """
    rng = np.random.default_rng(RANDOM_SEED)

    # Create stratification groups
    remaining = remaining.copy()
    remaining['unc_band'] = pd.cut(
        remaining['nli_uncertainty'],
        bins=[0, 0.5, 0.75, 1.0],
        labels=['low', 'med', 'high'],
        include_lowest=True
    )
    remaining['stratum'] = remaining['domain'] + '_' + remaining['unc_band'].astype(str)

    # Assign batch indices via round-robin within each stratum
    batch_idx = np.zeros(len(remaining), dtype=int)
    for stratum in remaining['stratum'].unique():
        mask = remaining['stratum'] == stratum
        idx = remaining.index[mask]
        # Shuffle within stratum
        shuffled = rng.permutation(len(idx))
        assignments = shuffled % n_batches
        batch_idx[remaining.index.get_indexer(idx)] = assignments

    remaining['batch'] = batch_idx

    batches = {}
    for i in range(n_batches):
        letter = chr(ord('A') + i)
        batch = remaining[remaining['batch'] == i].copy()
        # Sort by uncertainty descending (most informative first)
        batch = batch.sort_values('nli_uncertainty', ascending=False)
        batch = batch.drop(columns=['unc_band', 'stratum', 'batch'])
        batches[letter] = batch

    return batches


def add_annotation_columns(df, annotator_name, batch_type):
    """Add empty annotation columns to a batch dataframe."""
    out = df.copy()
    out.insert(0, 'annotator', annotator_name)
    out.insert(1, 'batch_type', batch_type)  # 'overlap' or 'private'

    # Empty annotation columns
    out['label'] = ''           # Stage 1-5
    out['stage_name'] = ''      # Human-readable
    out['flagged'] = ''         # Y/N — boundary case
    out['confidence'] = ''      # H/M/L — annotator confidence
    out['note'] = ''            # Free text reasoning

    return out


def print_summary(overlap, batches, annotators):
    """Print a human-readable summary of the batch assignment."""
    print("\n" + "="*70)
    print("ANNOTATION BATCH SUMMARY")
    print("="*70)

    print(f"\nOVERLAP SET ({len(overlap)} products — all 4 annotators)")
    print(f"  D4: {(overlap['domain']=='D4').sum()}  "
          f"D5: {(overlap['domain']=='D5').sum()}")
    print(f"  Mean uncertainty: {overlap['nli_uncertainty'].mean():.3f}")
    unc_dist = overlap['nli_uncertainty'].describe()
    print(f"  Uncertainty range: {unc_dist['min']:.3f} – {unc_dist['max']:.3f}")

    print(f"\nPRIVATE BATCHES:")
    for letter, name in annotators.items():
        batch = batches[letter]
        total = len(batch)
        d4 = (batch['domain']=='D4').sum()
        d5 = (batch['domain']=='D5').sum()
        mean_unc = batch['nli_uncertainty'].mean()
        high_unc = (batch['nli_uncertainty'] > 0.75).sum()
        print(f"\n  Batch {letter} — {name}")
        print(f"    Products: {total}  (D4: {d4}, D5: {d5})")
        print(f"    Mean uncertainty: {mean_unc:.3f}  |  High unc (>0.75): {high_unc}")

    print(f"\nPER-ANNOTATOR TOTAL (overlap + private):")
    for letter, name in annotators.items():
        total = len(overlap) + len(batches[letter])
        print(f"  {name}: {total} products")

    print("\n" + "="*70)
    print("OUTPUT FILES")
    print("="*70)
    print("  annotation_overlap.csv     → all 4 annotators label these")
    for letter, name in annotators.items():
        print(f"  annotation_batch_{letter}.csv     → {name} only")
    print("  annotation_summary.txt     → this summary")
    print("\nANNOTATION INSTRUCTIONS")
    print("="*70)
    print("""
  1. Open the annotation tool (Claude artifact link shared by Rhea/Apuela)
  2. Upload YOUR batch CSV + the overlap CSV together, OR annotate separately
  3. For each product, select a transformation stage (S1–S5)
  4. FLAG any genuinely ambiguous boundary cases
  5. Add a NOTE for any product where your reasoning might be non-obvious
  6. Fill in CONFIDENCE: H (certain), M (reasonably sure), L (guessing)
  7. Download your annotations CSV when done
  8. Share your CSV in the group — Apuela will merge

  OVERLAP PRODUCTS: Annotate these without looking at others' labels first.
  They will be used to compute inter-annotator agreement (Cohen's kappa).
  Disagreements on flagged products will be discussed as a team.

  STAGE DEFINITIONS (keep this open while annotating):
  S1 Raw/Unprocessed   Ore, mineral, metallic waste — no industrial transformation
  S2 Primary Processed Bulk metal from smelting/refining — ingot, billet, granular
  S3 Fabricated Mat.   Standardised form (sheet, bar, tube, wire) — generic, not a part
  S4 Manuf. Component  Discrete precision part for a specific mechanical function
  S5 Assembled/Finished Complete operational article — sold to end user as-is
""")


def save_summary(overlap, batches, annotators, output_dir):
    """Save summary to text file."""
    import io, sys
    old_stdout = sys.stdout
    sys.stdout = buffer = io.StringIO()
    print_summary(overlap, batches, annotators)
    sys.stdout = old_stdout
    summary_text = buffer.getvalue()

    path = output_dir / 'annotation_summary.txt'
    with open(path, 'w') as f:
        f.write(summary_text)
    return summary_text


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Create GVC annotation batches')
    parser.add_argument('--input', default='gvc_d4_d5_diagnostic_results.csv',
                        help='Path to diagnostic results CSV')
    parser.add_argument('--output_dir', default='.',
                        help='Directory to write batch CSVs')
    parser.add_argument('--n_overlap', type=int, default=N_OVERLAP,
                        help='Number of products in overlap set')
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load data
    df = load_diagnostic(args.input)

    # Create overlap set and private batches
    overlap, remaining = select_overlap_set(df, n=args.n_overlap)
    batches = create_batches(remaining, n_batches=4)

    # Save overlap CSV — same file for all annotators
    # Each annotator gets a copy with their name pre-filled
    for letter, name in ANNOTATORS.items():
        overlap_out = add_annotation_columns(overlap, name, 'overlap')
        path = output_dir / f'annotation_overlap_{letter}.csv'
        overlap_out.to_csv(path, index=False)

    print(f"\nSaved overlap CSVs for each annotator")

    # Save private batch CSVs
    for letter, name in ANNOTATORS.items():
        batch_out = add_annotation_columns(batches[letter], name, 'private')
        path = output_dir / f'annotation_batch_{letter}.csv'
        batch_out.to_csv(path, index=False)
        print(f"Saved batch {letter} ({name}): {len(batches[letter])} products → {path}")

    # Print and save summary
    summary = save_summary(overlap, batches, ANNOTATORS, output_dir)
    print(summary)

    print(f"\nAll files saved to: {output_dir.resolve()}")
    print("\nNext step: share each annotator's files with them via the group.")


if __name__ == '__main__':
    main()
