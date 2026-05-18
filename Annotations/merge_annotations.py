"""
GVC Annotation Merge & Agreement Analysis
==========================================
Merges annotation CSVs from all 4 annotators and computes inter-annotator
agreement on the overlap set.

Usage:
    python merge_annotations.py
    python merge_annotations.py --annotation_dir ./annotations

Expects files named:
    annotation_overlap_A_done.csv   (Apuela's overlap labels)
    annotation_overlap_B_done.csv   (Rhea's overlap labels)
    annotation_overlap_C_done.csv   (Michelle's overlap labels)
    annotation_overlap_D_done.csv   (Olivia's overlap labels)
    annotation_batch_A_done.csv     (Apuela's private labels)
    ... etc.

Output:
    annotations_merged.csv          (full labeled dataset)
    agreement_report.txt            (kappa scores + disagreement analysis)
    disagreements_for_review.csv    (overlap products where annotators disagree)
"""

import pandas as pd
import numpy as np
import argparse
from pathlib import Path
from itertools import combinations

# ── Agreement metrics ──────────────────────────────────────────────────────────

def cohens_kappa(labels_a, labels_b):
    """
    Compute Cohen's kappa between two annotators on the same products.
    Returns kappa score and observed/expected agreement.
    """
    assert len(labels_a) == len(labels_b), "Label lists must be same length"
    n = len(labels_a)
    if n == 0:
        return None, None, None

    classes = sorted(set(labels_a) | set(labels_b))
    n_classes = len(classes)
    class_idx = {c: i for i, c in enumerate(classes)}

    # Confusion matrix
    cm = np.zeros((n_classes, n_classes), dtype=int)
    for a, b in zip(labels_a, labels_b):
        if pd.isna(a) or pd.isna(b):
            continue
        cm[class_idx[int(a)], class_idx[int(b)]] += 1

    n_valid = cm.sum()
    if n_valid == 0:
        return None, None, None

    # Observed agreement
    p_o = np.diag(cm).sum() / n_valid

    # Expected agreement
    row_sums = cm.sum(axis=1) / n_valid
    col_sums = cm.sum(axis=0) / n_valid
    p_e = (row_sums * col_sums).sum()

    if p_e == 1.0:
        kappa = 1.0
    else:
        kappa = (p_o - p_e) / (1 - p_e)

    return round(kappa, 4), round(p_o, 4), round(p_e, 4)


def interpret_kappa(kappa):
    if kappa is None: return "N/A"
    if kappa >= 0.8:  return "Almost perfect"
    if kappa >= 0.6:  return "Substantial"
    if kappa >= 0.4:  return "Moderate"
    if kappa >= 0.2:  return "Fair"
    return "Poor — review annotation guidelines"


# ── Load annotations ───────────────────────────────────────────────────────────

def load_annotation_file(path):
    """Load a completed annotation CSV and validate required columns."""
    df = pd.read_csv(path, dtype={'subheading': str})
    df['subheading'] = df['subheading'].astype(str).str.zfill(6)

    required = ['annotator', 'subheading', 'label']
    missing = [c for c in required if c not in df.columns]
    if missing:
        print(f"  WARNING: {path.name} missing columns: {missing}")
        return None

    # Drop unannotated rows
    df = df[df['label'].astype(str).str.strip() != ''].copy()
    df['label'] = pd.to_numeric(df['label'], errors='coerce')
    df = df.dropna(subset=['label'])
    df['label'] = df['label'].astype(int)

    return df


