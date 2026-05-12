"""
TiVA 2025 — Origin of Value Added in Final Demand (FDVA)
Fetches OECD SDMX data, builds a bilateral edge list, and plots a
weighted directed network graph on a Robinson-projected world map.

Dependencies:  requests pandas numpy geopandas pyproj matplotlib networkx
               geodatasets  (first run downloads a small Natural Earth zip)

Runtime note:  the full CSV download is ~9.3 GB and takes ~15 minutes.
               All intermediate files are cached; subsequent runs are fast.

Usage:
    pip install requests pandas numpy geopandas pyproj matplotlib networkx geodatasets
    python fdva_network.py
"""

import json
import zipfile
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")

import requests
import pandas as pd
import numpy as np
import geopandas as gpd
import pyproj
import matplotlib
matplotlib.use("Agg")          # change to "TkAgg" / "MacOSX" for interactive window
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.patheffects as pe
from matplotlib.colors import LogNorm
from matplotlib.cm import ScalarMappable
from matplotlib.patches import FancyArrowPatch, ArrowStyle

# ══════════════════════════════════════════════════════════════════════════
# CONFIGURATION  — edit these to change behaviour
# ══════════════════════════════════════════════════════════════════════════

CACHE_DIR  = Path(__file__).parent / "tiva_fdva_cache"
META_XML   = CACHE_DIR / "dataflow_metadata.xml"
DATA_CSV   = CACHE_DIR / "fdva_full.csv"
EDGE_CSV   = CACHE_DIR / "edge_list_2021.csv"
CL_JSON    = CACHE_DIR / "codelists_full.json"
SHP_DIR    = CACHE_DIR / "ne_countries"
OUT_PNG    = CACHE_DIR / "fdva_network_2021.png"

YEAR       = "2021"          # year to analyse (only 2021-2022 available at activity level)
THRESHOLD  = 10_000          # min bilateral flow in million USD to draw an edge

# ── API endpoints ──────────────────────────────────────────────────────────
META_URL = (
    "https://sdmx.oecd.org/sti-public/rest/dataflow/"
    "OECD.STI.PIE/DSD_TIVA_FDVA@DF_FDVA/1.1?references=all"
)

DATA_URL = (
    "https://sdmx.oecd.org/sti-public/rest/data/"
    "OECD.STI.PIE,DSD_TIVA_FDVA@DF_FDVA,1.1/"
    ".W+OECD+WXOECD+WXD+APEC+ASEAN+S2+EU28+EU15+EU28XEU15+EA19+G20+F+S2_S8+E"
    "+NAFTA+A5_A7+W_O+AUS+AUT+BEL+CAN+CHL+COL+CRI+CZE+DNK+EST+FIN+FRA+DEU+GRC"
    "+HUN+ISL+IRL+ISR+ITA+JPN+KOR+LVA+LTU+LUX+MEX+NLD+NZL+NOR+POL+PRT+SVK+SVN"
    "+ESP+SWE+CHE+TUR+GBR+USA+AGO+ARG+BGD+BLR+BRA+BRN+BGR+KHM+CMR+CHN+COD+CIV"
    "+HRV+CYP+EGY+HKG+IND+IDN+JOR+KAZ+LAO+MYS+MLT+MAR+MMR+NGA+PAK+PER+PHL+ROU"
    "+RUS+STP+SAU+SEN+SGP+ZAF+TWN+THA+TUN+UKR+ARE+VNM+EU27_2020+D"
    ".BTE+FTT+GTT+INFO+A01+A02+A01_02+A03+B05+B06+B07+B08+B05_06+B07_08+B09+C16"
    "+C17_18+C20+C21+C19+C20_21+C22+C23+C241_2431+C242_2432+C24+C25+C26+C27+C301"
    "+C302T309+C29+C30+C10T12+C13T15+C16T18+C19T23+C24_25+C26_27+C28+C29_30+C31T33"
    "+D+E+H49+H50+H51+H52+H53+G+H+I+J58T60+J61+J62_63+M+N+J+K+L+M_N+GTI+JTN+O+P"
    "+Q+R+S+R_S+T+OTQ+RTT+A+B+C+D_E+F+GTN+OTT+_T"
    ".OECD+AUS+AUT+BEL+CAN+CHL+COL+CRI+CZE+DNK+EST+FIN+FRA+DEU+GRC+HUN+ISL+IRL"
    "+ISR+ITA+JPN+KOR+LVA+LTU+LUX+MEX+NLD+NZL+NOR+POL+PRT+SVK+SVN+ESP+SWE+CHE"
    "+TUR+GBR+USA+WXOECD+AGO+ARG+BGD+BLR+BRA+BRN+BGR+KHM+CMR+CHN+COD+CIV+HRV+CYP"
    "+EGY+HKG+IND+IDN+JOR+KAZ+LAO+MYS+MLT+MAR+MMR+NGA+PAK+PER+PHL+ROU+RUS+STP+SAU"
    "+SEN+SGP+ZAF+TWN+THA+TUN+UKR+ARE+VNM+WXD+APEC+ASEAN+S2+EU27_2020+EU28+EU15"
    "+EU28XEU15+EA19+G20+F+S2_S8+E+NAFTA+A5_A7+W_O+D+W"
    "._T+BTE+FTT+GTT+INFO+A01+A02+A01_02+A03+B05+B06+B07+B08+B05_06+B07_08+B09+C16"
    "+C17_18+C20+C21+C19+C20_21+C22+C23+C241_2431+C242_2432+C24+C25+C26+C27+C301"
    "+C302T309+C29+C30+C10T12+C13T15+C16T18+C19T23+C24_25+C26_27+C28+C29_30+C31T33"
    "+D+E+H49+H50+H51+H52+H53+G+H+I+J58T60+J61+J62_63+M+N+J+K+L+M_N+GTI+JTN+O+P"
    "+Q+R+S+R_S+T+OTQ+RTT+A+B+C+D_E+F+GTN+OTT"
    "..A"
    "?startPeriod=1995&endPeriod=2022&dimensionAtObservation=AllDimensions"
)

