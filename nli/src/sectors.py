"""
Sector definitions for the GVC × China-shock thesis.

Each sector is defined by a tuple of HS chapter prefixes (2-digit strings).
Membership in a sector is determined by HS6.startswith(prefix) for any prefix
in the tuple.

The four-sector design gives a 2x2 in (GVC depth, tariff exposure):
    Electronics : high GVC, heavy 2018 tariff exposure
    Machinery   : high GVC, heavy 2018 tariff exposure
    Apparel     : low  GVC, partial 2018 tariff exposure
    Furniture   : medium GVC, heavy 2018 tariff exposure

Note: Electronics (HS 85) and Machinery (HS 84) overlap conceptually for
computers/laptops (HS 8471), which sits in HS 84 chapter but is functionally
electronics. The default treatment here puts HS 84 in Machinery and HS 85 in
Electronics. Document this choice in the thesis methods.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class Sector:
    name: str
    chapters: tuple[str, ...]
    description: str

    def matches(self, hs6: str) -> bool:
        return any(hs6.startswith(c) for c in self.chapters)


SECTORS: dict[str, Sector] = {
    "electronics": Sector(
        name="electronics",
        chapters=("85",),
        description="HS 85 — Electrical machinery, equipment, parts. High GVC depth.",
    ),
    "machinery": Sector(
        name="machinery",
        chapters=("84",),
        description="HS 84 — Nuclear reactors, boilers, machinery. High GVC depth.",
    ),
    "apparel": Sector(
        name="apparel",
        chapters=("61", "62"),
        description="HS 61 (knitted) + HS 62 (woven) apparel. Low GVC depth.",
    ),
    "furniture": Sector(
        name="furniture",
        chapters=("94",),
        description="HS 94 — Furniture, bedding, lamps, prefabs. Medium GVC depth.",
    ),
}


def label_sector(hs6: pd.Series) -> pd.Series:
    """
    Return a Categorical Series labelling each HS6 with its sector name,
    or NaN if the HS6 is not in any defined sector.

    Parameters
    ----------
    hs6 : pd.Series
        HS6 codes as 6-digit strings (with leading zeros preserved).

    Returns
    -------
    pd.Series
        Sector name as Categorical, with the same index as `hs6`.
    """
    if not pd.api.types.is_string_dtype(hs6):
        raise TypeError(
            "label_sector expects HS6 as string dtype to preserve leading zeros."
        )

    out = pd.Series(pd.NA, index=hs6.index, dtype="object")
    for name, sector in SECTORS.items():
        for prefix in sector.chapters:
            mask = hs6.str.startswith(prefix) & out.isna()
            out.loc[mask] = name

    categories = list(SECTORS.keys())
    return pd.Categorical(out, categories=categories)


def all_sector_chapters() -> tuple[str, ...]:
    """Flat tuple of all HS chapter prefixes across all defined sectors."""
    return tuple(c for s in SECTORS.values() for c in s.chapters)


def hs6_in_sectors(hs6: pd.Series) -> pd.Series:
    """Boolean Series: True if HS6 belongs to any defined sector."""
    chapters = all_sector_chapters()
    return hs6.str[:2].isin(chapters)
