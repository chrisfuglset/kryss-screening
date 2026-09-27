# kryss-screening

Kobler trafikkulykker til kryss for et valgfritt område i Norge, basert på åpne data fra
OpenStreetMap og Nasjonal vegdatabank (NVDB). Resultatet er én GeoPackage-fil med ferdige
stiler, som kan åpnes direkte i QGIS.


## Hva skriptet gjør

1. Henter kjørbart gatenett for området fra OpenStreetMap.
2. Slår sammen noder som ligger tett (f.eks. kryss med midtdeler) til ett kryss, og slår
   sammen hver rundkjøring til ett kryss.
3. Klassifiserer kryssene som T-kryss, X-kryss, flerarmet eller rundkjøring.
4. Henter trafikkulykker (vegobjekttype 570) og trafikkmengde (540) fra NVDB.
5. Kobler hver ulykke til nærmeste kryss innenfor 30 m. Ulykker som ikke ligger ved et kryss
   tas ikke med.
6. Overfører ÅDT fra NVDB til gatenettet der vegene overlapper.
7. Skriver tre lag til en GeoPackage med innebygde QGIS-stiler, pluss en CSV med kryssene.

## Kom i gang

Følg [BRUKSANVISNING.md](BRUKSANVISNING.md). 

```bash
git clone https://github.com/chrisfuglset/kryss-screening.git
cd kryss-screening
pip install -r requirements.txt
```

Åpne `innstillinger.toml`, skriv inn området ditt, og kjør:

```bash
python kryss_screening.py
```

Resultatet havner i mappen du kjører fra, f.eks. `molde.gpkg` og `molde.csv`. Dra
GeoPackage-filen inn i QGIS, så får lagene riktige farger automatisk.

## Velg analyseområde

Området settes i `[omrade]` i `innstillinger.toml`. Bruk **én** av tre måter:

**1. Stedsnavn**: kommune, bydel eller tettsted slik OpenStreetMap kjenner det.
«Norway» legges til automatisk. Er du usikker på navnet, søk det opp på
[nominatim.openstreetmap.org](https://nominatim.openstreetmap.org) og se at du får en flate.

```toml
sted = "Grünerløkka, Oslo"
```

**2. Polygonfil**: tegn området selv i QGIS og lagre som GeoPackage, GeoJSON eller Shape.
Alle flater i laget slås sammen.

```toml
polygon_fil = "mitt_omrade.gpkg"
polygon_lag = ""          # lagnavn; tomt = første lag
```

**3. Boks** i lengde- og breddegrader: `[vest, sør, øst, nord]`. Koordinatene finner du ved å
høyreklikke i f.eks. Google Maps eller norgeskart.no.

```toml
boks = [10.74, 59.91, 10.80, 59.94]
```

Du kan også overstyre området fra kommandolinjen uten å endre filen:

```bash
python kryss_screening.py --sted "Molde sentrum"
python kryss_screening.py --polygon-fil mitt_omrade.gpkg
python kryss_screening.py --boks 10.74 59.91 10.80 59.94
```

## Andre innstillinger

| Innstilling | Standard | Betydning |
|---|---|---|
| `fra_aar` | `0` | Ta bare med ulykker fra dette året og senere. `0` betyr alle år. |
| `toleranse_m` | `15` | Noder nærmere enn dette slås sammen til ett kryss. |
| `radius_m` | `30` | Ulykker innenfor denne avstanden kobles til nærmeste kryss. |
| `adt_buffer_m` | `10` | Hvor langt fra OSM-vegen en NVDB-strekning kan ligge og likevel gi ÅDT. |
| `maks_areal_km2` | `500` | Stopper kjøringen hvis området er større enn dette. Hele Oslo er ca. 450 km². |
| `fil` | `""` | Navn på utfilen (må slutte på `.gpkg`). Tomt betyr navn fra området. |
| `crs` | `"auto"` | Koordinatsystem. `auto` velger ETRS89 / UTM 32, 33 eller 35 etter hvor området ligger. |
| `ulykker_fil` | `""` | Ulykkesdata fra fil, f.eks. fra Geonorge, i stedet for NVDB-APIet. |

Kjør `python kryss_screening.py --help` for alle valg på kommandolinjen.

**Eksisterende filer:** Skriptet overskriver bare GeoPackage- og CSV-filer det har laget selv.
Finnes det allerede en fil med samme navn fra et annet sted, f.eks. din egen `molde.gpkg`,
stopper skriptet før det laster ned noe. Velg da et annet navn med `fil` eller `--ut`, eller
bruk `--overskriv` hvis du faktisk vil erstatte filen.

## Resultat

GeoPackage-filen har tre lag:

**`kryss`**: ett punkt per kryss, nummerert etter antall ulykker (1 = flest).

| Kolonne | Innhold |
|---|---|
| `kryss_id` | Løpenummer, 1 er krysset med flest ulykker |
| `krysstype` | T-kryss, X-kryss, flerarmet eller rundkjøring |
| `antall_armer` | Antall veger inn i krysset |
| `hoyeste_vegklasse` | Viktigste OSM-vegklasse i krysset (`primary`, `secondary` …) |
| `maks_fart` | Høyeste fartsgrense i OSM på vegene inn i krysset |
| `antall_ulykker` | Antall ulykker koblet til krysset |

**`ulykker`**: ulykkene som er koblet til et kryss, med alle attributtene fra NVDB, pluss
`kryss_id` og `avstand_til_kryss_m`.

**`vegnett`**: kjørbart gatenett fra OSM med `adt`, `adt_aar`, `adt_andel_lange_pst` og
`adt_grunnlag` fra NVDB der det finnes.

CSV-filen har samme innhold som `kryss`-laget, med semikolon og desimalkomma, slik at den
åpnes riktig i norsk Excel.

Stilene ligger i `stiler/`. Endrer du en `.qml`-fil der, bruker neste kjøring den nye stilen.

## Installasjon

Skriptet krever Python 3.11 eller nyere.

### Med vanlig Python

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

### Med Python-en som følger med QGIS (Windows)

Har du QGIS installert, trenger du ikke egen Python. Åpne **OSGeo4W Shell** fra Start-menyen
og kjør:

```bash
python -m pip install --user --no-deps osmnx
python kryss_screening.py
```

QGIS har allerede de andre pakkene. `--no-deps` hindrer pip i å oppgradere pakker QGIS er
avhengig av. Bruk OSGeo4W Shell og ikke et vanlig terminalvindu, ellers kan importen av
`pyproj` feile med en DLL-feil.

## Kjente begrensninger

- **Gamle ÅDT-tall.** Mange ÅDT-verdier i NVDB er mange år gamle. Sjekk `adt_aar` og
  `adt_grunnlag` før du bruker dem.
- **Parallelle veger.** ÅDT overføres etter hvilken NVDB-strekning som overlapper OSM-vegen
  mest. Ved planskilte kryss kan ramper få ÅDT fra hovedvegen ved siden av.
- **Alvorlighetsgrad.** NVDB-APIet gir ikke skadegrad for ulykkene. Trenger du det, last ned
  ulykkesdata fra Geonorge og bruk `ulykker_fil`.
- **Kryssdata fra OSM.** Antall armer og vegklasse kommer fra OpenStreetMap og er ikke bedre
  enn kartdataene der.
- **Bare Norge.** NVDB har bare norske data.

## Datakilder og kreditering

- Gatenett: © [OpenStreetMap](https://www.openstreetmap.org/copyright)-bidragsytere,
  tilgjengelig under [ODbL](https://opendatacommons.org/licenses/odbl/).
- Trafikkulykker og trafikkmengde: © Statens vegvesen, [NVDB](https://nvdb.atlas.vegvesen.no/),
  under [NLOD 2.0](https://data.norge.no/nlod/no/2.0).

