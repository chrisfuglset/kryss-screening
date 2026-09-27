#!/usr/bin/env python3
"""
kryss_screening.py
==================

Kobler trafikkulykker til kryss for et valgfritt område i Norge, basert på åpne data
fra OpenStreetMap og Nasjonal vegdatabank (NVDB).

Skriptet
  1. henter kjørbart gatenett for analyseområdet fra OpenStreetMap (OSMnx),
  2. slår sammen nærliggende noder til ett kryss (f.eks. kryss med midtdeler),
     og slår sammen hver rundkjøring til ett kryss,
  3. klassifiserer kryssene som T-kryss / X-kryss / flerarmet / rundkjøring,
  4. henter trafikkulykker (vegobjekttype 570) og trafikkmengde (540) fra NVDB,
  5. kobler hver ulykke til nærmeste kryss innenfor en gitt radius,
  6. overfører ÅDT fra NVDB til gatenettet der vegene overlapper, og
  7. skriver kryss, tilknyttede ulykker og vegnett til en GeoPackage med
     innebygde QGIS-stiler, pluss en CSV med kryssene.

Analyseområdet og øvrige valg settes i innstillinger.toml. Se README.md.

Bruk:
    python kryss_screening.py                          # bruker innstillinger.toml
    python kryss_screening.py --sted "Frogner, Oslo"    # overstyrer området
    python kryss_screening.py --boks 10.74 59.91 10.80 59.94
    python kryss_screening.py --polygon-fil mitt_omrade.gpkg
    python kryss_screening.py --help
"""

from __future__ import annotations

import argparse
import math
import re
import socket
import sys
import time
import tomllib
from pathlib import Path
from urllib.parse import urlsplit

import geopandas as gpd
import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd
import pyogrio
import requests
from shapely import box, force_2d, wkt
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union

# --------------------------------------------------------------------------
# Konstanter
# --------------------------------------------------------------------------

MAPPE = Path(__file__).resolve().parent
STANDARD_INNSTILLINGER = MAPPE / "innstillinger.toml"
STILMAPPE = MAPPE / "stiler"

CRS_GEO = "EPSG:4326"
NVDB_CRS = "EPSG:25833"  # NVDB tolker kartutsnitt i UTM 33 uansett srid, så vi henter i 33
NVDB_URL = "https://nvdbapiles.atlas.vegvesen.no/vegobjekter/api/v4/vegobjekter"
NVDB_KLIENT = "kryss-screening"
# Overpass-tjenesten for OSM-data. Den er flere maskiner bak samme navn, og hver testes for seg.
# Andre servere brukes bare hvis brukeren selv velger dem med overpass_url.
OVERPASS_URL = "https://overpass-api.de/api"
NORGE_BOKS = box(4.0, 57.8, 31.5, 71.5)  # grov boks (lon/lat), bare for en advarsel
# Gatenettet hentes så langt utenfor området at kryss på grensen får alle armene sine
KANTSONE_M = 200
# Merke i GeoPackage-fila som viser at skriptet har laget den og trygt kan overskrive den
STIL_BESKRIVELSE = "Laget av kryss_screening.py"
KRYSS_KOLONNER = ["kryss_id", "krysstype", "antall_armer", "hoyeste_vegklasse", "maks_fart",
                  "antall_ulykker"]

STANDARDVERDIER = {
    "omrade": {"sted": "", "polygon_fil": "", "polygon_lag": "", "boks": []},
    "analyse": {"fra_aar": 0, "toleranse_m": 15.0, "radius_m": 30.0,
                "adt_buffer_m": 10.0, "maks_areal_km2": 500.0},
    "utdata": {"fil": "", "crs": "auto"},
    "kilder": {"ulykker_fil": "", "overpass_url": ""},
}

# Rangering av OSM-vegklasser (lavere tall = viktigere veg)
VEGKLASSE_RANG = {
    "motorway": 1, "trunk": 2, "primary": 3, "secondary": 4, "tertiary": 5,
    "unclassified": 6, "residential": 7, "living_street": 8,
}
RANG_TIL_KLASSE = {v: k for k, v in VEGKLASSE_RANG.items()}


# --------------------------------------------------------------------------
# Små hjelpefunksjoner
# --------------------------------------------------------------------------