# ── Individual ISO3 country codes (excludes regional aggregates) ───────────
COUNTRIES = {
    "AUS","AUT","BEL","CAN","CHL","COL","CRI","CZE","DNK","EST","FIN","FRA","DEU",
    "GRC","HUN","ISL","IRL","ISR","ITA","JPN","KOR","LVA","LTU","LUX","MEX","NLD",
    "NZL","NOR","POL","PRT","SVK","SVN","ESP","SWE","CHE","TUR","GBR","USA",
    "AGO","ARG","BGD","BLR","BRA","BRN","BGR","KHM","CMR","CHN","COD","CIV","HRV",
    "CYP","EGY","HKG","IND","IDN","JOR","KAZ","LAO","MYS","MLT","MAR","MMR","NGA",
    "PAK","PER","PHL","ROU","RUS","STP","SAU","SEN","SGP","ZAF","TWN","THA","TUN",
    "UKR","ARE","VNM",
}

# ── Approximate geographic centroids (lon, lat) ────────────────────────────
GEO = {
    "USA":(-98,38),"CAN":(-96,60),"MEX":(-102,24),"BRA":(-51,-14),"ARG":(-64,-34),
    "CHL":(-71,-35),"COL":(-74,4),"CRI":(-84,10),"PER":(-75,-9),
    "GBR":(-2,54),"DEU":(10,51),"FRA":(2,47),"ITA":(12,43),"ESP":(-3,40),
    "NLD":(5,52),"BEL":(4,51),"CHE":(8,47),"SWE":(18,62),"NOR":(9,62),
    "DNK":(10,56),"FIN":(26,64),"AUT":(14,47),"POL":(20,52),"CZE":(16,50),
    "HUN":(19,47),"SVK":(19,48),"SVN":(15,46),"GRC":(22,39),"PRT":(-8,39),
    "IRL":(-8,53),"LUX":(6,50),"ISL":(-19,65),"EST":(25,59),"LVA":(25,57),
    "LTU":(24,56),"BGR":(25,43),"ROU":(25,46),"HRV":(16,45),"CYP":(33,35),
    "MLT":(14,36),"ISR":(35,31),"TUR":(35,39),
    "RUS":(100,60),"UKR":(32,49),"BLR":(28,54),
    "CHN":(104,35),"JPN":(138,36),"KOR":(128,37),"IND":(78,21),"IDN":(118,-5),
    "THA":(101,15),"VNM":(108,16),"MYS":(110,4),"SGP":(104,1),"PHL":(122,13),
    "TWN":(121,24),"HKG":(114,22),"BGD":(90,24),"PAK":(70,30),"KAZ":(68,48),
    "KHM":(105,12),"LAO":(103,18),"MMR":(96,20),"BRN":(115,5),
    "AUS":(133,-27),"NZL":(174,-41),
    "SAU":(45,24),"ARE":(54,24),"EGY":(30,27),"JOR":(36,31),
    "MAR":(-6,32),"TUN":(9,34),"NGA":(8,10),"ZAF":(25,-29),"AGO":(18,-12),
    "CMR":(12,5),"COD":(24,-3),"CIV":(-6,7),"SEN":(-14,14),"STP":(7,1),
}