def load_all_annotations(annotation_dir):
    """Load all completed annotation files from directory."""
    annotation_dir = Path(annotation_dir)
    overlap_dfs = []
    private_dfs = []

    for letter in ['A', 'B', 'C', 'D']:
        # Try both naming conventions (_done suffix or not)
        for suffix in ['_done', '']:
            ov_path = annotation_dir / f'annotation_overlap_{letter}{suffix}.csv'
            pr_path = annotation_dir / f'annotation_batch_{letter}{suffix}.csv'

            if ov_path.exists():
                df = load_annotation_file(ov_path)
                if df is not None:
                    df['batch_source'] = f'overlap_{letter}'
                    overlap_dfs.append(df)
                    print(f"  Loaded overlap {letter}: {len(df)} annotations")
                break

        for suffix in ['_done', '']:
            pr_path = annotation_dir / f'annotation_batch_{letter}{suffix}.csv'
            if pr_path.exists():
                df = load_annotation_file(pr_path)
                if df is not None:
                    df['batch_source'] = f'private_{letter}'
                    private_dfs.append(df)
                    print(f"  Loaded batch {letter}: {len(df)} annotations")
                break

    return overlap_dfs, private_dfs


# ── Agreement analysis ─────────────────────────────────────────────────────────

def compute_agreement(overlap_dfs):
    """
    Compute pairwise Cohen's kappa for all annotator pairs on overlap products.
    Returns a summary dataframe and disagreement details.
    """
    if len(overlap_dfs) < 2:
        print("  Need at least 2 annotators' overlap annotations to compute agreement.")
        return None, None

    # Pivot to wide format: rows=products, cols=annotators
    all_overlap = pd.concat(overlap_dfs, ignore_index=True)
    annotators = all_overlap['annotator'].unique()

    pivot = all_overlap.pivot_table(
        index='subheading',
        columns='annotator',
        values='label',
        aggfunc='first'
    ).reset_index()

    print(f"\nOverlap products with at least 1 annotation: {len(pivot)}")
    complete = pivot.dropna()
    print(f"Products with all annotators' labels: {len(complete)}")

    # Pairwise kappa
    results = []
    for a1, a2 in combinations(annotators, 2):
        if a1 not in pivot.columns or a2 not in pivot.columns:
            continue
        pair_df = pivot[[a1, a2]].dropna()
        if len(pair_df) < 5:
            print(f"  Skipping {a1}/{a2} — too few shared products ({len(pair_df)})")
            continue
        kappa, p_o, p_e = cohens_kappa(pair_df[a1].tolist(), pair_df[a2].tolist())
        results.append({
            'annotator_1': a1,
            'annotator_2': a2,
            'n_shared': len(pair_df),
            'kappa': kappa,
            'observed_agreement': p_o,
            'expected_agreement': p_e,
            'interpretation': interpret_kappa(kappa),
        })

    kappa_df = pd.DataFrame(results)

    # Overall kappa (Fleiss' approximation using mean of pairwise)
    if len(results) > 0:
        mean_kappa = kappa_df['kappa'].mean()
        print(f"\nMean pairwise kappa: {mean_kappa:.3f} ({interpret_kappa(mean_kappa)})")

    # Disagreement analysis
    disagreements = []
    for _, row in pivot.iterrows():
        labels = [row[a] for a in annotators if a in row.index and not pd.isna(row[a])]
        if len(labels) < 2:
            continue
        if len(set(labels)) > 1:
            entry = {'subheading': row['subheading']}
            for a in annotators:
                if a in row.index:
                    entry[f'label_{a}'] = row[a]
            entry['n_unique_labels'] = len(set(labels))
            entry['labels'] = str(sorted([int(l) for l in labels if not pd.isna(l)]))
            disagreements.append(entry)

    disagree_df = pd.DataFrame(disagreements) if disagreements else pd.DataFrame()
    print(f"Products with disagreement: {len(disagree_df)}")

    return kappa_df, disagree_df, pivot


# ── Merge to final dataset ─────────────────────────────────────────────────────