def logg(melding: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {melding}", flush=True)


def tall(x: float, desimaler: int = 0) -> str:
    """Norsk tallformat: 12 345,6"""
    return f"{x:,.{desimaler}f}".replace(",", " ").replace(".", ",")


def som_liste(verdi) -> list:
    """OSMnx lagrer noen ganger flere verdier som liste etter forenkling."""
    if verdi is None:
        return []
    if isinstance(verdi, float) and math.isnan(verdi):
        return []
    if isinstance(verdi, (list, tuple, set)):
        return list(verdi)
    return [verdi]


def tolk_fart(verdi) -> int | None:
    tekst = str(verdi).strip().lower()
    treff = re.match(r"^(\d+)", tekst)
    if treff:
        return int(treff.group(1))
    return {"no:urban": 50, "no:rural": 80, "no:motorway": 110}.get(tekst)


def vegrang(highway) -> int:
    return VEGKLASSE_RANG.get(str(highway).replace("_link", ""), 9)


def veginfo(G: nx.MultiDiGraph, noder, interne: frozenset = frozenset()) -> tuple[int, float]:
    """Høyeste vegklasse (som rang) og høyeste fartsgrense på kantene inn/ut av nodene."""
    rangs, farter = [], []
    for n in noder:
        for u, v, data in list(G.out_edges(n, data=True)) + list(G.in_edges(n, data=True)):
            if u in interne and v in interne:
                continue  # kanter inne i en rundkjøring teller ikke som armer
            rangs += [vegrang(h) for h in som_liste(data.get("highway"))]
            farter += [f for f in (tolk_fart(x) for x in som_liste(data.get("maxspeed"))) if f]
    return (min(rangs) if rangs else 9), (max(farter) if farter else np.nan)


def krysstype(armer: int) -> str:
    if armer == 3:
        return "T-kryss"
    if armer == 4:
        return "X-kryss"
    return "flerarmet"


def filnavn_fra(tekst: str) -> str:
    """«Grünerløkka, Oslo» -> «grunerlokka»."""
    tekst = tekst.split(",")[0].strip().lower()
    tekst = tekst.translate(str.maketrans({"æ": "ae", "ø": "o", "å": "a", "ä": "a",
                                           "ö": "o", "ü": "u", "é": "e"}))
    return re.sub(r"[^a-z0-9]+", "_", tekst).strip("_") or "omrade"


def rens_for_gpkg(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """GeoPackage tåler ikke lister/objekter i kolonner; gjør dem om til tekst."""
    gdf = gdf.copy()
    for kolonne in gdf.columns:
        if kolonne == gdf.geometry.name:
            continue
        if gdf[kolonne].dtype == object:
            gdf[kolonne] = gdf[kolonne].apply(
                lambda v: ";".join(map(str, v)) if isinstance(v, (list, tuple, set))
                else (None if v is None or (isinstance(v, float) and math.isnan(v)) else str(v))
            )
    return gdf


# --------------------------------------------------------------------------
# Innstillinger og analyseområde
# --------------------------------------------------------------------------

def les_innstillinger(sti: Path) -> dict:
    innst = {seksjon: dict(verdier) for seksjon, verdier in STANDARDVERDIER.items()}
    if sti.exists():
        with open(sti, "rb") as f:
            fra_fil = tomllib.load(f)
        for seksjon, verdier in fra_fil.items():
            innst.setdefault(seksjon, {}).update(verdier)
    elif sti != STANDARD_INNSTILLINGER:
        raise FileNotFoundError(f"Fant ikke innstillingsfila {sti}")
    return innst


def som_flate(geom, kilde: str):
    if geom is None or geom.is_empty:
        raise ValueError(f"Området fra {kilde} er tomt.")
    if not isinstance(geom, (Polygon, MultiPolygon)):
        raise ValueError(f"Området fra {kilde} er ikke en flate ({geom.geom_type}). "
                         "Prøv et mer presist stedsnavn, en polygonfil eller en boks.")
    return geom.buffer(0)  # reparerer eventuelle ugyldige polygoner


def finn_omrade(omr: dict) -> tuple[Polygon | MultiPolygon, str]:
    """Analyseområdet i lengde-/breddegrader, pluss et kort navn til utfila."""
    valgt = [k for k in ("sted", "polygon_fil", "boks") if omr.get(k)]
    if len(valgt) != 1:
        raise ValueError("Angi nøyaktig én av «sted», «polygon_fil» eller «boks» "
                         f"i [omrade] (fant {len(valgt)}: {', '.join(valgt) or 'ingen'}).")

    if omr.get("sted"):
        sted = omr["sted"]
        sporring = sted if any(o in sted.lower() for o in ("norway", "norge", "noreg")) \
            else f"{sted}, Norway"
        logg(f"Slår opp «{sporring}» i OpenStreetMap")
        geom = ox.geocode_to_gdf(sporring).to_crs(CRS_GEO).union_all()
        return som_flate(geom, f"stedsnavnet «{sted}»"), filnavn_fra(sted)

    if omr.get("polygon_fil"):
        sti = Path(omr["polygon_fil"])
        logg(f"Leser analyseområde fra {sti}")
        gdf = gpd.read_file(sti, layer=omr["polygon_lag"]) if omr.get("polygon_lag") \
            else gpd.read_file(sti)
        if gdf.empty or gdf.crs is None:
            raise ValueError(f"{sti} er tom eller mangler koordinatsystem.")
        return som_flate(gdf.to_crs(CRS_GEO).union_all(), str(sti)), filnavn_fra(sti.stem)

    vest, sor, ost, nord = (float(x) for x in omr["boks"])
    if not (vest < ost and sor < nord):
        raise ValueError("«boks» må oppgis som [vest, sør, øst, nord] i lengde-/breddegrader.")
    return box(vest, sor, ost, nord), "omrade"


def velg_crs(omrade, crs: str) -> str:
    """
    «auto» gir ETRS89 / UTM-sonen for områdets midtpunkt, justert til sonene som brukes
    i Norge: 32 (Sør-Norge), 33 (Midt- og Nord-Norge) og 35 (Finnmark).
    """
    if crs.lower() != "auto":
        return crs
    sone = int((omrade.centroid.x + 180) // 6) + 1
    sone = {31: 32, 34: 33, 36: 35}.get(sone, sone)
    return f"EPSG:{25800 + sone}"


def kontroller_omrade(omrade, crs: str, maks_areal_km2: float) -> None:
    areal = gpd.GeoSeries([omrade], crs=CRS_GEO).to_crs(crs).area.iloc[0] / 1e6
    logg(f"Analyseområde: {tall(areal, 1)} km², koordinatsystem {crs}")
    if maks_areal_km2 and areal > maks_areal_km2:
        raise ValueError(
            f"Området er {tall(areal)} km², over grensen på {tall(maks_areal_km2)} km² "
            "(maks_areal_km2). Velg et mindre område, eller øk grensen hvis du vet hva du gjør: "
            "store områder tar lang tid og belaster de åpne tjenestene.")
    if not omrade.intersects(NORGE_BOKS):
        logg("ADVARSEL: Området ser ut til å ligge utenfor Norge. NVDB har bare norske data.")


# --------------------------------------------------------------------------
# 1. Gatenett fra OSM
# --------------------------------------------------------------------------

_EKTE_GETADDRINFO = socket.getaddrinfo
_EKTE_GETHOSTBYNAME = socket.gethostbyname


def las_vertsnavn(vert: str, ip: str) -> None:
    """Får alle oppslag av vertsnavnet, også de OSMnx gjør, til å gå til én bestemt IP-adresse."""
    def getaddrinfo(host, *args, **kwargs):
        return _EKTE_GETADDRINFO(ip if host == vert else host, *args, **kwargs)

    def gethostbyname(host):
        return ip if host == vert else _EKTE_GETHOSTBYNAME(host)

    socket.getaddrinfo = getaddrinfo
    socket.gethostbyname = gethostbyname


def kontroller_overpass_url(url: str) -> None:
    deler = urlsplit(url)
    if url and (deler.scheme != "https" or not deler.hostname):
        raise ValueError(f"overpass_url må være en https-adresse, f.eks. \"{OVERPASS_URL}\" "
                         f"(fikk «{url}»).")


def velg_overpass(foretrukket: str) -> None:
    """
    Finner en Overpass-server som svarer, og låser OSMnx til den. Brukerens egen server
    (overpass_url) prøves først, deretter overpass-api.de.

    overpass-api.de er flere maskiner bak samme navn. OSMnx slår opp én av dem og venter i
    180 s hvis den ikke svarer, uten å prøve de andre. Her testes hver adresse med kort
    tidsgrense, og den første som svarer brukes.
    """
    kandidater = list(dict.fromkeys(([foretrukket] if foretrukket else []) + [OVERPASS_URL]))
    for url in kandidater:
        vert = urlsplit(url).hostname
        try:
            adresser = list(dict.fromkeys(
                a[4][0] for a in _EKTE_GETADDRINFO(vert, 443, 0, socket.SOCK_STREAM)))
        except socket.gaierror:
            logg(f"  Fant ikke {vert} i DNS, prøver neste")
            continue
        for ip in adresser:
            las_vertsnavn(vert, ip)
            try:
                svar = requests.get(f"{url.rstrip('/')}/status", timeout=(10, 30),
                                    headers={"User-Agent": ox.settings.http_user_agent})
                svar.raise_for_status()
            except requests.RequestException:
                logg(f"  {vert} ({ip}) svarer ikke, prøver neste")
                continue
            ox.settings.overpass_url = url
            logg(f"Bruker Overpass-serveren {vert} ({ip})")
            return
    socket.getaddrinfo, socket.gethostbyname = _EKTE_GETADDRINFO, _EKTE_GETHOSTBYNAME
    logg("ADVARSEL: Fikk ikke kontakt med noen Overpass-server. Prøver likevel, noe som går bra "
         "hvis området er hentet før. Ellers: sjekk internettforbindelsen, eller vent noen "
         "minutter og prøv igjen.")


def hent_gatenett(omrade, crs: str) -> nx.MultiDiGraph:
    ox.settings.use_cache = True
    ox.settings.log_console = False
    ox.settings.useful_tags_way = list(dict.fromkeys(list(ox.settings.useful_tags_way) + ["junction"]))

    logg("Henter kjørbart gatenett fra OpenStreetMap (kan ta noen minutter)")
    # retain_all: behold også øyer og vegnett uten forbindelse til resten
    G = ox.graph_from_polygon(omrade, network_type="drive", simplify=True, retain_all=True)
    logg(f"Gatenett: {tall(G.number_of_nodes())} noder, {tall(G.number_of_edges())} kanter")
    return ox.project_graph(G, to_crs=crs)


# --------------------------------------------------------------------------
# 2. Kryss
# --------------------------------------------------------------------------

def finn_rundkjoringer(Gp: nx.MultiDiGraph) -> gpd.GeoDataFrame:
    """Én rad per rundkjøring: antall armer, veginfo og flaten ringen dekker."""
    crs = Gp.graph["crs"]
    kanter = ox.graph_to_gdfs(Gp, nodes=False)
    if "junction" not in kanter.columns:
        return gpd.GeoDataFrame(geometry=[], crs=crs)
    maske = kanter["junction"].apply(
        lambda v: any(x in ("roundabout", "circular") for x in som_liste(v)))
    rk = kanter[maske]
    if rk.empty:
        return gpd.GeoDataFrame(geometry=[], crs=crs)

    u = rk.index.get_level_values("u")
    v = rk.index.get_level_values("v")
    H = nx.Graph()
    H.add_edges_from(zip(u, v))

    rader = []
    for komponent in nx.connected_components(H):
        noder = list(komponent)
        utvalg = rk[u.isin(noder) & v.isin(noder)]
        naboer = {m for n in noder
                  for m in set(Gp.successors(n)) | set(Gp.predecessors(n))
                  if m not in komponent}
        rang, maksfart = veginfo(Gp, noder, interne=frozenset(komponent))
        rader.append({
            "antall_armer": len(naboer),
            "vegklasse_rang": rang,
            "maks_fart": maksfart,
            "geometry": unary_union(list(utvalg.geometry)).convex_hull,
        })
    rundkj = gpd.GeoDataFrame(rader, geometry="geometry", crs=crs)
    logg(f"Rundkjøringer funnet: {len(rundkj)}")
    return rundkj


def lag_kryss(Gp: nx.MultiDiGraph, toleranse: float) -> gpd.GeoDataFrame:
    crs = Gp.graph["crs"]
    rundkj = finn_rundkjoringer(Gp)

    logg(f"Slår sammen noder innenfor {toleranse:g} m til kryss")
    Gc = ox.consolidate_intersections(Gp, tolerance=toleranse, rebuild_graph=True,
                                      dead_ends=False, reconnect_edges=True)
    armer = ox.stats.count_streets_per_node(Gc)
    noder = ox.graph_to_gdfs(Gc, edges=False)
    noder["antall_armer"] = noder.index.map(armer).fillna(0).astype(int)
    kryss = noder[noder["antall_armer"] >= 3].copy()

    info = [veginfo(Gc, [n]) for n in kryss.index]
    kryss["vegklasse_rang"] = [i[0] for i in info]
    kryss["maks_fart"] = [i[1] for i in info]
    kryss = kryss[["antall_armer", "vegklasse_rang", "maks_fart", "geometry"]].reset_index(drop=True)
    kryss["krysstype"] = kryss["antall_armer"].apply(krysstype)

    # Erstatt nodene i/ved en rundkjøring med ett punkt midt i rundkjøringen
    if not rundkj.empty:
        sone = gpd.GeoDataFrame(geometry=rundkj.geometry.buffer(toleranse), crs=crs)
        inne = gpd.sjoin(kryss, sone, predicate="intersects", how="inner").index.unique()
        kryss = kryss.drop(index=inne)
        rk_punkt = rundkj.copy()
        rk_punkt["geometry"] = rk_punkt.geometry.centroid
        rk_punkt["krysstype"] = "rundkjøring"
        kryss = pd.concat([kryss, rk_punkt], ignore_index=True)

    kryss = gpd.GeoDataFrame(kryss, geometry="geometry", crs=crs).reset_index(drop=True)
    kryss["kryss_id"] = kryss.index + 1
    kryss["hoyeste_vegklasse"] = kryss["vegklasse_rang"].map(RANG_TIL_KLASSE).fillna("annet")
    logg(f"Kryss totalt: {tall(len(kryss))}")
    return kryss


# --------------------------------------------------------------------------
# 3. NVDB: ulykker og trafikkmengde
# --------------------------------------------------------------------------

def hent_nvdb(vegobjekttype: int, bbox: tuple[float, float, float, float], crs: str) -> gpd.GeoDataFrame:
    """Henter alle objekter av en vegobjekttype innenfor bbox (gitt i crs) fra NVDB API Les V4."""
    bbox_nvdb = gpd.GeoSeries([box(*bbox)], crs=crs).to_crs(NVDB_CRS).total_bounds
    okt = requests.Session()
    okt.headers.update({"Accept": "application/json", "X-Client": NVDB_KLIENT})
    parametre = {"kartutsnitt": ",".join(f"{x:.0f}" for x in bbox_nvdb),
                 "inkluder": "egenskaper,geometri,metadata", "srid": "5973", "antall": 1000}
    rader, forrige_start = [], None

    for _ in range(1000):  # sikkerhetsgrense mot evig løkke
        svar = okt.get(f"{NVDB_URL}/{vegobjekttype}", params=parametre, timeout=120)
        if svar.status_code != 200:
            raise RuntimeError(f"NVDB svarte {svar.status_code}: {svar.text[:400]}")
        data = svar.json()
        objekter = data.get("objekter", [])
        for obj in objekter:
            geo = (obj.get("geometri") or {}).get("wkt")
            if not geo:
                continue
            rad = {"nvdb_id": obj.get("id")}
            for egenskap in obj.get("egenskaper") or []:
                navn, verdi = egenskap.get("navn"), egenskap.get("verdi")
                if navn and not str(navn).lower().startswith("geometri") \
                        and not isinstance(verdi, (dict, list)):
                    rad[navn] = verdi
            rad["geometry"] = force_2d(wkt.loads(geo))
            rader.append(rad)

        start = ((data.get("metadata") or {}).get("neste") or {}).get("start")
        if not objekter or not start or start == forrige_start:
            break
        forrige_start = start
        parametre["start"] = start
        time.sleep(0.2)

    return gpd.GeoDataFrame(rader, geometry="geometry", crs=NVDB_CRS).to_crs(crs)


def les_ulykker_fil(sti: str, crs: str) -> gpd.GeoDataFrame:
    logg(f"Leser ulykker fra {sti}")
    ulykker = gpd.read_file(sti).to_crs(crs)
    ulykker["geometry"] = force_2d(ulykker.geometry.values)
    return ulykker


def filtrer_aar(ulykker: gpd.GeoDataFrame, fra_aar: int) -> gpd.GeoDataFrame:
    dato_kol = next((c for c in ulykker.columns if "dato" in str(c).lower()), None)
    if not dato_kol:
        logg("  ADVARSEL: Fant ingen datokolonne; fra_aar ignoreres")
        return ulykker
    aar = pd.to_datetime(ulykker[dato_kol], errors="coerce").dt.year
    ulykker = ulykker[aar >= fra_aar]
    logg(f"  {tall(len(ulykker))} ulykker fra {fra_aar} og senere")
    return ulykker


def koble_ulykker(kryss: gpd.GeoDataFrame, ulykker: gpd.GeoDataFrame,
                  radius: float) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Kobler hver ulykke til nærmeste kryss innenfor radius. Ulykker uten kryss droppes."""
    logg(f"Kobler ulykker til nærmeste kryss innenfor {radius:g} m")
    ulykker = ulykker[ulykker.geometry.notna() & ~ulykker.geometry.is_empty].reset_index(drop=True)
    koblet = gpd.sjoin_nearest(ulykker, kryss[["kryss_id", "geometry"]],
                               how="inner", max_distance=radius, distance_col="avstand_til_kryss_m")
    koblet = koblet[~koblet.index.duplicated(keep="first")]  # like avstander gir duplikater
    koblet = koblet.drop(columns="index_right")
    koblet["avstand_til_kryss_m"] = koblet["avstand_til_kryss_m"].round(1)

    antall = koblet.groupby("kryss_id").size().rename("antall_ulykker")
    kryss = kryss.merge(antall, on="kryss_id", how="left")
    kryss["antall_ulykker"] = kryss["antall_ulykker"].fillna(0).astype(int)
    logg(f"  {tall(len(koblet))} av {tall(len(ulykker))} ulykker ligger innenfor {radius:g} m fra et kryss")
    return kryss, koblet.reset_index(drop=True)


# --------------------------------------------------------------------------
# 4. Vegnett med ÅDT
# --------------------------------------------------------------------------

def lag_vegnett(Gp: nx.MultiDiGraph, omrade_utm, trafikk: gpd.GeoDataFrame,
                buffer_m: float) -> gpd.GeoDataFrame:
    """
    OSM-gatenettet i området (én linje per vegstrekning) med ÅDT fra NVDB. Hver OSM-linje
    får verdiene fra den NVDB-lenken som dekker mest av den innenfor buffer_m meter,
    men bare hvis minst halve linjen er dekket.
    """
    crs = Gp.graph["crs"]
    veger = ox.graph_to_gdfs(ox.convert.to_undirected(Gp), nodes=False).reset_index(drop=True)
    veger = veger[veger.intersects(omrade_utm)].reset_index(drop=True)
    behold = [k for k in ["highway", "name", "maxspeed", "lanes", "oneway"] if k in veger]
    veger = veger[behold + ["geometry"]]
    veger["veg_id"] = veger.index
    veger["lengde_m"] = veger.length.round(1)
    adt_kol = ["adt", "adt_andel_lange_pst", "adt_aar", "adt_grunnlag"]

    trafikk = trafikk.rename(columns={
        "ÅDT, total": "adt", "ÅDT, andel lange kjøretøy": "adt_andel_lange_pst",
        "År, gjelder for": "adt_aar", "Grunnlag for ÅDT": "adt_grunnlag"})
    for kol in adt_kol:
        if kol not in trafikk:
            trafikk[kol] = np.nan
    trafikk = trafikk[pd.to_numeric(trafikk["adt"], errors="coerce").fillna(0) > 0]  # 0 = mangler

    if trafikk.empty:
        logg("  Fant ingen ÅDT i NVDB for området")
        for kol in adt_kol:
            veger[kol] = pd.NA
        return veger

    sone = gpd.GeoDataFrame(trafikk[["nvdb_id"] + adt_kol],
                            geometry=trafikk.geometry.buffer(buffer_m, cap_style="flat"), crs=crs)
    biter = gpd.overlay(veger[["veg_id", "geometry"]], sone, how="intersection", keep_geom_type=True)
    biter["overlapp_m"] = biter.length
    beste = biter.sort_values("overlapp_m", ascending=False).drop_duplicates("veg_id")

    veger = veger.merge(beste[["veg_id", "overlapp_m"] + adt_kol], on="veg_id", how="left")
    for_lite = veger["overlapp_m"] < 0.5 * veger["lengde_m"]
    veger.loc[for_lite, adt_kol] = np.nan
    veger = veger.drop(columns="overlapp_m")
    for kol in ["adt", "adt_andel_lange_pst", "adt_aar"]:
        veger[kol] = pd.to_numeric(veger[kol], errors="coerce").astype("Int64")

    med_adt = veger["adt"].notna()
    logg(f"  ÅDT funnet for {tall(med_adt.sum())} av {tall(len(veger))} vegstrekninger "
         f"({veger.loc[med_adt, 'lengde_m'].sum() / veger['lengde_m'].sum():.0%} av veglengden)")
    return veger


# --------------------------------------------------------------------------
# 5. Utdata
# --------------------------------------------------------------------------

def bygg_inn_stiler(ut: Path, lagnavn: list[str]) -> None:
    """
    Legger QGIS-stilene fra stiler/<lag>.qml inn i GeoPackage-fila (tabellen layer_styles),
    slik at QGIS bruker dem automatisk når lagene åpnes.
    """
    rader = []
    for lag in lagnavn:
        qml = STILMAPPE / f"{lag}.qml"
        if not qml.exists():
            continue
        rader.append({
            "f_table_catalog": "", "f_table_schema": "", "f_table_name": lag,
            "f_geometry_column": pyogrio.read_info(ut, layer=lag)["geometry_name"],
            "styleName": lag, "styleQML": qml.read_text(encoding="utf-8"), "styleSLD": "",
            "useAsDefault": True, "description": STIL_BESKRIVELSE,
            "owner": "", "ui": "", "update_time": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })
    if rader:
        pyogrio.write_dataframe(pd.DataFrame(rader), ut, layer="layer_styles")


def er_egen_gpkg(sti: Path) -> bool:
    """Sant hvis GeoPackage-fila er laget av dette skriptet (kjennes igjen på de innebygde stilene)."""
    try:
        stiler = pyogrio.read_dataframe(sti, layer="layer_styles", columns=["description"],
                                        read_geometry=False)
    except Exception:  # ikke en GeoPackage, eller ingen stiltabell
        return False
    return bool((stiler["description"] == STIL_BESKRIVELSE).any())


def er_egen_csv(sti: Path) -> bool:
    """Sant hvis CSV-fila har nøyaktig de kolonnene skriptet skriver."""
    try:
        with open(sti, encoding="utf-8-sig") as f:
            return f.readline().strip() == ";".join(KRYSS_KOLONNER)
    except (OSError, UnicodeDecodeError):
        return False


def kontroller_utfil(ut: Path, overskriv: bool) -> None:
    """
    Stopper før noe lastes ned hvis utfilene ville erstattet filer skriptet ikke har laget selv,
    f.eks. en egen molde.gpkg i samme mappe.
    """
    if ut.suffix.lower() != ".gpkg":
        raise ValueError(f"Utfila må slutte på .gpkg (fikk «{ut.name}»).")
    if overskriv:
        return
    csv = ut.with_suffix(".csv")
    fremmede = [str(f) for f, er_egen in ((ut, er_egen_gpkg), (csv, er_egen_csv))
                if f.exists() and not er_egen(f)]
    if fremmede:
        raise ValueError(
            f"{' og '.join(fremmede)} finnes allerede og er ikke laget av dette skriptet. "
            "Velg et annet navn med «fil» i innstillingene eller --ut, "
            "eller bruk --overskriv hvis du vil erstatte dem.")


def skriv_resultat(ut: Path, kryss: gpd.GeoDataFrame, ulykker: gpd.GeoDataFrame,
                   vegnett: gpd.GeoDataFrame) -> list[str]:
    if ut.exists():
        ut.unlink()  # kontroller_utfil har sjekket at det er trygt
    rens_for_gpkg(vegnett).to_file(ut, layer="vegnett", driver="GPKG")
    lag = ["vegnett"]
    if not ulykker.empty:
        rens_for_gpkg(ulykker).to_file(ut, layer="ulykker", driver="GPKG")
        lag.append("ulykker")
    rens_for_gpkg(kryss[KRYSS_KOLONNER + ["geometry"]]).to_file(ut, layer="kryss", driver="GPKG")
    lag.append("kryss")
    bygg_inn_stiler(ut, lag)
    # Semikolon og desimalkomma, slik at fila åpnes riktig i norsk Excel
    kryss[KRYSS_KOLONNER].to_csv(ut.with_suffix(".csv"), index=False, sep=";", decimal=",",
                                 encoding="utf-8-sig")
    return lag


# --------------------------------------------------------------------------
# Hovedprogram
# --------------------------------------------------------------------------

def les_argumenter() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Kobler trafikkulykker (NVDB) til kryss (OSM) for et valgfritt område i Norge. "
                    "Standardverdiene hentes fra innstillinger.toml; argumentene under overstyrer dem.")
    p.add_argument("--innstillinger", type=Path, default=STANDARD_INNSTILLINGER,
                   help="Innstillingsfil (standard: innstillinger.toml ved siden av skriptet)")
    omr = p.add_mutually_exclusive_group()
    omr.add_argument("--sted", help="Stedsnavn, f.eks. \"Grünerløkka, Oslo\" eller \"Tromsøya\"")
    omr.add_argument("--polygon-fil", help="Fil med polygon for analyseområdet (GPKG/GeoJSON/SHP)")
    omr.add_argument("--boks", nargs=4, type=float, metavar=("VEST", "SØR", "ØST", "NORD"),
                     help="Boks i lengde-/breddegrader")
    p.add_argument("--fra-aar", type=int, help="Ta bare med ulykker fra dette året og senere")
    p.add_argument("--ulykker-fil", help="Ulykkesdata fra fil i stedet for NVDB-APIet")
    p.add_argument("--crs", help="Koordinatsystem for resultatet, f.eks. EPSG:25833 (standard: auto)")
    p.add_argument("--ut", help="Utfil (GeoPackage). Standard: navn fra analyseområdet")
    p.add_argument("--overskriv", action="store_true",
                   help="Erstatt utfilene selv om de ikke er laget av dette skriptet")
    return p.parse_args()


def main() -> int:
    args = les_argumenter()
    innst = les_innstillinger(args.innstillinger)
    omr, ana, utd, kil = innst["omrade"], innst["analyse"], innst["utdata"], innst["kilder"]

    # Område fra kommandolinjen erstatter området i innstillingsfila
    if args.sted or args.polygon_fil or args.boks:
        omr = {"sted": args.sted or "", "polygon_fil": args.polygon_fil or "",
               "polygon_lag": "", "boks": args.boks or []}
    fra_aar = args.fra_aar if args.fra_aar is not None else ana["fra_aar"]
    ulykker_fil = args.ulykker_fil or kil["ulykker_fil"]

    try:
        omrade, navn = finn_omrade(omr)
        crs = velg_crs(omrade, args.crs or utd["crs"])
        kontroller_omrade(omrade, crs, ana["maks_areal_km2"])
        ut = Path(args.ut or utd["fil"] or f"{navn}.gpkg")
        kontroller_utfil(ut, args.overskriv)
        kontroller_overpass_url(kil["overpass_url"])
    except (ValueError, FileNotFoundError) as feil:
        logg(f"FEIL: {feil}")
        return 1

    omrade_utm = gpd.GeoSeries([omrade], crs=CRS_GEO).to_crs(crs)
    med_kantsone = omrade_utm.buffer(KANTSONE_M).to_crs(CRS_GEO).iloc[0]
    omrade_utm = omrade_utm.iloc[0]

    velg_overpass(kil["overpass_url"])
    Gp = hent_gatenett(med_kantsone, crs)
    kryss = lag_kryss(Gp, ana["toleranse_m"])
    if not kryss.intersects(omrade_utm).any():
        logg("FEIL: Fant ingen kryss i området.")
        return 1

    radius = ana["radius_m"]
    xmin, ymin, xmax, ymax = ox.graph_to_gdfs(Gp, edges=False).total_bounds
    bbox = (xmin - radius, ymin - radius, xmax + radius, ymax + radius)

    if ulykker_fil:
        ulykker = les_ulykker_fil(ulykker_fil, crs)
    else:
        logg("Henter trafikkulykker (vegobjekttype 570) fra NVDB")
        ulykker = hent_nvdb(570, bbox, crs)
        logg(f"  Hentet {tall(len(ulykker))} ulykker")
    if fra_aar:
        ulykker = filtrer_aar(ulykker, fra_aar)
    # Ulykkene kobles mot alle kryss, også i kantsonen, slik at en ulykke aldri havner på et
    # kryss inne i området når et kryss like utenfor ligger nærmere. Deretter beholdes bare
    # kryssene i området, nummerert etter antall ulykker (1 = flest).
    kryss, ulykker = koble_ulykker(kryss, ulykker, radius)
    kryss = kryss[kryss.intersects(omrade_utm)]
    kryss = kryss.sort_values("antall_ulykker", ascending=False).reset_index(drop=True)
    ny_id = dict(zip(kryss["kryss_id"], kryss.index + 1))
    kryss["kryss_id"] = kryss.index + 1
    ulykker = ulykker[ulykker["kryss_id"].isin(ny_id)].copy()
    ulykker["kryss_id"] = ulykker["kryss_id"].map(ny_id)
    logg(f"  I området: {tall(len(kryss))} kryss og {tall(len(ulykker))} tilknyttede ulykker")

    logg("Henter trafikkmengde (vegobjekttype 540) fra NVDB")
    trafikk = hent_nvdb(540, bbox, crs)
    logg(f"  Hentet {tall(len(trafikk))} ÅDT-strekninger")
    vegnett = lag_vegnett(Gp, omrade_utm, trafikk, ana["adt_buffer_m"])

    try:
        lag = skriv_resultat(ut, kryss, ulykker, vegnett)
    except PermissionError:
        logg(f"FEIL: Får ikke skrevet til {ut}. Er fila åpen i QGIS eller et annet program? "
             "Lukk den, eller velg et annet navn med --ut.")
        return 1

    # ---- Oppsummering ----
    print("\nKryss etter type:")
    print(kryss.groupby("krysstype").agg(kryss=("kryss_id", "size"),
                                         ulykker=("antall_ulykker", "sum")).to_string())
    print("\nTopp 15 etter antall ulykker:")
    with pd.option_context("display.width", 200):
        print(kryss[KRYSS_KOLONNER].head(15).to_string(index=False))
    logg(f"Ferdig. Lagene {', '.join(lag)} er skrevet til {ut} (med QGIS-stiler), "
         f"og kryssene til {ut.with_suffix('.csv')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
