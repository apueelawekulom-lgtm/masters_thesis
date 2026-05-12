"""
Build a narrow semiconductor edge list from baci_combined.parquet.

Filter: HS6 codes under HS 8541 (semiconductor devices: diodes, transistors,
photovoltaic / LEDs, piezo crystals, parts) and HS 8542 (electronic integrated
circuits and parts).

Caveat: HS 854140 lumps photovoltaic cells/modules together with LEDs. So this
edge list captures "semiconductors + solar panels + LEDs" — note in writeups.

Outputs in BACI_HS92_V202601/:
  baci_edges_country_semiconductors.parquet   year × source × target
"""

from pathlib import Path
from collections import defaultdict
import time

import pandas as pd
import pyarrow.dataset as ds

ROOT = Path(__file__).parent
BACI_DIR = ROOT / "BACI_HS92_V202601"
COMBINED = BACI_DIR / "baci_combined.parquet"
OUT = BACI_DIR / "baci_edges_country_semiconductors.parquet"

PREFIXES = ("8541", "8542")


def main() -> None:
    dset = ds.dataset(COMBINED, format="parquet")
    years = sorted(int(y) for y in pd.unique(
        dset.to_table(columns=["t"]).to_pandas()["t"]
    ))
    print(f"[stream] {len(years)} years; filtering HS6 starting with {PREFIXES}")

    acc: dict[tuple[int, str, str], float] = defaultdict(float)
    t0 = time.time()
    for yr in years:
        t = time.time()
        tbl = dset.to_table(
            columns=["t","k","v","iso3_exporter","iso3_importer"],
            filter=ds.field("t") == yr,
        )
        df = tbl.to_pandas()
        mask = df["k"].str.startswith(PREFIXES, na=False)
        sub = df.loc[mask]
        g = sub.groupby(["iso3_exporter","iso3_importer"], observed=True)["v"].sum()
        for (src, tgt), val in g.items():
            acc[(yr, src, tgt)] += float(val)
        print(f"  {yr}  matched_rows={mask.sum():>8,}  pairs={len(g):>6,}  "
              f"trade=${sub['v'].sum()/1e6:>8.1f}B  dt={time.time()-t:4.1f}s")

    rows = [{"year": y, "source": s, "target": t, "value_kusd": v}
            for (y, s, t), v in acc.items()]
    out = pd.DataFrame.from_records(rows)
    out["value_busd"] = out["value_kusd"] / 1_000_000
    out = out[["year","source","target","value_kusd","value_busd"]]
    out["source"] = out["source"].astype("category")
    out["target"] = out["target"].astype("category")
    out.to_parquet(OUT, compression="snappy", index=False)

    print(f"\n[saved] {OUT.name}  {len(out):,} rows  {out['value_busd'].sum():.0f} bn total")
    print(f"[total] {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