def create_final_dataset(overlap_dfs, private_dfs, pivot=None):
    """
    Create the final merged annotation dataset.

    For overlap products: use majority vote label, flag if split.
    For private products: use the single annotator's label.

    Returns merged dataframe ready for SetFit training.
    """
    records = []

    # ── Overlap products: majority vote ──
    if overlap_dfs and pivot is not None:
        all_overlap = pd.concat(overlap_dfs, ignore_index=True)
        annotators = all_overlap['annotator'].unique()

        for _, row in pivot.iterrows():
            labels = [row[a] for a in annotators if a in row.index and not pd.isna(row[a])]
            if not labels:
                continue

            # Majority vote
            from collections import Counter
            vote = Counter([int(l) for l in labels])
            majority_label = vote.most_common(1)[0][0]
            n_agree = vote.most_common(1)[0][1]
            unanimous = len(set(int(l) for l in labels)) == 1

            # Get metadata from first annotator's record
            meta = all_overlap[all_overlap['subheading'] == row['subheading']].iloc[0]

            records.append({
                'subheading': row['subheading'],
                'subheading_text': meta.get('subheading_text', ''),
                'domain': meta.get('domain', ''),
                'chapter': meta.get('chapter', ''),
                'nli_class': meta.get('nli_class', ''),
                'nli_uncertainty': meta.get('nli_uncertainty', ''),
                'label': majority_label,
                'stage_name': _stage_name(majority_label),
                'source': 'overlap',
                'n_annotators': len(labels),
                'n_agree': n_agree,
                'unanimous': unanimous,
                'flagged': any(str(meta.get('flagged', '')).upper() == 'Y'
                               for _, meta in all_overlap[
                                   all_overlap['subheading'] == row['subheading']
                               ].iterrows()),
                'annotators': ','.join(sorted(annotators)),
            })

    # ── Private products: single annotator ──
    for df in private_dfs:
        for _, row in df.iterrows():
            records.append({
                'subheading': row['subheading'],
                'subheading_text': row.get('subheading_text', ''),
                'domain': row.get('domain', ''),
                'chapter': row.get('chapter', ''),
                'nli_class': row.get('nli_class', ''),
                'nli_uncertainty': row.get('nli_uncertainty', ''),
                'label': int(row['label']),
                'stage_name': _stage_name(int(row['label'])),
                'source': 'private',
                'n_annotators': 1,
                'n_agree': 1,
                'unanimous': True,
                'flagged': str(row.get('flagged', '')).upper() == 'Y',
                'annotators': row.get('annotator', ''),
            })

    return pd.DataFrame(records)


def _stage_name(stage):
    names = {1:'Raw/Unprocessed', 2:'Primary Processed', 3:'Fabricated Material',
             4:'Manufactured Component', 5:'Assembled/Finished'}
    return names.get(stage, f'S{stage}')


# ── Report generation ──────────────────────────────────────────────────────────