# ── Region colours ─────────────────────────────────────────────────────────
REGION_COLOR = {
    **{c:"#4393c3" for c in {"AUT","BEL","CZE","DNK","EST","FIN","FRA","DEU","GRC",
                              "HUN","ISL","IRL","ISR","ITA","LVA","LTU","LUX","NLD",
                              "NOR","POL","PRT","SVK","SVN","ESP","SWE","CHE","TUR","GBR"}},
    **{c:"#e05252" for c in {"CAN","CHL","COL","CRI","MEX","USA"}},
    **{c:"#52b052" for c in {"AUS","JPN","KOR","NZL"}},
    **{c:"#f4a442" for c in {"BGD","BRN","KHM","CHN","HKG","IND","IDN","JOR","KAZ",
                              "LAO","MYS","MMR","PAK","PHL","SGP","TWN","THA","VNM"}},
    **{c:"#9970ab" for c in {"BLR","BGR","HRV","CYP","MLT","ROU","RUS","UKR"}},
    **{c:"#e066a0" for c in {"ARG","BRA","PER"}},
    **{c:"#c9b23a" for c in {"AGO","CMR","COD","CIV","EGY","MAR","NGA","SAU","SEN",
                              "STP","ZAF","TUN","ARE"}},
}

LEGEND_DATA = [
    ("OECD Europe",          "#4393c3"),
    ("OECD Americas",        "#e05252"),
    ("OECD Asia-Pacific",    "#52b052"),
    ("Emerging Asia",        "#f4a442"),
    ("Europe (non-OECD)",    "#9970ab"),
    ("Latin America",        "#e066a0"),
    ("Africa & Middle East", "#c9b23a"),
]


# ══════════════════════════════════════════════════════════════════════════
# 1. FETCH & PARSE METADATA
# ══════════════════════════════════════════════════════════════════════════

def fetch_metadata():
    if META_XML.exists():
        print(f"[meta] Using cached {META_XML.name}")
        return
    print("[meta] Downloading dataflow metadata …")
    r = requests.get(META_URL, timeout=120)
    r.raise_for_status()
    META_XML.write_bytes(r.content)
    print(f"[meta] Saved {META_XML.stat().st_size / 1e6:.1f} MB")


def parse_codelists() -> dict:
    if CL_JSON.exists():
        with open(CL_JSON) as f:
            return json.load(f)

    S = "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure"
    C = "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common"
    M = "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message"

    tree = ET.parse(META_XML)
    structures = tree.getroot().find(f"{{{M}}}Structures")
    codelists: dict = {}
    for cl in structures.iter(f"{{{S}}}Codelist"):
        codes: dict = {}
        for code in cl.iter(f"{{{S}}}Code"):
            name_el = code.find(f"{{{C}}}Name")
            codes[code.get("id")] = name_el.text if name_el is not None else ""
        codelists[cl.get("id")] = codes

    CL_JSON.write_text(json.dumps(codelists, indent=2, ensure_ascii=False))
    return codelists


