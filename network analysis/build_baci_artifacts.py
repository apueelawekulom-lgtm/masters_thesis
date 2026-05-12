"""
Build the foundational BACI artifacts from the 30 per-year parquets.

Inputs  : BACI_HS92_V202601/baci_{1995..2024}.parquet, country_codes_V202601.csv
Outputs : BACI_HS92_V202601/baci_combined.parquet
          BACI_HS92_V202601/baci_edges_country.parquet

Streaming design (peak memory ~ one year's data, ~1.5 GB) so it runs on 16 GB.
Idempotent: re-running overwrites the two output parquets.
"""

from __future__ import annotations

import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).parent
BACI_DIR = ROOT / "BACI_HS92_V202601"
COUNTRY_CSV = BACI_DIR / "country_codes_V202601.csv"
COMBINED_OUT = BACI_DIR / "baci_combined.parquet"
COUNTRY_EDGES_OUT = BACI_DIR / "baci_edges_country.parquet"

YEAR_GLOB = "baci_[0-9]*.parquet"

ARROW_SCHEMA = pa.schema([
    ("t", pa.int16()),
    ("k", pa.string()),
    ("v", pa.float32()),
    ("q", pa.float32()),
    ("iso3_exporter", pa.string()),
    ("iso3_importer", pa.string()),
    ("hs2", pa.string()),
])


def load_code_to_iso3() -> dict[int, str]:
    cc = pd.read_csv(COUNTRY_CSV)
    return dict(zip(cc["country_code"].astype("int32"), cc["country_iso3"]))


def process_one_year(
    year_path: Path,
    code_to_iso3: dict[int, str],
    writer: pq.ParquetWriter,
    accumulator: dict[tuple[int, str, str], float],
) -> tuple[int, int]:
    """Read one year, clean, map ISO3, write to combined, aggregate to accumulator.

    Returns (rows_in, rows_out)
    """
    df = pd.read_parquet(year_path)
    rows_in = len(df)

    # 1. Drop invalid rows
    df = df[df["v"].notna() & (df["v"] > 0) & (df["i"] != df["j"])]

    # 2. Map numeric country codes → ISO3
    iso3_exp = df["i"].map(code_to_iso3)
    iso3_imp = df["j"].map(code_to_iso3)
    mask = iso3_exp.notna() & iso3_imp.notna()
    df = df.loc[mask].copy()
    df["iso3_exporter"] = iso3_exp.loc[mask].astype("category")
    df["iso3_importer"] = iso3_imp.loc[mask].astype("category")

    # 3. HS2 chapter
    df["hs2"] = df["k"].str[:2].astype("category")

    # 4. Drop integer codes
    df = df.drop(columns=["i", "j"])

    # 5. Aggregate to (year, source, target) — value in USD thousands
    grouped = df.groupby(["t", "iso3_exporter", "iso3_importer"], observed=True)["v"].sum()
    for (yr, src, tgt), val in grouped.items():
        accumulator[(int(yr), src, tgt)] += float(val)

    # 6. Append to combined parquet
    table = pa.Table.from_pandas(df, schema=ARROW_SCHEMA, preserve_index=False)
    writer.write_table(table)

    return rows_in, len(df)


def main() -> None:
    assert BACI_DIR.exists(), f"Missing BACI directory: {BACI_DIR}"
    code_to_iso3 = load_code_to_iso3()
    print(f"[setup] loaded {len(code_to_iso3)} country codes")

    year_paths = sorted(BACI_DIR.glob(YEAR_GLOB))
    # Filter to actual per-year files (exclude any combined output)
    year_paths = [p for p in year_paths if p.stem.removeprefix("baci_").isdigit()]
    print(f"[setup] found {len(year_paths)} per-year parquets ({year_paths[0].name} → {year_paths[-1].name})")

    accumulator: dict[tuple[int, str, str], float] = defaultdict(float)
    total_in = total_out = 0

    t0 = time.time()
    with pq.ParquetWriter(
        COMBINED_OUT,
        schema=ARROW_SCHEMA,
        compression="snappy",
    ) as writer:
        for yp in year_paths:
            t = time.time()
            ri, ro = process_one_year(yp, code_to_iso3, writer, accumulator)
            total_in += ri
            total_out += ro
            print(
                f"  {yp.stem:>13s}  in={ri:>10,}  out={ro:>10,}  "
                f"edges_acc={len(accumulator):>8,}  dt={time.time()-t:5.1f}s"
            )

    print(f"[combined] rows in={total_in:,}  out={total_out:,}  "
          f"file={COMBINED_OUT.stat().st_size/1e9:.2f} GB  total={time.time()-t0:.1f}s")

    # Build country edges dataframe
    records = [
        {"year": yr, "source": src, "target": tgt, "value_kusd": v}
        for (yr, src, tgt), v in accumulator.items()
    ]
    ce = pd.DataFrame.from_records(records)
    # Convert USD thousands → USD billions for downstream consistency w/ existing notebook
    ce["value_busd"] = ce["value_kusd"] / 1_000_000
    ce = ce[["year", "source", "target", "value_kusd", "value_busd"]]
    ce["source"] = ce["source"].astype("category")
    ce["target"] = ce["target"].astype("category")
    ce.to_parquet(COUNTRY_EDGES_OUT, engine="pyarrow", compression="snappy", index=False)

    print(f"[country_edges] rows={len(ce):,}  years={ce['year'].nunique()}  "
          f"file={COUNTRY_EDGES_OUT.stat().st_size/1e6:.1f} MB")
    print(f"  yr range: {ce['year'].min()}–{ce['year'].max()}")
    print(f"  value_busd: min={ce['value_busd'].min():.6f}  "
          f"median={ce['value_busd'].median():.4f}  "
          f"mean={ce['value_busd'].mean():.4f}  "
          f"max={ce['value_busd'].max():.2f}")


if __name__ == "__main__":
    main()