def generate_report(kappa_df, disagree_df, merged_df, output_dir):
    """Generate a human-readable agreement report."""
    lines = []
    lines.append("=" * 70)
    lines.append("GVC ANNOTATION — INTER-ANNOTATOR AGREEMENT REPORT")
    lines.append("=" * 70)

    if kappa_df is not None and len(kappa_df) > 0:
        lines.append("\nPAIRWISE COHEN'S KAPPA (overlap set)")
        lines.append("-" * 50)
        for _, row in kappa_df.iterrows():
            lines.append(f"  {row['annotator_1']} vs {row['annotator_2']}: "
                        f"κ = {row['kappa']:.3f}  ({row['interpretation']})  "
                        f"[n={row['n_shared']}, p_o={row['observed_agreement']:.2f}]")

        mean_k = kappa_df['kappa'].mean()
        lines.append(f"\n  Mean pairwise κ: {mean_k:.3f}  ({interpret_kappa(mean_k)})")

        lines.append("\nKAPPA INTERPRETATION GUIDE:")
        lines.append("  ≥ 0.80  Almost perfect  → proceed to SetFit")
        lines.append("  0.60–0.79  Substantial  → proceed with caution, review flagged")
        lines.append("  0.40–0.59  Moderate     → review guidelines, re-annotate uncertain cases")
        lines.append("  < 0.40     Poor         → stop, revise guidelines, recalibrate")

    if disagree_df is not None and len(disagree_df) > 0:
        lines.append(f"\nDISAGREEMENTS ({len(disagree_df)} products)")
        lines.append("-" * 50)
        lines.append("  These products should be discussed as a team.")
        lines.append("  Products flagged by ≥1 annotator are highest priority.")
        for _, row in disagree_df.head(15).iterrows():
            lines.append(f"  {row['subheading']}  labels={row['labels']}  "
                        f"n_unique={row['n_unique_labels']}")

    if merged_df is not None and len(merged_df) > 0:
        lines.append(f"\nFINAL DATASET SUMMARY")
        lines.append("-" * 50)
        lines.append(f"  Total labeled products: {len(merged_df)}")
        lines.append(f"  Unanimous labels: {merged_df['unanimous'].sum()} "
                    f"({merged_df['unanimous'].mean():.0%})")
        lines.append(f"  Flagged boundary cases: {merged_df['flagged'].sum()}")

        lines.append("\n  Label distribution:")
        dist = merged_df.groupby(['label', 'stage_name'])['subheading'].count()
        for (label, name), count in dist.items():
            pct = count / len(merged_df) * 100
            lines.append(f"    S{label} {name:<25} {count:>4} ({pct:.0f}%)")

        lines.append("\n  By domain:")
        for domain in ['D4', 'D5']:
            sub = merged_df[merged_df['domain'] == domain]
            if len(sub) == 0:
                continue
            lines.append(f"  {domain}:")
            dist = sub.groupby('label')['subheading'].count()
            for label, count in dist.items():
                lines.append(f"    S{label}: {count}")

        lines.append("\n  SetFit readiness:")
        min_class = merged_df.groupby('label')['subheading'].count().min()
        if min_class >= 10:
            lines.append(f"  ✓ Min examples per class: {min_class} — sufficient for SetFit seed run")
        else:
            lines.append(f"  ✗ Min examples per class: {min_class} — need more annotations")
            lines.append("    Target: ≥10 per class for seed run, ≥50 for stable SetFit")

    report = '\n'.join(lines)
    path = output_dir / 'agreement_report.txt'
    with open(path, 'w') as f:
        f.write(report)
    print(report)
    return report


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Merge GVC annotations and compute agreement')
    parser.add_argument('--annotation_dir', default='.',
                        help='Directory containing completed annotation CSVs')
    parser.add_argument('--output_dir', default='.',
                        help='Directory for output files')
    args = parser.parse_args()

    annotation_dir = Path(args.annotation_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Loading annotation files...")
    overlap_dfs, private_dfs = load_all_annotations(annotation_dir)

    if not overlap_dfs and not private_dfs:
        print("No annotation files found. Check directory and file naming.")
        return

    # Agreement analysis on overlap set
    print("\nComputing inter-annotator agreement...")
    result = compute_agreement(overlap_dfs)
    if result and len(result) == 3:
        kappa_df, disagree_df, pivot = result
    else:
        kappa_df, disagree_df, pivot = None, None, None

    # Save disagreements for team review
    if disagree_df is not None and len(disagree_df) > 0:
        # Enrich with product descriptions
        all_ann = pd.concat(overlap_dfs, ignore_index=True)
        desc_map = all_ann.drop_duplicates('subheading').set_index('subheading')['subheading_text'].to_dict()
        disagree_df['subheading_text'] = disagree_df['subheading'].map(desc_map)
        disagree_df.to_csv(output_dir / 'disagreements_for_review.csv', index=False)
        print(f"Saved {len(disagree_df)} disagreements → disagreements_for_review.csv")

    # Merge to final dataset
    print("\nCreating final merged dataset...")
    merged_df = create_final_dataset(overlap_dfs, private_dfs, pivot)
    merged_df.to_csv(output_dir / 'annotations_merged.csv', index=False)
    print(f"Saved {len(merged_df)} labeled products → annotations_merged.csv")

    # Generate report
    print("\nGenerating agreement report...")
    generate_report(kappa_df, disagree_df, merged_df, output_dir)
    print(f"\nAll outputs saved to: {output_dir.resolve()}")
    print("\nNext step: use annotations_merged.csv as input to SetFit training.")


if __name__ == '__main__':
    main()