def print_codelist_summary(codelists: dict):
    DIM_CL = {
        "MEASURE":                    "CL_TIVA_MEASURE",
        "VALUE_ADDED_SOURCE_AREA":    "CL_AREA",
        "VALUE_ADDED_SOURCE_ACTIVITY":"CL_ACTIVITY_ISIC4",
        "FINAL_DEMAND_AREA":          "CL_AREA",
        "FINAL_DEMAND_ACTIVITY":      "CL_ACTIVITY_ISIC4",
        "UNIT_MEASURE":               "CL_UNIT_MEASURE",
        "FREQ":                       "CL_FREQ",
        "TIME_PERIOD":                "TEXT",
    }
    print("\n" + "=" * 65)
    print("DIMENSION MAP")
    print("=" * 65)
    print(f"  {'Dimension':<35} {'Codelist':<25} #Codes")
    print("  " + "-" * 63)
    for dim, cl in DIM_CL.items():
        n = len(codelists.get(cl, {})) or "—"
        print(f"  {dim:<35} {cl:<25} {n}")

    for cl_id in ("CL_TIVA_MEASURE", "CL_AREA", "CL_ACTIVITY_ISIC4"):
        codes = codelists.get(cl_id, {})
        print(f"\n{cl_id}  ({len(codes)} codes)")
        print("-" * 65)
        for code, label in codes.items():
            print(f"  {code:<22} {label}")


# ══════════════════════════════════════════════════════════════════════════
# 2. FETCH DATA
# ══════════════════════════════════════════════════════════════════════════

