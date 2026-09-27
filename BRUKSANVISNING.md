# Bruksanvisning for kryss-screening

Denne veiledningen er for deg som ikke har brukt terminal eller Python før. Den tar deg
gjennom alt, fra nedlasting til ferdig kart i QGIS. Du trenger ikke kunne programmere.

Første gang tar det ca. 20 minutter. Etter det tar en ny analyse bare noen få minutter.

**Innhold**

1. [Hva du trenger](#1-hva-du-trenger)
2. [Last ned skriptet](#2-last-ned-skriptet)
3. [Engangsoppsett](#3-engangsoppsett)
4. [Velg analyseområde](#4-velg-analyseområde)
5. [Kjør analysen](#5-kjør-analysen)
6. [Se resultatet i QGIS](#6-se-resultatet-i-qgis)
7. [Kjør en ny analyse](#7-kjør-en-ny-analyse)
8. [Når noe går galt](#8-når-noe-går-galt)
9. [Andre innstillinger](#9-andre-innstillinger)

---

## 1. Hva du trenger

- **En Windows-PC.** Bruker du Mac eller Linux, se avsnittet *Installasjon* i
  [README.md](README.md).
- **QGIS, helst nyeste versjon.** Last ned fra [qgis.org](https://qgis.org/download/) hvis du
  ikke har det. QGIS har med seg Python, som skriptet trenger. Skriptet er testet med QGIS 3.44.
  I [punkt 3](#sjekk-python-versjonen) sjekker du at din versjon er ny nok.
- **Internett.** Skriptet henter data fra OpenStreetMap og Statens vegvesen mens det kjører.

### To ord du trenger å kjenne

- **Terminal:** Et vindu der du skriver kommandoer i stedet for å klikke. Du trenger bare å
  skrive noen få linjer, og alle står i denne veiledningen.
- **OSGeo4W Shell:** Terminalen som følger med QGIS. Den vet hvor QGIS sin Python ligger.
  **Bruk alltid denne**, ikke vanlig *Ledetekst* eller *PowerShell*.

---

## 2. Last ned skriptet

1. Gå til [github.com/chrisfuglset/kryss-screening](https://github.com/chrisfuglset/kryss-screening).
   Så lenge prosjektet er privat, må eieren ha invitert deg, og du må være logget inn på GitHub.
2. Klikk den grønne knappen **Code**, og velg **Download ZIP**.
3. Åpne mappen *Nedlastinger*, høyreklikk på `kryss-screening-main.zip` og velg
   **Pakk ut alle …**.
4. Velg hvor mappen skal ligge, f.eks. `Dokumenter`, og klikk **Pakk ut**.

Du har nå en mappe som heter `kryss-screening-main`. Ligger det en ny mappe med samme navn inni
den, bruk den innerste, altså den som inneholder `kryss_screening.py`. Mappen inneholder blant
annet:

| Fil | Hva den er |
|---|---|
| `kryss_screening.py` | Selve skriptet. Denne trenger du ikke åpne. |
| `innstillinger.toml` | Her velger du område. **Dette er den eneste filen du skal endre.** |
| `stiler` | Farger og symboler til QGIS. |

---

## 3. Engangsoppsett

Skriptet trenger én ekstra pakke, **osmnx**, som henter vegnett fra OpenStreetMap.
Dette gjør du bare én gang per PC.

### Åpne OSGeo4W Shell

1. Klikk på **Start**-knappen i Windows.
2. Skriv `OSGeo4W Shell`.
3. Klikk på **OSGeo4W Shell** i resultatlisten.

Det åpnes et svart vindu med tekst som slutter omtrent slik:

```
C:\Program Files\QGIS 3.44.9>
```

Tegnet `>` betyr at vinduet venter på en kommando fra deg.

### Sjekk Python-versjonen

Skriv følgende og trykk **Enter**:

```
python --version
```

Svaret skal være `Python 3.11` eller høyere, f.eks. `Python 3.12.10`. Står det 3.10 eller
lavere, må du oppdatere QGIS til nyeste versjon før du går videre.

### Installer osmnx

Skriv, eller kopier og lim inn, denne linjen og trykk **Enter**:

```
python -m pip install --user --no-deps "osmnx>=2.0,<3"
```

> **Tips:** Du limer inn i terminalen med **Ctrl+V** eller ved å høyreklikke.

Det skrives ut en del tekst. Det tar under ett minutt. Til slutt skal det stå noe som:

```
Successfully installed osmnx-2.1.1
```

Kommer det gul tekst med `WARNING` eller `notice`, kan du se bort fra den.

> **Hvorfor `--no-deps`?** QGIS har allerede de andre pakkene skriptet trenger. `--no-deps`
> hindrer at de blir erstattet med nye versjoner, som i verste fall kan få QGIS til å slutte å
> virke.

Oppsettet er ferdig. Du kan lukke vinduet.

---

## 4. Velg analyseområde

### Åpne innstillingsfilen

1. Gå inn i mappen `kryss-screening-main`.
2. Høyreklikk på `innstillinger.toml` og velg **Åpne med** → **Notisblokk**.
   Står ikke Notisblokk i listen, velg **Velg en annen app** og finn den der.

Filen ser slik ut øverst:

```toml
[omrade]
# Velg ÉN av de tre måtene å angi analyseområdet på. Kommenter ut de to andre.

# 1) Stedsnavn slik OpenStreetMap forstår det: kommune, bydel, tettsted o.l.
sted = "Grünerløkka, Oslo"

# 2) Polygonfil (GeoPackage, GeoJSON, Shape …) tegnet i QGIS.
# polygon_fil = "mitt_omrade.gpkg"
...
# 3) Boks i lengde-/breddegrader (WGS84): [vest, sør, øst, nord]
# boks = [10.74, 59.91, 10.80, 59.94]
```

### Tre regler for å redigere filen

1. **Linjer som starter med `#` blir ikke lest.** Å sette `#` foran en linje kalles å
   «kommentere den ut». Fjerner du `#`, blir linjen brukt.
2. **Bare én av `sted`, `polygon_fil` og `boks` kan være i bruk.** De to andre må ha `#` foran.
3. **Tekst skal stå i anførselstegn**, f.eks. `sted = "Tromsøya"`. Tall skal ikke ha det.

Du kan velge område på tre måter. Den første er enklest.

### Måte 1: Stedsnavn

Endre teksten mellom anførselstegnene på linjen `sted = …`. Eksempler som virker:

```toml
sted = "Grünerløkka, Oslo"     # bydel i Oslo, ca. 5 km²
sted = "Frogner, Oslo"         # bydel i Oslo, ca. 14 km²
sted = "Bergenhus, Bergen"     # bydel i Bergen, ca. 36 km²
sted = "Tromsøya"              # øya med Tromsø sentrum, ca. 23 km²
```

- «Norway» legges til automatisk, så du trenger ikke skrive det.
- Er et navn tvetydig, legg til kommune eller fylke, f.eks. `"Bergenhus, Bergen"`.
- **Bynavn gir hele kommunen**, og kommuner er ofte store fordi de tar med fjell, skog og sjø.
  `"Molde"` blir for eksempel nesten 2 000 km², og skriptet stopper ved 500 km². Vil du bare ha
  selve byen, bruk en bydel, tegn området selv (måte 2) eller bruk en boks (måte 3).
- Navn som «Molde sentrum» finnes ikke som område i OpenStreetMap og gir feilmelding. Bruk
  måte 2 eller 3 for sentrumsområder.
- Vil du sjekke at navnet blir funnet, søk på
  [nominatim.openstreetmap.org](https://nominatim.openstreetmap.org). Treffet må vises som et
  **område** på kartet, ikke som et punkt.

Lagre med **Ctrl+S** og gå til [punkt 5](#5-kjør-analysen).

### Måte 2: Tegn området selv i QGIS

Bruk denne når du vil analysere et bestemt område som ikke har et navn, f.eks. en gate eller
et planområde.

1. I QGIS: velg **Lag** → **Opprett lag** → **Nytt GeoPackage-lag …**.
2. Ved **Database**: klikk **…** og lagre filen i mappen `kryss-screening-main`, f.eks. som
   `mitt_omrade.gpkg`.
3. Ved **Geometritype**: velg **Polygon**. Klikk **OK**.
4. Klikk på blyanten (**Slå på redigering**) og deretter **Legg til polygonobjekt**.
5. Klikk rundt området i kartet. Høyreklikk for å avslutte, og klikk **OK**.
6. Klikk på blyanten igjen og velg **Lagre**.

Endre så innstillingsfilen slik: sett `#` foran `sted`, og fjern `#` foran `polygon_fil`.

```toml
# sted = "Grünerløkka, Oslo"

polygon_fil = "mitt_omrade.gpkg"
```

> **Ligger filen i en annen mappe?** Skriv hele stien med *enkle* anførselstegn,
> f.eks. `polygon_fil = 'C:\Users\ola\Documents\planomrade.gpkg'`. Med vanlige
> anførselstegn gir baklengs skråstrek `\` feil.

### Måte 3: Boks med koordinater

Oppgi fire tall: **vest, sør, øst, nord**, i lengde- og breddegrader.

1. Åpne [Google Maps](https://maps.google.com) og høyreklikk i **nedre venstre** hjørne av
   området. Øverst i menyen står to tall, f.eks. `59.9135, 10.7412`.
2. Høyreklikk i **øvre høyre** hjørne. Du får f.eks. `59.9398, 10.8021`.
3. **Pass på rekkefølgen.** Google viser *breddegrad* først og *lengdegrad* sist. Skriptet vil
   ha lengdegrad først:

| | Nedre venstre | Øvre høyre |
|---|---|---|
| Google viser | `59.9135, 10.7412` | `59.9398, 10.8021` |
| Betyr | sør, vest | nord, øst |

Innstillingsfilen blir da (husk `#` foran `sted`):

```toml
# sted = "Grünerløkka, Oslo"

boks = [10.7412, 59.9135, 10.8021, 59.9398]
```

Bruk **punktum** som desimaltegn, ikke komma.

### Lagre filen

Trykk **Ctrl+S** i Notisblokk. Du kan la Notisblokk være åpen.

---

## 5. Kjør analysen

### Gå til mappen i terminalen

Terminalen må «stå i» mappen med skriptet. Det gjør du slik:

1. Åpne mappen `kryss-screening-main` i Filutforsker.
2. Klikk i **adresselinjen** øverst, så stien blir markert. Trykk **Ctrl+C** for å kopiere.
3. Åpne **OSGeo4W Shell** fra Start-menyen, som i [punkt 3](#åpne-osgeo4w-shell).
4. Skriv `cd /d "`, lim inn stien med **Ctrl+V**, skriv `"` til slutt, og trykk **Enter**.
   Det ser omtrent slik ut:

   ```
   cd /d "C:\Users\ola\Documents\kryss-screening-main"
   ```

Linjen før `>` viser nå mappen din. Anførselstegnene trengs fordi stien kan ha mellomrom.

### Start skriptet

Skriv og trykk **Enter**:

```
python kryss_screening.py
```

Skriptet skriver ut hva det gjør underveis. For en bydel tar det 1–3 minutter, og for en hel
by kan det ta 10–20 minutter. **Ikke lukk vinduet** mens det jobber. Slik ser en vellykket
kjøring ut:

```
[10:31:13] Slår opp «Grünerløkka, Oslo, Norway» i OpenStreetMap
[10:31:15] Analyseområde: 4,8 km², koordinatsystem EPSG:25832
[10:31:15] Henter kjørbart gatenett fra OpenStreetMap (kan ta noen minutter)
[10:33:34] Gatenett: 762 noder, 1 586 kanter
...
[10:34:18]   I området: 243 kryss og 1 419 tilknyttede ulykker
...
[10:34:23] Ferdig. Lagene vegnett, ulykker, kryss er skrevet til grunerlokka.gpkg (med QGIS-stiler), og kryssene til grunerlokka.csv
```

Står det `Ferdig` nederst, har alt gått bra. Står det `FEIL` eller mye engelsk tekst, se
[punkt 8](#8-når-noe-går-galt).

### Hvor er resultatet?

I mappen `kryss-screening-main` ligger nå to nye filer, oppkalt etter området:

| Fil | Innhold |
|---|---|
| `grunerlokka.gpkg` | Kartdata for QGIS: kryss, ulykker og vegnett |
| `grunerlokka.csv` | Liste over kryssene, kan åpnes i Excel |

Det er også laget en mappe `cache`. Der lagrer skriptet data fra OpenStreetMap, slik at neste
kjøring går raskere. Du kan slette den når du vil.

---

## 6. Se resultatet i QGIS

### Legg til lagene

1. Åpne QGIS.
2. Dra filen `grunerlokka.gpkg` fra Filutforsker inn i kartvinduet i QGIS.
3. Et vindu spør hvilke lag du vil legge til. Klikk **Velg alle** og deretter
   **Legg til lag**.

Lagene får farger automatisk.

### Legg til bakgrunnskart

1. Finn panelet **Utforsker** til venstre. Ser du det ikke, velg **Vis** → **Paneler** →
   **Utforsker**.
2. Åpne **XYZ Tiles** og dobbeltklikk på **OpenStreetMap**.
3. I panelet **Lag**: dra *OpenStreetMap* helt nederst, ellers dekker bakgrunnskartet de andre
   lagene.

### Slik leser du kartet

| Lag | Hva det viser |
|---|---|
| **kryss** | Ett punkt per kryss. Jo større og mørkere, desto flere ulykker. |
| **ulykker** | Små grå punkter, én per ulykke som ligger ved et kryss. |
| **vegnett** | Vegene. Tykk, mørk blå betyr mye trafikk (ÅDT). Grå stiplet betyr at ÅDT mangler. |

**ÅDT** betyr *årsdøgntrafikk*: gjennomsnittlig antall kjøretøy per døgn gjennom året.

### Finn kryssene med flest ulykker

- Høyreklikk på laget **kryss** og velg **Åpne attributtabell**. Kryssene er nummerert etter
  antall ulykker, så `kryss_id` 1 har flest.
- Vil du se et kryss i kartet: klikk på radnummeret helt til venstre i tabellen, så raden blir
  merket. Klikk deretter på forstørrelsesglasset **Zoom kartet til de valgte radene** øverst i
  tabellen, eller trykk **Ctrl+J**.
- Vil du se ulykkene ved ett kryss: høyreklikk på **ulykker** → **Filter …**, skriv
  `"kryss_id" = 1` og klikk **OK**. Fjern filteret på samme måte etterpå.
- Klikk på **Identifiser objekter** (pil med «i») og deretter på en ulykke for å se alle
  opplysningene om den, f.eks. dato, ulykkestype og føreforhold.

### Åpne listen i Excel

Dobbeltklikk på `grunerlokka.csv`. Den åpnes med riktige kolonner i norsk Excel.

> **Husk:** Dette er en *screening* som viser hvor ulykkene samler seg. Det er ikke en faglig
> vurdering. Sjekk alltid kryssene mot flyfoto, NVDB og befaring før du trekker konklusjoner.

---

## 7. Kjør en ny analyse

1. Åpne `innstillinger.toml` i Notisblokk, endre området og lagre.
2. Åpne OSGeo4W Shell og gå til mappen med `cd /d "…"`, som i
   [punkt 5](#gå-til-mappen-i-terminalen).
3. Skriv `python kryss_screening.py` og trykk **Enter**.

Resultatet får automatisk navn etter det nye området, så de gamle filene blir liggende.

> **Tips:** Du kan hente frem forrige kommando med **pil opp** på tastaturet i stedet for å
> skrive den på nytt.

**Kjøre det samme området på nytt?** Da blir den gamle filen erstattet. Fjern lagene fra QGIS
først (høyreklikk → **Fjern lag**), ellers er filen i bruk og kan ikke skrives over.

---

## 8. Når noe går galt

Les den siste linjen i terminalen. Den forteller som regel hva som er galt. Finn meldingen i
tabellen under.

| Melding | Hva er galt | Hva du gjør |
|---|---|---|
| `'python' gjenkjennes ikke som en intern eller ekstern kommando` eller `Python was not found` | Du bruker vanlig Ledetekst eller PowerShell. | Lukk vinduet og åpne **OSGeo4W Shell**. |
| `No module named 'osmnx'` | Engangsoppsettet er ikke gjort. | Gjør [punkt 3](#installer-osmnx). |
| `No module named 'tomllib'` | QGIS er for gammel. | Installer nyeste QGIS. |
| `can't open file … kryss_screening.py` | Terminalen står ikke i riktig mappe. | Gå til mappen med `cd /d "…"`, se [punkt 5](#gå-til-mappen-i-terminalen). |
| `FEIL: Angi nøyaktig én av «sted», «polygon_fil» eller «boks»` | To eller ingen av områdelinjene er i bruk. | Sørg for at nøyaktig én av dem er uten `#` foran. |
| `TOMLDecodeError: Invalid …` | Skrivefeil i `innstillinger.toml`. | Sjekk at teksten står i anførselstegn og at stier med `\` har *enkle* anførselstegn. Linjenummeret står i meldingen. |
| `FEIL: Nominatim geocoder returned 0 results for query …` | Stedsnavnet ble ikke funnet. | Sjekk stavemåten og søk på navnet på [nominatim.openstreetmap.org](https://nominatim.openstreetmap.org). Finnes det ikke som område, bruk måte 2 eller 3. |
| `FEIL: Området fra stedsnavnet … er ikke en flate` | Navnet ga et punkt, ikke et område. | Bruk et mer presist navn, eller tegn området selv (måte 2). |
| `FEIL: Området er … km², over grensen` | Området er for stort. | Velg et mindre område, eller øk `maks_areal_km2`, se [punkt 9](#9-andre-innstillinger). |
| `FEIL: … finnes allerede og er ikke laget av dette skriptet` | Det finnes en annen fil med samme navn i mappen. | Gi resultatet et annet navn med `fil = "nytt_navn.gpkg"` i innstillingene. |
| `FEIL: Får ikke skrevet til …` | Filen er åpen i QGIS. | Fjern lagene fra QGIS, eller lukk QGIS, og kjør på nytt. |
| `DLL load failed` | Du bruker ikke OSGeo4W Shell. | Åpne **OSGeo4W Shell** og prøv igjen. |
| `svarer ikke, prøver neste` | En av OpenStreetMap-maskinene svarer ikke. | Ingenting. Skriptet prøver selv neste maskin. |
| `ADVARSEL: Fikk ikke kontakt med noen Overpass-server` | Ingen av OpenStreetMap-maskinene svarer. | Sjekk at du er på nett. Vent 10–15 minutter og prøv igjen. |
| `FEIL: overpass_url må være en https-adresse` | Feil i `overpass_url` i innstillingene. | Sett den tilbake til `overpass_url = ""`. |
| `429`, `Too Many Requests`, `timed out` eller `NVDB svarte 5…` | Tjenesten er opptatt eller nede. | Vent noen minutter og prøv igjen. |

Kommer du ikke videre: ta skjermbilde av terminalen og send det til den som ga deg skriptet.

---

## 9. Andre innstillinger

Lenger ned i `innstillinger.toml` finner du flere valg. Standardverdiene passer i de fleste
tilfeller.

| Innstilling | Standard | Hva den gjør |
|---|---|---|
| `fra_aar` | `0` | Ta bare med ulykker fra dette året og senere, f.eks. `2019`. `0` betyr alle år NVDB har. |
| `toleranse_m` | `15` | Veikryss som består av flere punkter nærmere enn dette (i meter) regnes som ett kryss. |
| `radius_m` | `30` | En ulykke regnes til et kryss hvis den ligger nærmere enn dette (i meter). |
| `adt_buffer_m` | `10` | Hvor nær vegen trafikktallene fra Statens vegvesen må ligge for å bli brukt. |
| `maks_areal_km2` | `500` | Stopper hvis området er større enn dette. Hele Oslo er ca. 450 km². |
| `fil` | `""` | Navn på resultatfilen, f.eks. `"molde_2019.gpkg"`. Tomt betyr navn fra området. |
| `crs` | `"auto"` | Koordinatsystem. `"auto"` velger riktig UTM-sone for Norge. |
| `ulykker_fil` | `""` | Bruk ulykkesdata fra en fil i stedet for å hente fra Statens vegvesen. |
| `overpass_url` | `""` | Hvilken OpenStreetMap-server som skal prøves først. La den stå tom. |

Et typisk eksempel er å bare ta med de siste fem årene:

```toml
fra_aar = 2021
```

---

**Datakilder:** Vegnett © OpenStreetMap-bidragsytere (ODbL). Trafikkulykker og trafikkmengde
© Statens vegvesen, NVDB (NLOD 2.0). Oppgi kildene når du bruker eller deler resultatene.
