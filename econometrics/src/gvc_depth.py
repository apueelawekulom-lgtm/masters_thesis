"""
GVC depth measure construction.

Builds a layered HS6-level GVC depth measure from three components:

    (1) Foreign Value-Added share (FVA share) at industry level, from TiVA.
    (2) Upstreamness at industry level, from Antras-Chor or computed.
    (3) BEC intermediate-goods indicator at HS6 level, from UN BEC concordance.

Components 1 and 2 are industry-level (ISIC Rev. 4) and are mapped down to HS6
via an HS6 -> ISIC concordance. Component 3 is native HS6.

The combined measure is a weighted z-score:

    GVC_depth_z(k) = w1 * z(FVA_share(ISIC(k)))
                   + w2 * z(upstreamness(ISIC(k)))
                   + w3 * z(BEC_intermediate(k))

A categorical tier is also produced (high / medium / low) using terciles of
the continuous measure within sample.

Expected input file schemas
---------------------------
hs6_isic_path : CSV with at least columns:
    hs6, isic4
    (one row per HS6; if multi-mapped, take modal or trade-weighted choice
     before passing to this module.)

hs6_bec_path : CSV with at least columns:
    hs6, bec
    where `bec` is the BEC Rev. 4 or Rev. 5 category code as string
    (e.g., "111", "22", "42", "53", "61"). The intermediate-goods set is
    defined below in BEC_INTERMEDIATE_REV4.

fva_share_path : CSV with at least columns:
    isic4, fva_share
    (long format: one row per ISIC4 industry. If you have country-level
     FVA shares from TiVA, aggregate to the relevant exporter set or just
     use China as the reference exporter, depending on your design.)
    Optionally:
        country_iso3, year
    (Pass `fva_country` and `fva_year` to filter; otherwise the full file
     is averaged.)

upstreamness_path : CSV with at least columns:
    isic4, upstreamness
    Optionally:
        country_iso3
    (Antras-Chor publish per-country upstreamness; pick a reference country
     or average across the relevant set.)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# -------------------------------------------------------------------
# BEC intermediate-goods classification
# -------------------------------------------------------------------
# BEC Rev. 4 (UN classification): codes that count as INTERMEDIATE
# - 111: food/beverages, primary, mainly for industry
# - 121: food/beverages, processed, mainly for industry
# - 21:  industrial supplies nes, primary
# - 22:  industrial supplies nes, processed
# - 31:  fuels and lubricants, primary
# - 322: fuels and lubricants, processed (other than motor spirit)
# - 42:  parts and accessories of capital goods
# - 53:  parts and accessories of transport equipment
BEC_INTERMEDIATE_REV4 = frozenset({"111", "121", "21", "22", "31", "322", "42", "53"})

# Capital goods (used as a separate indicator if you want a 3-tier modulator
# rather than binary intermediate dummy).
BEC_CAPITAL_REV4 = frozenset({"41", "521"})


# -------------------------------------------------------------------
# Loaders
# -------------------------------------------------------------------
def load_hs6_isic(path: Path | str) -> pd.DataFrame:
    """Load HS6 -> ISIC4 concordance. Returns DataFrame[hs6, isic4]."""
    df = pd.read_csv(path, dtype={"hs6": "string", "isic4": "string"})
    df["hs6"] = df["hs6"].str.strip().str.zfill(6)
    df["isic4"] = df["isic4"].str.strip()
    if df["hs6"].duplicated().any():
        n_dup = df["hs6"].duplicated().sum()
        logger.warning(
            "HS6->ISIC concordance contains %d duplicate HS6 entries; "
            "keeping first occurrence (consider trade-weighted resolution).",
            n_dup,
        )
        df = df.drop_duplicates("hs6", keep="first")
    return df.reset_index(drop=True)


def load_hs6_bec(path: Path | str) -> pd.DataFrame:
    """
    Load HS6 -> BEC concordance.
    Returns DataFrame[hs6, bec, bec_intermediate, bec_capital, bec_consumer].
    """
    df = pd.read_csv(path, dtype={"hs6": "string", "bec": "string"})
    df["hs6"] = df["hs6"].str.strip().str.zfill(6)
    df["bec"] = df["bec"].str.strip()
    if df["hs6"].duplicated().any():
        df = df.drop_duplicates("hs6", keep="first")
    df["bec_intermediate"] = df["bec"].isin(BEC_INTERMEDIATE_REV4).astype("int8")
    df["bec_capital"] = df["bec"].isin(BEC_CAPITAL_REV4).astype("int8")
    df["bec_consumer"] = (
        (df["bec_intermediate"] == 0) & (df["bec_capital"] == 0)
    ).astype("int8")
    return df.reset_index(drop=True)


def load_fva_share(
    path: Path | str,
    country_iso3: Optional[str] = None,
    year: Optional[int] = None,
) -> pd.DataFrame:
    """
    Load TiVA-derived FVA shares at ISIC4 level.
    Returns DataFrame[isic4, fva_share].

    If the input file has country / year columns, optionally filter to a
    specific country and year. Otherwise, average across whatever rows exist.
    """
    df = pd.read_csv(path)
    df.columns = [c.lower() for c in df.columns]
    if "isic4" not in df.columns:
        raise KeyError("FVA share file must have an 'isic4' column.")
    if "fva_share" not in df.columns:
        raise KeyError("FVA share file must have a 'fva_share' column.")
    df["isic4"] = df["isic4"].astype(str).str.strip()
    if country_iso3 is not None and "country_iso3" in df.columns:
        df = df[df["country_iso3"] == country_iso3]
    if year is not None and "year" in df.columns:
        df = df[df["year"] == year]
    out = df.groupby("isic4", as_index=False)["fva_share"].mean()
    return out


def load_upstreamness(
    path: Path | str, country_iso3: Optional[str] = None
) -> pd.DataFrame:
    """
    Load Antras-Chor upstreamness at ISIC4 level.
    Returns DataFrame[isic4, upstreamness].
    """
    df = pd.read_csv(path)
    df.columns = [c.lower() for c in df.columns]
    if "isic4" not in df.columns:
        raise KeyError("Upstreamness file must have an 'isic4' column.")
    if "upstreamness" not in df.columns:
        raise KeyError("Upstreamness file must have an 'upstreamness' column.")
    df["isic4"] = df["isic4"].astype(str).str.strip()
    if country_iso3 is not None and "country_iso3" in df.columns:
        df = df[df["country_iso3"] == country_iso3]
    return df.groupby("isic4", as_index=False)["upstreamness"].mean()


# -------------------------------------------------------------------
# Combined measure
# -------------------------------------------------------------------
@dataclass
class GVCDepthConfig:
    """Configuration for the combined GVC depth measure."""

    weights: tuple[float, float, float] = (1 / 3, 1 / 3, 1 / 3)
    # weights apply to (fva_share, upstreamness, bec_intermediate) z-scores
    tier_quantiles: tuple[float, float] = (1 / 3, 2 / 3)
    # quantile cutoffs for low/medium/high tier classification
    fva_country: Optional[str] = None
    fva_year: Optional[int] = None
    upstreamness_country: Optional[str] = None


def _zscore(s: pd.Series) -> pd.Series:
    """Standardise a Series; preserves NaN."""
    mu = s.mean()
    sd = s.std(ddof=0)
    if sd == 0 or np.isnan(sd):
        return s - mu  # all zeros (or NaN-preserving)
    return (s - mu) / sd


def build_gvc_depth(
    hs6_codes: pd.Series,
    hs6_isic_path: Path | str,
    hs6_bec_path: Path | str,
    fva_share_path: Path | str,
    upstreamness_path: Path | str,
    config: Optional[GVCDepthConfig] = None,
) -> pd.DataFrame:
    """
    Construct the layered GVC depth measure for a set of HS6 codes.

    Parameters
    ----------
    hs6_codes : pd.Series
        HS6 codes to compute the measure for. Should be 6-digit strings.
    hs6_isic_path, hs6_bec_path, fva_share_path, upstreamness_path : path
        Input concordances and component data files. See module docstring
        for expected schemas.
    config : GVCDepthConfig, optional
        Weighting and country/year filters.

    Returns
    -------
    pd.DataFrame indexed by hs6, with columns:
        isic4, bec, bec_intermediate, bec_capital, bec_consumer,
        fva_share, upstreamness,
        fva_share_z, upstreamness_z, bec_intermediate_z,
        gvc_depth_z, gvc_tier
    """
    if config is None:
        config = GVCDepthConfig()

    hs6_set = pd.DataFrame({"hs6": hs6_codes.astype("string").str.zfill(6).unique()})

    # 1. HS6 -> ISIC concordance
    hs2isic = load_hs6_isic(hs6_isic_path)
    df = hs6_set.merge(hs2isic, on="hs6", how="left")
    if df["isic4"].isna().any():
        n = df["isic4"].isna().sum()
        logger.warning("%d HS6 codes missing ISIC4 mapping; will get NaN GVC scores.", n)

    # 2. HS6 -> BEC
    hs2bec = load_hs6_bec(hs6_bec_path)
    df = df.merge(hs2bec, on="hs6", how="left")
    if df["bec"].isna().any():
        logger.warning(
            "%d HS6 codes missing BEC mapping; bec_intermediate will be 0.",
            df["bec"].isna().sum(),
        )
    df["bec_intermediate"] = df["bec_intermediate"].fillna(0).astype("int8")
    df["bec_capital"] = df["bec_capital"].fillna(0).astype("int8")
    df["bec_consumer"] = df["bec_consumer"].fillna(0).astype("int8")

    # 3. FVA share (industry-level, mapped via ISIC4)
    fva = load_fva_share(
        fva_share_path,
        country_iso3=config.fva_country,
        year=config.fva_year,
    )
    df = df.merge(fva, on="isic4", how="left")

    # 4. Upstreamness (industry-level, mapped via ISIC4)
    ups = load_upstreamness(
        upstreamness_path, country_iso3=config.upstreamness_country
    )
    df = df.merge(ups, on="isic4", how="left")

    # 5. Standardise components
    df["fva_share_z"] = _zscore(df["fva_share"])
    df["upstreamness_z"] = _zscore(df["upstreamness"])
    df["bec_intermediate_z"] = _zscore(df["bec_intermediate"].astype("float"))

    # 6. Combined depth score (weighted)
    w1, w2, w3 = config.weights
    df["gvc_depth_z"] = (
        w1 * df["fva_share_z"].fillna(0)
        + w2 * df["upstreamness_z"].fillna(0)
        + w3 * df["bec_intermediate_z"].fillna(0)
    )
    # Re-introduce NaN if all three components were missing
    all_missing = (
        df["fva_share_z"].isna()
        & df["upstreamness_z"].isna()
        & df["bec_intermediate_z"].isna()
    )
    df.loc[all_missing, "gvc_depth_z"] = np.nan

    # 7. Tier classification (low/medium/high) by terciles
    q_low, q_high = config.tier_quantiles
    cuts = df["gvc_depth_z"].quantile([q_low, q_high]).values
    df["gvc_tier"] = pd.cut(
        df["gvc_depth_z"],
        bins=[-np.inf, cuts[0], cuts[1], np.inf],
        labels=["low", "medium", "high"],
    )

    return df.set_index("hs6")


# -------------------------------------------------------------------
# Diagnostics
# -------------------------------------------------------------------
def variance_decomposition(
    gvc: pd.DataFrame, sector_labels: pd.Series, score: str = "gvc_depth_z"
) -> pd.DataFrame:
    """
    One-way ANOVA decomposition of GVC depth variance into within- and
    between-sector components. Returns a one-row DataFrame with the F stat
    and within/between variance shares.

    The thesis methods should report this to demonstrate that the four-sector
    design is not throwing away within-sector variation.
    """
    aligned = gvc.assign(sector=sector_labels.values).dropna(subset=[score, "sector"])
    overall_mean = aligned[score].mean()
    grand_var = ((aligned[score] - overall_mean) ** 2).sum()
    group_means = aligned.groupby("sector", observed=True)[score].agg(["mean", "size"])
    between = (group_means["size"] * (group_means["mean"] - overall_mean) ** 2).sum()
    within = grand_var - between
    n = len(aligned)
    k = aligned["sector"].nunique()
    if k < 2 or n - k < 1:
        f_stat = np.nan
    else:
        f_stat = (between / (k - 1)) / (within / (n - k))
    return pd.DataFrame(
        {
            "n_obs": [n],
            "n_sectors": [k],
            "between_share": [between / grand_var if grand_var > 0 else np.nan],
            "within_share": [within / grand_var if grand_var > 0 else np.nan],
            "f_stat": [f_stat],
        }
    )


def face_validity_check(gvc: pd.DataFrame) -> pd.DataFrame:
    """
    Print the GVC depth scores for a set of canonical HS6 codes, as a
    sanity check that the measure produces the expected ordering.
    Returns the subset of `gvc` containing those codes.
    """
    canonical = {
        "854231": "Semiconductors (electronic ICs, processors)",
        "847330": "Parts of automatic data-processing machines",
        "851712": "Smartphones / cellular network phones",
        "847130": "Portable ADP machines (laptops)",
        "852872": "Colour reception apparatus / TVs",
        "940360": "Wooden furniture nesoi",
        "940161": "Upholstered seats with wooden frames",
        "940429": "Mattresses (other than cellular plastic)",
        "610910": "T-shirts of cotton, knitted",
        "620342": "Men's trousers of cotton",
    }
    keys = [k for k in canonical if k in gvc.index]
    out = gvc.loc[keys].copy()
    out["description"] = [canonical[k] for k in keys]
    cols = ["description", "isic4", "bec", "fva_share", "upstreamness", "gvc_depth_z", "gvc_tier"]
    return out[cols]