def fetch_data():
    if DATA_CSV.exists():
        print(f"[data] Using cached {DATA_CSV.name} "
              f"({DATA_CSV.stat().st_size / 1e9:.1f} GB)")
        return
    print("[data] Downloading full dataset — ~9.3 GB, expect ~15 min …")
    with requests.get(
        DATA_URL,
        headers={"Accept": "application/vnd.sdmx.data+csv;version=1.0.0"},
        stream=True,
        timeout=1800,
    ) as r:
        r.raise_for_status()
        total = 0
        with open(DATA_CSV, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
                total += len(chunk)
                if total % (100 * 1 << 20) == 0:
                    print(f"  … {total / 1e9:.1f} GB received")
    print(f"[data] Saved {DATA_CSV.stat().st_size / 1e9:.2f} GB")


# ══════════════════════════════════════════════════════════════════════════
# 3. BUILD EDGE LIST
# ══════════════════════════════════════════════════════════════════════════

def build_edge_list() -> pd.DataFrame:
    if EDGE_CSV.exists():
        print(f"[edges] Using cached {EDGE_CSV.name}")
        return pd.read_csv(EDGE_CSV)

    print(f"[edges] Filtering {YEAR} · _T×_T · country-to-country flows …")
    dtype_map = {
        "VALUE_ADDED_SOURCE_AREA":     "category",
        "VALUE_ADDED_SOURCE_ACTIVITY": "category",
        "FINAL_DEMAND_AREA":           "category",
        "FINAL_DEMAND_ACTIVITY":       "category",
        "TIME_PERIOD":                 "category",
        "OBS_VALUE":                   "float32",
        "UNIT_MULT":                   "float32",
    }
    accumulator: dict = defaultdict(float)
    rows_kept = 0

    for chunk in pd.read_csv(
        DATA_CSV,
        dtype=dtype_map,
        usecols=list(dtype_map.keys()),
        chunksize=500_000,
    ):
        sub = chunk[
            (chunk["TIME_PERIOD"] == YEAR) &
            (chunk["VALUE_ADDED_SOURCE_ACTIVITY"] == "_T") &
            (chunk["FINAL_DEMAND_ACTIVITY"] == "_T") &
            (chunk["VALUE_ADDED_SOURCE_AREA"].isin(COUNTRIES)) &
            (chunk["FINAL_DEMAND_AREA"].isin(COUNTRIES))
        ]
        for _, row in sub.iterrows():
            src, tgt = row["VALUE_ADDED_SOURCE_AREA"], row["FINAL_DEMAND_AREA"]
            if src != tgt:
                accumulator[(src, tgt)] += float(row["OBS_VALUE"])
        rows_kept += len(sub)

    edges = pd.DataFrame(
        [(s, t, w) for (s, t), w in accumulator.items()],
        columns=["source", "target", "weight_musd"],
    ).sort_values("weight_musd", ascending=False)

    edges.to_csv(EDGE_CSV, index=False)
    print(f"[edges] {rows_kept:,} rows matched → {len(edges):,} bilateral pairs")
    return edges


# ══════════════════════════════════════════════════════════════════════════
# 4. WORLD MAP NETWORK GRAPH
# ══════════════════════════════════════════════════════════════════════════

def _ensure_shapefile():
    shp = SHP_DIR / "ne_110m_admin_0_countries.shp"
    if shp.exists():
        return shp
    SHP_DIR.mkdir(exist_ok=True)
    url = ("https://naciscdn.org/naturalearth/110m/cultural/"
           "ne_110m_admin_0_countries.zip")
    zip_path = SHP_DIR / "countries.zip"
    print("[map] Downloading Natural Earth country boundaries …")
    urllib.request.urlretrieve(url, zip_path)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(SHP_DIR)
    return shp


def plot_network(edges: pd.DataFrame):
    shp = _ensure_shapefile()
    world     = gpd.read_file(shp)
    world_rob = world.to_crs("ESRI:54030")   # Robinson projection

    # Project node lon/lat → Robinson metres
    tf  = pyproj.Transformer.from_crs("EPSG:4326", "ESRI:54030", always_xy=True)
    pos = {iso: tf.transform(lon, lat) for iso, (lon, lat) in GEO.items()}

    edf   = edges[edges["weight_musd"] >= THRESHOLD].copy()
    nodes = [n for n in set(edf["source"]) | set(edf["target"]) if n in pos]
    print(f"[graph] Edges ≥ ${THRESHOLD:,}M: {len(edf):,}  |  Nodes: {len(nodes)}")

    out_str = edf.groupby("source")["weight_musd"].sum().to_dict()
    max_s   = max(out_str.values())
    top10   = sorted(out_str, key=out_str.get, reverse=True)[:10]

    # ── Figure ───────────────────────────────────────────────────────────
    BG, LAND, BORD = "#0a1628", "#162032", "#1e3a58"
    fig, ax = plt.subplots(figsize=(28, 16), facecolor=BG)
    ax.set_facecolor(BG)
    xmin, ymin, xmax, ymax = world_rob.total_bounds
    ax.set_xlim(xmin * 1.01, xmax * 1.01)
    ax.set_ylim(ymin * 1.02, ymax * 1.02)

    # World land masses
    world_rob.plot(ax=ax, color=LAND, edgecolor=BORD, linewidth=0.25, zorder=1)

    # Highlight network countries with their region colour (translucent fill)
    iso_idx = world_rob.set_index("ISO_A3")
    for iso in nodes:
        if iso in iso_idx.index:
            gpd.GeoDataFrame(
                geometry=[iso_idx.loc[iso, "geometry"]], crs=world_rob.crs
            ).plot(ax=ax, color=REGION_COLOR.get(iso, "#888"),
                   alpha=0.22, edgecolor=BORD, linewidth=0.3, zorder=2)

    # ── Edges (weakest first → strongest paints on top) ──────────────────
    weights_arr = edf["weight_musd"].values
    log_w       = np.log10(weights_arr)
    lw_min, lw_max = log_w.min(), log_w.max()
    norm  = LogNorm(vmin=weights_arr.min(), vmax=weights_arr.max())
    cmap  = plt.cm.plasma

    for i in np.argsort(weights_arr):
        row = edf.iloc[i]
        src, tgt = row["source"], row["target"]
        if src not in pos or tgt not in pos:
            continue
        lw_norm  = (log_w[i] - lw_min) / (lw_max - lw_min)
        lat_avg  = (GEO[src][1] + GEO[tgt][1]) / 2
        rad      = 0.25 if lat_avg >= 0 else -0.25
        color    = cmap(norm(weights_arr[i]))
        alpha    = float(0.15 + 0.70 * lw_norm)
        lw       = float(0.15 + 1.0  * lw_norm)   # thin tail: 0.15–1.15 pt
        head_len = 16 + 10 * lw_norm
        head_wid = 10 + 6  * lw_norm
        # shrinkA/B stop arrow at node boundary so head stays visible
        sA = float(node_r.get(src, 5))
        sB = float(node_r.get(tgt, 5))

        # White outline for contrast against dark background
        ax.add_patch(FancyArrowPatch(
            pos[src], pos[tgt],
            connectionstyle=f"arc3,rad={rad}",
            arrowstyle=ArrowStyle.Simple(
                head_length=head_len, head_width=head_wid, tail_width=lw + 0.9),
            color="white", alpha=float(0.18 + 0.20 * lw_norm),
            shrinkA=sA, shrinkB=sB, zorder=3,
        ))
        # Coloured arrow on top
        ax.add_patch(FancyArrowPatch(
            pos[src], pos[tgt],
            connectionstyle=f"arc3,rad={rad}",
            arrowstyle=ArrowStyle.Simple(
                head_length=head_len, head_width=head_wid, tail_width=lw),
            color=color, alpha=alpha,
            shrinkA=sA, shrinkB=sB, zorder=4,
        ))

    # ── Node sizes and radii (radius in points: scatter s is area in pt²) ──
    node_s = {n: 80 + 3800 * (out_str.get(n, 1) / max_s) ** 0.5 for n in nodes}
    node_r = {n: np.sqrt(node_s[n] / np.pi) for n in nodes}

    for n in nodes:
        x, y = pos[n]
        ax.scatter(x, y, s=node_s[n], color=REGION_COLOR.get(n, "#aaa"),
                   edgecolors="white", linewidths=0.7, zorder=5, alpha=0.95)

    # ── Labels inside nodes (hidden when node is too small to fit text) ──
    # Visible diameter ≈ sqrt(s) points; a 3-char label needs ~14pt at 6pt font
    LABEL_MIN_S = 350
    for n in nodes:
        s = node_s[n]
        if s < LABEL_MIN_S:
            continue
        x, y = pos[n]
        fs = min(9.0, 5.5 + 2.0 * (s - LABEL_MIN_S) /
                 (max(node_s.values()) - LABEL_MIN_S))
        ax.text(x, y, n, ha="center", va="center",
                fontsize=fs, fontweight="bold", color="white", zorder=6,
                path_effects=[pe.withStroke(linewidth=1.2, foreground="black")])

    # ── Colorbar with explicit USD billion tick labels ────────────────────
    sm = ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, orientation="vertical",
                        fraction=0.025, pad=0.015, shrink=0.75)
    cbar.set_label("Value Added in Final Demand Flow",
                   color="white", fontsize=13, labelpad=12)
    tick_vals = [10_000, 25_000, 50_000, 100_000, 200_000, 350_000, 513_000]
    cbar.set_ticks(tick_vals)
    cbar.set_ticklabels([f"${v // 1_000}B" for v in tick_vals])
    cbar.ax.yaxis.set_tick_params(color="white", labelsize=12)
    cbar.ax.set_title("USD (billions)", color="white", fontsize=11, pad=8)
    plt.setp(cbar.ax.yaxis.get_ticklabels(), color="white")

    # ── Region legend ─────────────────────────────────────────────────────
    handles = [
        mpatches.Patch(facecolor=c, edgecolor="white",
                       linewidth=0.8, label=l)
        for l, c in LEGEND_DATA
    ]
    ax.legend(handles=handles, loc="lower left", framealpha=0.40,
              facecolor="#0d1b2a", edgecolor="#2a5080",
              fontsize=13, title="Region", title_fontsize=14,
              labelcolor="white", borderpad=1.0,
              handlelength=1.8, handleheight=1.4, labelspacing=0.6)

    # ── Title ─────────────────────────────────────────────────────────────
    ax.set_title(
        f"TiVA 2025  ·  Origin of Value Added in Final Demand  ·  {YEAR}\n"
        f"Weighted Directed Network  ·  Bilateral flows ≥ ${THRESHOLD:,} M USD  "
        "·  Node size ∝ total outgoing VA  ·  Edge colour ∝ flow magnitude",
        color="white", fontsize=13, fontweight="bold", pad=14,
    )
    ax.axis("off")
    plt.tight_layout(pad=0.5)
    plt.savefig(OUT_PNG, dpi=180, bbox_inches="tight", facecolor=BG)
    print(f"[graph] Saved → {OUT_PNG}")
    plt.close()


# ══════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    CACHE_DIR.mkdir(exist_ok=True)

    # 1. Metadata & codelists
    fetch_metadata()
    codelists = parse_codelists()
    print_codelist_summary(codelists)

    # 2. Raw data  (cached after first run — ~15 min download)
    fetch_data()

    # 3. Edge list  (cached after first run — ~10 min scan)
    edges = build_edge_list()
    print(f"\nTop 10 flows  ({YEAR}, million USD):")
    print(edges.head(10).to_string(index=False))

    # 4. World-map network graph
    plot_network(edges)
