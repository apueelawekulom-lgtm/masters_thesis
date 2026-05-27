"""
BACI loader.

Reads the yearly BACI HS6 trade-flow CSVs from CEPII, filters to a target
importer (default: USA) and a target HS6 universe (default: the four
sectors defined in sectors.py), and writes a clean panel as Parquet.

BACI file conventions
---------------------
Yearly files: BACI_HS{rev}_Y{year}_V{vintage}.csv
    e.g. BACI_HS17_Y2020_V202501.csv
Columns:
    t : year (int)
    i : exporter CEPII code (int)
    j : importer CEPII code (int)
    k : HS6 code (string after we cast)
    v : value, thousand USD (float)
    q : quantity, tons (float, with NaNs)
Country code lookup:
    country_codes_V{vintage}.csv with columns including:
        country_code, country_name, country_iso2, country_iso3

Important: read `k` as string from the start so leading zeros are preserved.

Usage
-----
    from baci_loader import load_baci_panel
    panel = load_baci_panel(
        baci_dir="/path/to/baci",
        years=range(2017, 2025),
        importer_iso3="USA",
        sector_filter=True,
        output_path="baci_us_imports.parquet",
    )
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

from sectors import hs6_in_sectors

logger = logging.getLogger(__name__)


# CEPII country codes for the most common importers used in this thesis.
# These are stable across BACI vintages.
_CEPII_CODES_FALLBACK = {
    "USA": 842,
    "CHN": 156,
    "VNM": 704,
    "MEX": 484,
    "TWN": 158,
    "BGD": 50,
    "IND": 699,  # CEPII uses 699 for India in some vintages; verify against country_codes file
    "THA": 764,
    "MYS": 458,
    "KHM": 116,
    "DEU": 276,
    "JPN": 392,
    "KOR": 410,
}


def _baci_filename_pattern(hs_revision: str) -> re.Pattern:
    """Regex matching BACI yearly files for a given HS revision."""
    return re.compile(
        rf"BACI_{hs_revision}_Y(?P<year>\d{{4}})_V(?P<vintage>\d+)\.csv$"
    )


def discover_baci_files(
    baci_dir: Path | str, hs_revision: str = "HS17"
) -> dict[int, Path]:
    """
    Find all BACI yearly files in `baci_dir` matching the HS revision.

    Returns a dict mapping year -> path. If multiple vintages of the same
    year are present, the latest vintage wins.
    """
    baci_dir = Path(baci_dir)
    pattern = _baci_filename_pattern(hs_revision)
    found: dict[int, tuple[int, Path]] = {}
    for path in baci_dir.glob(f"BACI_{hs_revision}_Y*_V*.csv"):
        m = pattern.search(path.name)
        if not m:
            continue
        year = int(m.group("year"))
        vintage = int(m.group("vintage"))
        if year not in found or vintage > found[year][0]:
            found[year] = (vintage, path)
    return {year: path for year, (_, path) in found.items()}


def load_country_codes(
    baci_dir: Path | str, vintage: Optional[str] = None
) -> pd.DataFrame:
    """
    Load the BACI country-code lookup file.

    If `vintage` is None, picks the latest country_codes_V*.csv in the dir.
    Returns a DataFrame with at least:
        country_code (int), country_iso3 (str), country_name (str)
    """
    baci_dir = Path(baci_dir)
    if vintage is None:
        candidates = sorted(baci_dir.glob("country_codes_V*.csv"))
        if not candidates:
            raise FileNotFoundError(
                f"No country_codes_V*.csv in {baci_dir}; pass vintage explicitly."
            )
        path = candidates[-1]
    else:
        path = baci_dir / f"country_codes_V{vintage}.csv"
        if not path.exists():
            raise FileNotFoundError(path)

    df = pd.read_csv(path)
    # Column names vary slightly by vintage. Normalise.
    rename = {
        "country_code": "country_code",
        "country_iso3": "country_iso3",
        "iso_3digit_alpha": "country_iso3",  # older vintages
        "iso3": "country_iso3",
        "country_name_full": "country_name",
        "country_name": "country_name",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    keep = [c for c in ("country_code", "country_iso3", "country_name") if c in df.columns]
    return df[keep].copy()


def iso3_to_cepii(iso3: str | Iterable[str], country_codes: pd.DataFrame) -> int | list[int]:
    """Translate ISO3 country codes to CEPII numeric codes via the lookup."""
    lookup = (
        country_codes.dropna(subset=["country_iso3"])
        .set_index("country_iso3")["country_code"]
        .to_dict()
    )
    if isinstance(iso3, str):
        if iso3 in lookup:
            return int(lookup[iso3])
        if iso3 in _CEPII_CODES_FALLBACK:
            logger.warning("Using fallback CEPII code for %s", iso3)
            return _CEPII_CODES_FALLBACK[iso3]
        raise KeyError(f"ISO3 {iso3!r} not found in BACI country codes.")
    return [int(lookup[c]) if c in lookup else _CEPII_CODES_FALLBACK[c] for c in iso3]


def _read_one_year(path: Path) -> pd.DataFrame:
    """Read a single BACI yearly CSV with HS6 as string."""
    df = pd.read_csv(
        path,
        dtype={"k": "string", "i": "int32", "j": "int32", "t": "int16"},
        # value and quantity are floats; quantity has NaNs (denoted "           NA")
        na_values=["           NA", "NA", ""],
    )
    # BACI sometimes ships with whitespace-padded codes
    df["k"] = df["k"].str.strip().str.zfill(6)
    # Ensure value/quantity numeric
    df["v"] = pd.to_numeric(df["v"], errors="coerce")
    df["q"] = pd.to_numeric(df["q"], errors="coerce")
    return df


def load_baci_panel(
    baci_dir: Path | str,
    years: Iterable[int],
    importer_iso3: str | Iterable[str] = "USA",
    sector_filter: bool = True,
    hs6_filter: Optional[Iterable[str]] = None,
    hs_revision: str = "HS17",
    output_path: Optional[Path | str] = None,
    country_codes: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """
    Build a clean BACI panel restricted to one or more importers and a target
    HS6 universe.

    Parameters
    ----------
    baci_dir : path
        Directory containing yearly BACI_HS*_Y*_V*.csv files and a
        country_codes_V*.csv lookup.
    years : iterable of int
        Years to include in the panel.
    importer_iso3 : str or iterable of str
        ISO3 codes of importers to retain. Default "USA".
    sector_filter : bool
        If True, retain only HS6 codes belonging to any sector defined in
        sectors.py. Ignored if hs6_filter is given.
    hs6_filter : iterable of str, optional
        Explicit set of HS6 codes to retain. Overrides sector_filter if given.
    hs_revision : str
        HS revision suffix used in BACI filenames. Default "HS17".
    output_path : path, optional
        If given, write the resulting panel to Parquet at this path.
    country_codes : DataFrame, optional
        Pre-loaded country codes lookup. Loaded from baci_dir if None.

    Returns
    -------
    pd.DataFrame
        Panel with columns:
            t (year), i (exporter CEPII), j (importer CEPII),
            k (HS6 string), v (value, kUSD), q (quantity, tons),
            exporter_iso3, importer_iso3
    """
    baci_dir = Path(baci_dir)
    if country_codes is None:
        country_codes = load_country_codes(baci_dir)

    if isinstance(importer_iso3, str):
        importer_iso3 = [importer_iso3]
    importer_codes = {iso3: iso3_to_cepii(iso3, country_codes) for iso3 in importer_iso3}
    importer_codes_set = set(importer_codes.values())

    files = discover_baci_files(baci_dir, hs_revision=hs_revision)
    selected = {y: files[y] for y in years if y in files}
    missing = [y for y in years if y not in files]
    if missing:
        logger.warning("Missing BACI files for years: %s", missing)
    if not selected:
        raise FileNotFoundError(
            f"No BACI files found in {baci_dir} for years {list(years)}."
        )

    # Build HS6 filter mask
    explicit_filter = None
    if hs6_filter is not None:
        explicit_filter = set(s.zfill(6) for s in hs6_filter)

    chunks: list[pd.DataFrame] = []
    for year, path in sorted(selected.items()):
        logger.info("Reading %s", path.name)
        df = _read_one_year(path)
        df = df[df["j"].isin(importer_codes_set)]
        if explicit_filter is not None:
            df = df[df["k"].isin(explicit_filter)]
        elif sector_filter:
            df = df[hs6_in_sectors(df["k"])]
        chunks.append(df)

    panel = pd.concat(chunks, ignore_index=True)

    # Annotate with ISO3 codes for human readability
    iso3_lookup = country_codes.set_index("country_code")["country_iso3"]
    panel["exporter_iso3"] = panel["i"].map(iso3_lookup)
    panel["importer_iso3"] = panel["j"].map(iso3_lookup)

    panel = panel.sort_values(["t", "k", "i"]).reset_index(drop=True)

    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        panel.to_parquet(output_path, index=False)
        logger.info("Wrote panel to %s (%d rows)", output_path, len(panel))

    return panel


def summarise_panel(panel: pd.DataFrame) -> pd.DataFrame:
    """
    Quick descriptive summary of a loaded panel: rows by year, unique HS6,
    unique exporters.
    """
    return (
        panel.groupby("t")
        .agg(
            rows=("v", "size"),
            n_hs6=("k", "nunique"),
            n_exporters=("i", "nunique"),
            total_value_kusd=("v", "sum"),
        )
        .assign(total_value_busd=lambda d: d["total_value_kusd"] / 1e6)
    )
