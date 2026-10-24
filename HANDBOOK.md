# Ahmedabad Urban Scanner — Reproducibility Handbook

> **Living document.** Update this file whenever a source, parameter, command,
> method, output path, limitation, or software version changes.

Last updated: **2026-10-20 IST**
Project path: `<repo-root>`
Deployment branch: `main` (prepare changes on a topic branch)

## 1. Purpose

This handbook documents how to reproduce the Ahmedabad Urban Scanner manually.
The project currently contains:

1. a Google Open Buildings V3 building-footprint pilot;
2. a pedestrian-network 5/10/15-minute accessibility analysis;
3. a hot-season heat, greenery, and environmental analysis;
4. a complete local interactive web application with selective PlanX diagnostics.

A building is used as the visual and locational unit. Values must retain their
actual evidence type and geography. Building proximity must not be described as
observed facility use, pedestrian activity, wellbeing, vitality, or service
quality.

## 2. Current study area

The first end-to-end pilot covers Navrangpura and adjacent central Ahmedabad.

| Parameter | Value |
|---|---|
| Study bbox order | `[min_lon, min_lat, max_lon, max_lat]` |
| Study bbox | `[72.5443429, 23.0159998, 72.5843429, 23.0559998]` |
| Source CRS | EPSG:4326 |
| Metric analysis CRS | EPSG:32643 — WGS 84 / UTM zone 43N |
| Walking-network buffer | 1,600 m |
| Walking speed | 4.8 km/h, or 80 m/min |
| Accessibility thresholds | 5, 10, and 15 minutes |
| Maximum reported search time | 45 minutes |
| Maximum accepted building-network snap | 250 m |

The complete configuration is stored in:

```text
config/ahmedabad_pilot.toml
```

Do not silently change a value in code without updating the configuration and
this handbook.

### 2.1 New Ahmedabad–Gandhinagar scale-up extent

The user selected a new future study area by drawing a black polygon around the
Ahmedabad ring-road area, Bopal, South Bopal, and Gandhinagar. The supplied map
was a 588 × 670 pixel screenshot rather than an exported GIS geometry. The
outline was therefore digitised from its 39 circular vertices and approximately
georeferenced using visible map labels and landmarks.

Verified outputs:

```text
config/study_areas/ahmedabad-gandhinagar-black-line.geojson
config/study_areas/ahmedabad-gandhinagar-black-line.gpkg
config/study_areas/ahmedabad-gandhinagar-black-line-shapefile.zip
config/study_areas/ahmedabad-gandhinagar-black-line.bbox.txt
config/study_areas/ahmedabad-gandhinagar-black-line.toml
config/study_areas/ahmedabad-gandhinagar-black-line.metadata.json
outputs/study_area/ahmedabad-gandhinagar-black-line-digitisation-preview.png
```

| Property | Value |
|---|---:|
| CRS | EPSG:4326 |
| Recommended metric CRS | EPSG:32643 |
| Vertices | 39 |
| West | 72.415466858 |
| South | 22.917600869 |
| East | 72.738803816 |
| North | 23.267288991 |
| Approximate area | 651.84 km² |
| Approximate perimeter | 117.87 km |

Rebuild the bundle with:

```bash
uv run python scripts/build_study_area_extent.py
```

The polygon is a faithful screen digitisation of the visible black line, but
its geographic position remains approximate, with an estimated uncertainty of
about ±1 km because place labels are not survey-control points. It is suitable
as a reproducible acquisition/clipping extent for Luna's next bounded workflow,
not as a statutory municipal, development-plan, property, or administrative
boundary. Use the polygon for clipping and the bbox only for coarse download
queries. Replace it if the original drawing can be exported as KML, GeoJSON, or
another georeferenced vector file.

## 3. Software environment

Verified environment on 2026-10-17:

| Software | Version |
|---|---|
| macOS | 15.0.1 host environment |
| Python | 3.13.1 |
| uv | 0.12.7 |
| OSMnx | 2.1.1 |
| GeoPandas | 1.1.4 |
| Shapely | 2.1.2 |
| PyArrow | 25.0.1 |
| Matplotlib | 3.11.2 |
| Rasterio | 1.5.1 |
| NumPy | 2.5.3 |
| pystac-client | 0.9.0 |
| planetary-computer | 1.0.0 |
| Node.js | 26.7.0 |
| npm | 11.19.0 |
| MapLibre GL JS | 6.14.0 |
| Vite | 7.3.7 |
| Vitest | 4.1.12 |

### 3.1 Install uv

Follow the official uv installation documentation:

- <https://docs.astral.sh/uv/getting-started/installation/>

### 3.2 Priority 4 overlay legend contract

Published `metadata.json` contains `overlay_legends`, with one record for every
`PLANX_OVERLAYS` key. The `spaceSyntax` record is nested by selector and includes
`off`, which explicitly means no legend. Each record declares a stable key/title,
renderer kind, geometry/symbol shape, rendered property when applicable, unit and
`unit_status`, provenance context, caveat, numeric applicability, entries, and
source metadata. Classification records embed the exact corresponding
`overlay_classifications` object; labels are generated from its min/breaks/max or
exact categories, so the browser need not inspect MapLibre expressions.

The frontend builds one deterministic legend model from the selected building
indicator, the selected space-syntax field, active PlanX overlays, and the
existing `PLANX_OVERLAYS` declaration order. Space syntax has precedence and
`spaceSyntax=off` contributes no section. When any overlay is active, the
building legend is suppressed; when all overlays are off, the selected building
indicator legend returns. Every active overlay gets its own compact section,
including line, circle, fill, raster, scenario, constant, binary, interpolated,
and no-data records. The help panel is rendered from this same model.

Legend provenance is renderer-first: describe the property and stops/colors that
currently reach pixels, not merely fields available in the source data. Constant
vector fills receive single-symbol legends rather than invented numeric ramps.
Raster ranges, palettes, units, and validation status may be published only when
verified from the raster-generation code or manifest. Raster manifests include
explicit sampled palette stops so the browser does not inspect PNG pixels.
Height-dependent raster products retain an explicit unverified caveat, and solar
irradiation visibly states that its unit is not documented. This legend stage does
not change MapLibre paint expressions or analytical symbology.

The contextual **Urban flood-risk zones** overlay publishes the supplied
VEDAS/ISRO GeoJSON unchanged as `data/ahm-urban-flood-risk-zones.geojson`. Its
`uf_risk` source attribute drives the map colors, legend, and click inspector for
`Very High Risk Areas`, `High Risk Areas`, and `Moderate Risk Areas`. The overlay
is off by default, appears under the existing **Environment** context heading,
and is not dissolved, simplified, transformed, or reclassified.


### 3.3 Install the project

From the project root:

```bash
uv sync --group dev
```

This creates `.venv/` and installs the versions resolved in `uv.lock`.

### 3.4 Verify imports and tests

```bash
uv run python --version
uv run python -c "import geopandas, shapely, osmnx, pyarrow; print('imports ok')"
uv run --group dev pytest tests/ -q
```

Current verified test result:

```text
129 passed (Python suite; see the Local Area Profile release gate below for the
current frontend suite)
```

## 4. Project structure

```text
ahmedabad-urban-scanner/
├── ahmedabad_scanner/       # tested reusable Python functions
├── config/                  # study parameters
├── data/                    # downloaded and generated data; gitignored
│   ├── google-open-buildings-v3/
│   ├── osm/
│   ├── osmnx-cache/
│   └── derived/
├── outputs/                 # map images and later web artifacts
├── reports/                 # JSON audits and summaries
├── scripts/                 # executable workflow stages
├── tests/                   # automated tests
├── HANDBOOK.md              # this living manual
├── AHMEDABAD_SCANNER.md     # staged analytical design
├── pyproject.toml
└── uv.lock
```

`data/` is intentionally excluded from Git because the raw files are large.
The scripts, configuration, reports, and handbook record how to rebuild it.

# Part I — Building footprints

## 5. Building source

The active footprint source is **Google Research Open Buildings V3**.

Official resources:

- Dataset page: <https://sites.research.google/gr/open-buildings/>
- Earth Engine catalog: <https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_Research_open-buildings_v3_polygons>
- Official regional-download notebook: <https://colab.research.google.com/github/google-research/google-research/blob/master/building_detection/open_buildings_download_region_polygons.ipynb>
- Tile metadata: <https://openbuildings-public-dot-gweb-research.uw.r.appspot.com/public/tiles.geojson>
- Score thresholds: <https://storage.googleapis.com/open-buildings-data/v3/score_thresholds_s2_level_4.csv>

Open Buildings V3 supplies:

- polygon geometry;
- centroid latitude and longitude;
- modelled footprint area;
- detection confidence;
- full Plus Code.

It does **not** supply building use, address, construction year, floor count,
height, occupancy, tenure, or resident information.

### 5.1 Published display geometry contract

The canonical browser display archive is `web/public/data/buildings.pmtiles`.
It is Candidate A geometry-only PMTiles: source-layer `buildings`, zooms 1–16,
53,159,322 bytes, SHA-256
`01d9dfa22e15a6ed50eec3d776f298130ce1b31045c40f09edbbf365422e4ad7`.
The browser renders a fixed neutral polygon fill and outline; only visibility and
opacity are user-controlled. No area-based colour expression, no-data filter,
hover state, click selection, selected outline or building inspector may depend
on this archive because its feature properties are empty.

The superseded full-property display archive is retained outside the publication
at `archive/display-buildings-rollback-2026-10-23/buildings-full-properties.pmtiles`
(144,950,089 bytes; SHA-256
`fa7dfc5f79aa7a27295ed84dba4e0a5fb1101cd6b367bf3b70ad370ca9220fcf`). This is a
rollback artifact, not a deployed source.

The analytical `web/public/data/local-profile/buildings.fgb` asset and its
`web/dist` copy are separate and remain byte-identical. Local Area Profile
analytics must not be inferred from the geometry-only display archive.

The separate Open Buildings Temporal source supplies a modelled `building_height`
band in metres. For this project, the 2023 source tiles were downloaded directly
from the public temporal bucket and clipped to the study boundary. The cleaned
height raster is `data/external/open-buildings-height/ahmedabad-gandhinagar-building-height-2023.tif`.
It contains 228,452 valid 30 m pixels ranging from 0.023 to 92.319 m; it is not
 a terrain-plus-buildings DSM and should not be interpreted as observed survey height.

The source offers dual licensing under CC BY 4.0 and ODbL 1.0. Retain Google
Research attribution and confirm the preferred licence before publication.

## 6. Identify the Open Buildings shard

Open Buildings regional downloads are divided into level-6 S2 shards. The
pilot bbox intersects:

```text
S2 level 6 token: 395f
```

The full level-4 Ahmedabad-area cell is token `395`. Its published confidence
thresholds are:

| Intended precision | Confidence threshold |
|---|---:|
| 80% | 0.756 |
| 85% | 0.802 |
| 90% | 0.879 |

The pilot uses **0.802**, the cell's published 85% precision threshold. This is
not a completeness threshold: increasing confidence generally removes both
false detections and some real buildings.

The S2 token is reproduced in code by:

```python
from ahmedabad_scanner.open_buildings import s2_tokens_for_bbox

s2_tokens_for_bbox(
    (72.5443429, 23.0159998, 72.5843429, 23.0559998),
    level=6,
)
# ['395f']
```

## 7. Download the raw footprint shard

Create the destination directory:

```bash
mkdir -p data/google-open-buildings-v3/raw
```

Download with resume support:

```bash
curl -L --fail --show-error --continue-at - \
  --output data/google-open-buildings-v3/raw/395f_buildings.csv.gz \
  https://storage.googleapis.com/open-buildings-data/v3/polygons_s2_level_6_gzip_no_header/395f_buildings.csv.gz
```

Verify the compressed file:

```bash
gzip -t data/google-open-buildings-v3/raw/395f_buildings.csv.gz
```

Verified raw file size:

```text
504,268,007 bytes
```

The file is much larger than the pilot because the S2 shard extends well beyond
Navrangpura. The preparation script reads it in chunks and filters centroids to
the configured bbox before parsing WKT polygons.

## 8. Prepare pilot buildings

Run:

```bash
uv run python scripts/build_pilot_buildings.py
```

Processing sequence:

1. Read `config/ahmedabad_pilot.toml`.
2. Recalculate the level-6 S2 covering and verify it equals `395f`.
3. Read the compressed CSV in chunks.
4. Filter by the published centroid longitude and latitude.
5. Parse WKT only for selected records.
6. Apply confidence `>= 0.802`.
7. Repair geometries where possible.
8. Keep polygon and multipolygon geometries.
9. Select buildings whose representative points lie inside the study bbox.
10. Project to EPSG:32643.
11. Remove footprints smaller than 10 m².
12. Calculate footprint area, perimeter, compactness, elongation, and orientation.
13. Export GeoParquet, summary JSON, and a QA map.

### 8.1 Morphology calculations

Compactness is:

```text
4 × π × area / perimeter²
```

It approaches 1 for a circle and falls for elongated or irregular footprints.

Elongation is the longest side divided by the shortest side of the minimum
rotated rectangle. Orientation is the direction of its longest side in degrees
within `[0, 180)`.

### 8.2 Verified building result

| Check | Result |
|---|---:|
| Source records with centroid in bbox | 42,495 |
| Prepared buildings | 17,847 |
| Valid geometries | 17,847 |
| Empty geometries | 0 |
| Duplicate building IDs | 0 |
| Median footprint area | 150.18 m² |
| Mean footprint area | 202.23 m² |
| Minimum retained area | 11.54 m² |
| Maximum area | 7,409.72 m² |
| Median confidence | 0.8486 |

Outputs:

```text
data/derived/navrangpura-open-buildings-v3.parquet
outputs/navrangpura_open_buildings_v3_qa.png
reports/navrangpura_open_buildings_v3_summary.json
```

# Part II — Pedestrian-network accessibility

## 9. Accessibility data sources

### 9.1 Street and walking network

Source: **OpenStreetMap contributors**, queried through OSMnx and the Overpass
API.

- OpenStreetMap: <https://www.openstreetmap.org/>
- OSM copyright and ODbL attribution: <https://www.openstreetmap.org/copyright>
- OSMnx documentation: <https://osmnx.readthedocs.io/>
- Overpass API: <https://wiki.openstreetmap.org/wiki/Overpass_API>

The network query uses OSMnx `network_type="walk"`. It includes OSM ways that
OSMnx identifies as walkable and excludes explicitly private or foot-prohibited
ways according to its current filter.

### 9.2 Destination data

Destinations are queried from OpenStreetMap within the buffered network bbox.
The exact classification rules live in:

```text
ahmedabad_scanner/destinations.py
```

Current categories and included OSM values:

| Category | OSM values |
|---|---|
| Health | `amenity=clinic/doctors/hospital/pharmacy` |
| Education | `amenity=school/kindergarten/college/university` |
| Food | `amenity=marketplace`; selected food `shop=*` values |
| Transport | bus stops, public-transport platforms/stations/stop positions, selected railway stops |
| Green | parks, gardens, playgrounds, recreation grounds |
| Civic | community centres, social facilities, town halls |
| Culture | libraries, arts centres, cinemas, theatres, museums, galleries |
| Sport | fitness centres, pitches, sports centres, stadiums, swimming pools |

The query intentionally does not use `shop=true`, because that would mix food
access with unrelated retail.

## 10. Download and build the walking analysis

Run the complete acquisition and analysis:

```bash
uv run python scripts/build_accessibility.py
```

This performs live Overpass queries and saves the returned source data.

For subsequent reproducible reruns without querying Overpass again:

```bash
uv run python scripts/build_accessibility.py --reuse
```

Saved raw/cache inputs:

```text
data/osm/navrangpura_walk_buffered.graphml
data/osm/navrangpura_destinations_buffered.gpkg
data/osmnx-cache/
```

The first verified live query was run on **2026-10-17 IST**. OSM is a living
database, so a fresh query on another date can produce different counts. Use
`--reuse` for exact repetition of this snapshot.

## 11. Network preparation

The study bbox is buffered by 1,600 m to reduce artificial 15-minute boundary
effects.

Buffered query bbox:

```text
[72.52873616916015,
 23.001557243779402,
 72.59995017931962,
 23.070442265802292]
```

Processing:

1. Download a simplified walkable OSM graph.
2. Retain all components rather than silently dropping disconnected areas.
3. Project the graph to EPSG:32643.
4. Use the metric OSMnx `length` attribute.
5. Calculate walking time for every directed edge.

For 4.8 km/h:

```text
metres per minute = 4.8 × 1,000 / 60 = 80
edge walking time = edge length in metres / 80
```

Verified graph:

| Measure | Result |
|---|---:|
| Nodes | 10,411 |
| Directed edges | 27,852 |
| Weak components | 94 |
| Nodes in largest undirected component | 10,046 |

The component count must not be interpreted as 94 neighbourhoods. Small
components may represent mapped internal paths, disconnected service areas, or
network errors requiring later inspection.

## 12. Building-network connections

Each building footprint is converted to a representative interior point and
snapped to the nearest walkable network node.

The direct connection distance is retained separately. The nearest-destination
walking time includes:

```text
building connection time + network shortest-path time
```

Current snap-distance results:

| Statistic | Distance |
|---|---:|
| Median | 39.120 m |
| 90th percentile | 81.138 m |
| 95th percentile | 99.232 m |
| Maximum | 238.355 m |
| Buildings over 250 m | 0 |

These straight-line connection legs are modelling devices, not verified gates
or entrances. Later field/imagery validation should replace them where building
entrances or compound access points are known.

## 13. Destination preparation

OSM nodes, ways, and relations are converted to one destination point:

- mapped point features retain their point;
- polygons use an interior representative point;
- each feature retains its OSM element type and ID;
- duplicate OSM element identifiers are removed;
- destination points are snapped to the pedestrian network.

Current destination inventory:

| Category | Destinations | Unique network nodes |
|---|---:|---:|
| Health | 399 | 316 |
| Education | 61 | 57 |
| Food | 35 | 33 |
| Transport | 126 | 88 |
| Green | 106 | 99 |
| Civic | 8 | 8 |
| Culture | 45 | 40 |
| Sport | 72 | 59 |
| **Total** | **852** | — |

The imbalance—particularly only 35 mapped food destinations and 8 civic
facilities—is a data-quality warning. It probably reflects incomplete or uneven
OSM tagging, not the real absence of everyday shops or civic services.

## 14. Accessibility calculation

For every category:

1. Snap all destinations to graph nodes.
2. Reverse the directed graph for destination-to-origin multi-source routing.
3. Calculate the shortest network time from every reachable node to the nearest
   destination using `walk_time_min`.
4. Add the building-to-network connection time.
5. Calculate destination counts at 5, 10, and 15 minutes from each snapped
   network node.
6. Mark whether the nearest destination is reachable in 15 minutes.
7. Count how many of the eight categories are reachable in 15 minutes.

Destination counts currently exclude the building connection leg. This is
explicit in the configuration:

```toml
counts_include_building_connection = false
```

Nearest-destination times include that connection. Do not compare the count and
nearest-time measures as if they used identical origins.

## 15. Preliminary accessibility results

These values describe **modelled access to currently mapped OSM destinations**.
They are not final policy findings.

| Category | Median nearest walk | Buildings within 15 min |
|---|---:|---:|
| Health | 4.465 min | 98.46% |
| Education | 9.738 min | 83.82% |
| Food | 10.130 min | 69.89% |
| Transport | 8.315 min | 91.38% |
| Green | 9.235 min | 93.42% |
| Civic | 21.706 min | 24.39% |
| Culture | 10.082 min | 82.98% |
| Sport | 9.658 min | 89.20% |

Additional results:

| Measure | Result |
|---|---:|
| Median categories reachable in 15 minutes | 7 of 8 |
| Buildings reaching all eight categories | 18.37% |

The extremely high health coverage and low civic coverage should be treated as
signals to audit category definitions and OSM completeness—not immediately as
urban-performance conclusions.

## 16. Accessibility outputs

```text
data/derived/navrangpura-building-accessibility.parquet
data/derived/navrangpura-osm-destinations.parquet
data/derived/navrangpura-walk-nodes.parquet
data/derived/navrangpura-walk-edges.parquet
outputs/accessibility/navrangpura_accessibility_summary.png
reports/navrangpura_accessibility_summary.json
```

The building output contains:

- source building attributes and morphology;
- snapped network node;
- snap distance and connection time;
- nearest walking time for each category;
- destination counts within 5, 10, and 15 minutes;
- categories reachable within 15 minutes;
- network-snap quality flag.

## 17. Required validation before publication

The computational workflow is working, but the following evidence checks remain
mandatory before interpreting the results academically:

- compare POIs against AMC and sectoral facility registers;
- manually inspect unmapped food shops and informal markets;
- distinguish public transport platforms from duplicate stop positions;
- replace park representative points with verified entrances or sampled edges;
- inspect disconnected network components;
- inspect several actual shortest routes around bridges, railways, compounds,
  and the Sabarmati river;
- test slower walking speeds, such as 3.2 km/h;
- test sensitivity to the 1,600 m buffer;
- record facility capacity, affordability, opening hours, and public/private
  status where available.

## 18. Interpretation safeguards

Always describe these outputs as:

- modelled pedestrian-network proximity;
- based on the mapped OSM network and destinations;
- calculated at an assumed walking speed;
- subject to OSM completeness and tagging quality.

Do not call them:

- observed pedestrian behaviour;
- facility use;
- walkability without qualification;
- service quality;
- social inclusion;
- vitality;
- wellbeing.

# Part III — Heat, greenery, and environment

## 19. Heat, greenery, and environmental scanner

This stage is implemented as a reproducible multi-scene hot-season composite.
It adds satellite-derived environmental context to the existing building and
accessibility table. It does not claim to measure indoor conditions, personal
heat exposure, air temperature, thermal comfort, shade, or tree canopy.

### 19.1 Sources

The script queries the Microsoft Planetary Computer STAC API:

- STAC endpoint: <https://planetarycomputer.microsoft.com/api/stac/v1>
- Planetary Computer data catalog: <https://planetarycomputer.microsoft.com/catalog>
- Planetary Computer Python package: <https://github.com/microsoft/planetary-computer-sdk-for-python>

Land-surface temperature source:

- Collection: `landsat-c2-l2`
- Product: USGS Landsat 8/9 Collection 2 Level-2 Surface Temperature `ST_B10`
- USGS Level-2 overview: <https://www.usgs.gov/landsat-missions/landsat-collection-2-level-2-science-products>
- USGS scale-factor guidance: <https://www.usgs.gov/faqs/how-do-i-use-a-scale-factor-landsat-level-2-science-products>
- Microsoft collection documentation: <https://planetarycomputer.microsoft.com/dataset/landsat-c2-l2>

Vegetation source:

- Collection: `sentinel-2-l2a`
- Product: Copernicus Sentinel-2 Level-2A bottom-of-atmosphere reflectance
- Sentinel-2 L2A product specification: <https://sentiwiki.copernicus.eu/web/s2-products>
- Microsoft collection documentation: <https://planetarycomputer.microsoft.com/dataset/sentinel-2-l2a>

The workflow reads small bounded windows from cloud-optimized GeoTIFF assets;
it does not download the complete satellite granules. Exact STAC item metadata
is saved locally so every selected scene remains auditable:

```text
data/satellite/stac/landsat_items.json
data/satellite/stac/sentinel_items.json
```

### 19.2 Configured seasonal and spatial parameters

| Parameter | Value |
|---|---:|
| Hot-season date range | 2026-04-01 to 2026-05-31 |
| Landsat scene-level cloud limit | < 5% |
| Maximum Landsat scenes | 10 |
| Landsat output resolution | 30 m |
| Sentinel-2 scene-level cloud limit | < 5% |
| Maximum Sentinel-2 scenes | 10 |
| Sentinel-2 MGRS tile | 43QBF |
| Sentinel-2 output resolution | 10 m |
| Raster processing buffer | 150 m |
| Building LST neighbourhood | 100 m radius |
| Building NDVI neighbourhood | 50 m radius |
| Vegetated-pixel threshold | NDVI >= 0.3 |
| Minimum acceptable observations | 3 scenes |

Scene-level cloud percentages apply to the full source scene or tile, not only
the pilot. Pixel-level QA/SCL masks are also applied inside the study area.

### 19.3 Install satellite dependencies

The dependencies are locked in `pyproject.toml` and `uv.lock`. They were added
with:

```bash
uv add pystac-client planetary-computer
```

For a fresh checkout, the usual command is sufficient:

```bash
uv sync --group dev
```

### 19.4 Run the environmental workflow

Acquire/query the configured scenes and rebuild all composites:

```bash
uv run python scripts/build_environment.py
```

Reuse previously generated composite rasters without remote satellite reads:

```bash
uv run python scripts/build_environment.py --reuse
```

`--reuse` still recalculates the building-level neighbourhood statistics, map,
and summary. It requires the four saved composite/count rasters and the two
saved STAC item manifests.

### 19.5 Scene selection

The STAC query intersects the pilot bbox and configured date range. Candidate
scenes must pass the configured scene-level cloud threshold. If more candidates
exist than the maximum, the script selects evenly spaced acquisitions across
the date range rather than taking only the first or last scenes.

Selected Landsat item IDs:

```text
LC08_L2SP_149044_20260404_02_T1
LC09_L2SP_149044_20260412_02_T1
LC08_L2SP_149044_20260420_02_T1
LC09_L2SP_148044_20260421_02_T1
LC08_L2SP_148044_20260429_02_T1
LC08_L2SP_149044_20260506_02_T1
LC09_L2SP_149044_20260514_02_T1
LC08_L2SP_148044_20260515_02_T1
LC09_L2SP_148044_20260523_02_T1
LC08_L2SP_148044_20260531_02_T1
```

Selected Sentinel-2 item IDs:

```text
S2C_MSIL2A_20260406T053641_R005_T43QBF_20260406T102316
S2B_MSIL2A_20260411T053639_R005_T43QBF_20260411T092032
S2C_MSIL2A_20260416T053641_R005_T43QBF_20260416T104257
S2C_MSIL2A_20260426T053641_R005_T43QBF_20260426T101812
S2A_MSIL2A_20260428T054251_R005_T43QBF_20260428T103009
S2B_MSIL2A_20260501T053639_R005_T43QBF_20260501T091554
S2C_MSIL2A_20260506T053641_R005_T43QBF_20260506T102010
S2C_MSIL2A_20260516T053641_R005_T43QBF_20260516T101809
S2B_MSIL2A_20260521T053639_R005_T43QBF_20260521T091732
S2C_MSIL2A_20260526T053641_R005_T43QBF_20260526T102117
```

These IDs are a reproducible 2026 hot-season snapshot, not a permanent claim
that the same dates are best for every later citywide or longitudinal analysis.

### 19.6 Landsat surface-temperature processing

For each selected Landsat scene:

1. Read `lwir11`, the STAC alias for Collection 2 `ST_B10`.
2. Reproject/resample the bounded window to EPSG:32643 at 30 m.
3. Read `qa_pixel` using nearest-neighbour resampling.
4. Reject fill, dilated-cloud, cirrus, cloud, cloud-shadow, and snow bits.
5. Convert source integers to Kelvin using the asset metadata:

```text
Kelvin = DN * 0.00341802 + 149.0
```

6. Convert Kelvin to degrees Celsius by subtracting 273.15.
7. Reject values outside 10–75 °C as invalid safeguards.
8. Calculate the pixelwise median of the 10 masked scenes.
9. Save the number of valid observations for every output pixel.

The resulting raster is median daytime **land surface temperature**. Landsat 8
and 9 cross the equator at approximately 10:00–10:15 local solar time; this is
not daily maximum air temperature.

### 19.7 Sentinel-2 reflectance, mask, and NDVI

For each selected Sentinel-2 scene:

1. Read 10 m red band `B04` and near-infrared band `B08`.
2. Read the 20 m Scene Classification Layer `SCL` and resample it with nearest
   neighbour to the 10 m analysis grid.
3. Read `BOA_QUANTIFICATION_VALUE` and `BOA_ADD_OFFSET` from each scene's
   `product-metadata` XML.
4. Convert stored integers to bottom-of-atmosphere reflectance:

```text
reflectance = (DN + BOA_ADD_OFFSET) / BOA_QUANTIFICATION_VALUE
```

For the selected processing-baseline 05.12 scenes, the verified values are:

```text
BOA_ADD_OFFSET = -1000
BOA_QUANTIFICATION_VALUE = 10000
```

The values are read from metadata rather than hard-coded in the processing
script. This avoids the NDVI bias that would result from ignoring the additive
offset introduced in Sentinel-2 processing baseline 04.00 and later.

5. Retain SCL classes 2, 4, 5, and 6: dark-area pixels, vegetation, bare soil,
   and water.
6. Exclude no-data, saturated/defective, cloud-shadow, unclassified,
   medium/high-probability cloud, cirrus, and snow/ice classes.
7. Calculate:

```text
NDVI = (NIR - red) / (NIR + red)
```

8. Keep values in the physical range -1 to 1.
9. Calculate the pixelwise median of the 10 masked scenes.
10. Save the valid-observation count per pixel.

### 19.8 Building-level environmental context

The source building polygon remains the map object, but raster values are
summarised around its representative point:

- median LST within a 100 m radius;
- median NDVI within a 50 m radius;
- fraction of valid 50 m neighbourhood pixels with NDVI >= 0.3;
- local valid-pixel fractions;
- median number of valid source scenes in each neighbourhood.

The fixed-radius statistics use metric pixel centres in EPSG:32643. They are
neighbourhood indicators, not direct measurements of a building roof or indoor
environment. A 100 m LST radius is intentionally larger than the 30 m thermal
pixel to reduce single-pixel assignment noise.

Relative pilot indicators are also supplied:

- `heat_percentile_pilot`: percentile rank of local LST;
- `greenery_percentile_pilot`: mean of the local NDVI and vegetation-fraction
  percentile ranks;
- `heat_green_priority_pilot`: mean of heat percentile and inverse greenery
  percentile.

These ranks must be recalculated when the boundary changes. They cannot be
compared directly with a future Ahmedabad-wide percentile unless both are
derived against the same reference population and season.

### 19.9 Verified environmental results

All 17,847 buildings passed the minimum three-observation criterion.

| Building-neighbourhood metric | Minimum | P10 | Median | P90 | Maximum |
|---|---:|---:|---:|---:|---:|
| LST, °C within 100 m | 41.679 | 43.695 | 45.004 | 47.284 | 49.641 |
| NDVI within 50 m | 0.028 | 0.074 | 0.132 | 0.238 | 0.652 |
| Vegetated-pixel fraction within 50 m | 0.000 | 0.013 | 0.127 | 0.367 | 1.000 |

Composite raster QA:

| Raster | Shape | Resolution | Valid observations |
|---|---:|---:|---:|
| LST composite | 161 × 150 | 30 m | 8–10 scenes per pixel; median 9 |
| NDVI composite | 481 × 449 | 10 m | 7–10 scenes per pixel; median 9 |

The cold north–south feature in the LST raster and the linear low/variable NDVI
feature are spatially aligned with the Sabarmati River corridor. The eastern
bank and western urban fabric align across the Landsat, Sentinel-2, and building
panels. Visual inspection found no empty panels, tile seams, or CRS offsets.

### 19.10 Outputs

```text
data/derived/navrangpura-building-environment.parquet
data/derived/environment/navrangpura-hot-season-lst-c.tif
data/derived/environment/navrangpura-hot-season-lst-scene-count.tif
data/derived/environment/navrangpura-hot-season-ndvi.tif
data/derived/environment/navrangpura-hot-season-ndvi-scene-count.tif
data/satellite/stac/landsat_items.json
data/satellite/stac/sentinel_items.json
outputs/environment/navrangpura_environment_summary.png
reports/navrangpura_environment_summary.json
```

### 19.11 Interpretation safeguards

- Surface temperature is not air temperature, indoor temperature, thermal
  comfort, health risk, or a person's heat exposure.
- A seasonal multi-scene median is not a heatwave maximum.
- NDVI is not a direct tree-canopy, shade, biodiversity, landscape-quality, or
  public-access measure.
- The NDVI >= 0.3 fraction is an operational vegetation threshold and should be
  sensitivity-tested before academic publication.
- Satellite values reflect sensor resolution, processing, acquisition time,
  atmospheric correction, and cloud masking.
- Keep missing or inadequate observations as `NO DATA`; do not convert them to
  poor environmental scores.

# Part IV — Interactive public interface

## 20. Interactive public website

The Navrangpura pilot now has a complete static MapLibre web application. It is
an **Explore** interface: indicator selection and the map dominate, while a
secondary inspector reveals one building's evidence. It deliberately avoids a
marketing-page hero or decorative dashboard metrics.

### 20.1 Architecture

```text
data/derived/navrangpura-building-environment.parquet
data/derived/planx/outputs/*.gpkg
data/derived/space_syntax/ahmedabad-gandhinagar-space-syntax-clipped.gpkg
    → scripts/build_web_data.py
    → web/public/data/buildings.geojson (14,881,603 bytes)
    → web/public/data/walk-network.geojson (~2.3 MiB)
    → web/public/data/planx-centrality.geojson and other published
      planx-*.geojson layers, space-syntax.geojson, and
      space-syntax-points.geojson
    → web/public/data/metadata.json
    → Vite + MapLibre GL JS application
    → web/dist static production bundle
```

All heavy spatial analysis is precomputed. The browser does not need Python,
PostGIS, a routing engine, a server-side database, or paid runtime APIs.

The pilot uses GeoJSON because 17,847 simplified footprints remain below the
25 MiB individual-file limit of the intended Cloudflare Pages host. A citywide
version should migrate buildings to vector tiles or PMTiles rather than scaling
the single GeoJSON file indefinitely.

### 20.2 Web sources and attribution

- Map renderer: <https://maplibre.org/maplibre-gl-js/docs/>
- MapLibre package: <https://www.npmjs.com/package/maplibre-gl>
- Basemap: OpenFreeMap Liberty style, <https://tiles.openfreemap.org/styles/liberty>
- Basemap project: <https://openfreemap.org/>
- Basemap data attribution: OpenStreetMap contributors and OpenMapTiles

The map includes visible attribution for OpenFreeMap, OpenMapTiles,
OpenStreetMap contributors, Google Open Buildings, QGIS/PlanX space syntax,
and this analysis.

### 20.3 Web project structure

```text
web/
├── index.html
├── package.json
├── package-lock.json
├── vite.config.js
├── public/
│   └── data/
│       ├── buildings.geojson
│       ├── walk-network.geojson
│       ├── planx-centrality.geojson
│       ├── planx-deadends.geojson
│       ├── planx-service-areas.geojson
│       ├── planx-proposed-sites.geojson
│       ├── planx-green-connectivity.geojson
│       ├── planx-heat-risk.geojson
│       ├── planx-routes.geojson
│       ├── planx-access-change.geojson
│       ├── space-syntax.geojson
│       ├── space-syntax-points.geojson
│       └── metadata.json
└── src/
    ├── indicators.js
    ├── indicators.test.js
    ├── main.js
    ├── map_controls.js
    ├── map_controls.test.js
    ├── planx_layers.js
    ├── planx_layers.test.js
    └── styles.css
```

`web/node_modules/`, `web/dist/`, and `web/.vite/` are excluded from Git.

### 20.4 Export browser data

Run from the project root:

```bash
uv run python scripts/build_web_data.py
```

The export script:

1. reads `navrangpura-building-environment.parquet`;
2. keeps only public map properties;
3. shortens browser property names;
4. rounds values to display precision;
5. preserves nulls as `null` rather than converting them to poor values;
6. simplifies geometry by 0.5 m while preserving topology;
7. reprojects to EPSG:4326;
8. joins PlanX building metrics and tessellation-cell area to the stable
   building IDs;
9. transforms selected PlanX network, point, polygon, route, heat-screening,
   scenario, and clipped external space-syntax outputs to compact WGS84
   GeoJSON;
10. writes compact GeoJSON and metadata;
11. records byte size, feature count, and bounds in
   `reports/navrangpura_web_export_summary.json`.

The same command also reads the directed pedestrian graph edges, removes the
duplicated reverse direction of each edge, simplifies the lines by 0.5 m, and
exports the analysis network as `walk-network.geojson`. The browser street
overlay therefore shows the pedestrian network actually used for accessibility,
not a second generic road basemap. It also exports the clipped external PlanX
space-syntax layer with raw `connectivity`, `NC`, `TD`, `MD`, `NAIN`, `CH`, and `NACH` fields for the 400 m and 2,500 m radii; the source OSM network was extracted in August 2026. The source `length_m` field is preserved and `clipped_length_m` records the clipped geometry length.

Verified export:

| Item | Value |
|---|---:|
| Buildings | 17,847 |
| Building GeoJSON size | 14,881,603 bytes |
| Unique pedestrian-network segments | 13,954 |
| Pedestrian-network GeoJSON size | 2,382,718 bytes |
| PlanX prepared-network segments | 14,098 |
| PlanX dead-end points | 2,331 |
| PlanX service-area polygons | 3 |
| PlanX hypothetical civic sites | 3 |
| PlanX green-space polygons | 99 |
| PlanX heat-screening cells | 1,975 |
| PlanX representative routes | 261 |
| PlanX sampled access-change points | 309 |
| Clipped space-syntax segments | 94,723 |
| Space-syntax GeoJSON size | 45,412,269 bytes |
| Space-syntax point GeoJSON size | 40,431,002 bytes |
| Metadata size | 10,096 bytes |
| West/east bounds | 72.5441125 / 72.5847706 |
| South/north bounds | 23.0158865 / 23.0561342 |

### 20.5 Install and run locally

```bash
cd web
npm install
npm test
npm run dev -- --port 4173
```

Open:

```text
http://127.0.0.1:4173/
```

The interface includes:

- seventeen switchable building indicators, including four PlanX building-form
  measures;
- eight nearest-destination walking-time layers;
- 15-minute category coverage;
- land-surface temperature, NDVI, vegetation fraction, and heat–green priority;
- a dynamic legend and pilot median;
- building-layer opacity, no-data, and background-map controls;
- a background-map switch that hides every OpenFreeMap layer—including its
  3D buildings—while keeping the scanner footprints and interface visible;
- a separately switchable pedestrian-network overlay, enabled by default,
  showing the buffered OSM walking graph used for the accessibility model;
- nine independent PlanX overlay controls plus one space-syntax dropdown,
  all disabled by default: network
  centrality, critical links, dead ends, civic service areas, hypothetical
  civic sites, green connectivity, heat-risk proxy, representative OD routes,
  and sampled scenario access change; the space-syntax dropdown exposes
  connectivity plus NC, TD, MD, NAIN, CH, and NACH at 400 m and 2,500 m;
- click-to-inspect building details;
- explicit source, period, method, and interpretation text;
- a method-and-sources dialog;
- responsive sidebar/inspector behaviour;
- keyboard focus states and reduced-motion support.

### 20.6 Build the production site

```bash
cd web
npm audit --audit-level=low
npm test
npm run build
```

Verified results:

```text
npm audit: 0 vulnerabilities
Vitest: 11 passed
Vite production build: passed
```

The static site is written to:

```text
web/dist/
```

The main production bundle is about 1.06 MB before gzip and 290 KB after gzip.
The MapLibre worker is emitted as a separate 508 KB module. The building
GeoJSON remains the dominant transfer at approximately 14.9 MB before HTTP
compression.

MapLibre GL JS was upgraded to version 6.14.0 after `npm audit` identified a
critical sanitizer vulnerability affecting versions through 6.4.0. The final
dependency audit reports zero known vulnerabilities.

### 20.7 Interaction and visual QA

The site was opened in a real browser and checked at a 1280 × 577 desktop
viewport. Verified states:

- basemap and 17,847 colored footprints render;
- indicator switching updates title, context, median, legend, and fill colors;
- the LST layer displays a 45.00 °C pilot median;
- selecting a footprint opens the inspector with morphology, eight walking
  times, heat, NDVI, vegetation, and source/method notes;
- the method dialog opens and scrolls correctly;
- hidden inspector content no longer creates horizontal page overflow;
- map worker loads correctly under Vite and in the production build;
- turning the background map off hides all 111 initially visible basemap
  layers while preserving the four scanner footprint/interaction layers;
- turning it back on restores each basemap layer's original visibility rather
  than forcing normally hidden layers to appear;
- the separate pedestrian-network layer loads 13,954 deduplicated line
  segments, remains visible when the background map is hidden, and can be
  switched off independently;
- all nine original PlanX overlays load from separate analytical sources, switch
  independently, remain visible with the basemap hidden, and start hidden to
  prevent visual clutter;
- the clipped external space-syntax source loads 94,723 segments through one
  dropdown. Selecting a documented field activates the shared line layer;
  choosing `Off` hides it. Raw values remain unnormalised in the browser;
- the PlanX building-form indicators update the thematic fill, legend, median,
  and selected-building method text;
- enabling many PlanX overlays compacts the on-map status to an active-count
  message rather than covering the map with a long layer list;
- browser QA confirmed the nine PlanX controls and the space-syntax dropdown
  load independently, and no horizontal overflow was introduced;
- no JavaScript or browser-console errors remain after a clean reload.

The final design uses an IBM Carbon-inspired visual grammar: IBM Plex type,
rectangular controls, one blue interface accent, flat gray layers, and no card
shadows or decorative gradients. Thematic map palettes remain multicolour where
the data require sequential or diverging scales.

### 20.8 Static deployment

The production site is ready for a free static host. It has not yet been
published because this project session has no configured Git remote,
Cloudflare credentials, or Wrangler login.

Direct Cloudflare Pages deployment after authentication:

```bash
npm --prefix web run build
npx wrangler pages deploy web/dist --project-name ahmedabad-urban-scanner
```

For a Git-connected Cloudflare Pages project:

```text
Root directory: web
Build command: npm ci && npm run build
Build output directory: dist
```

The generated `web/public/data/` files must be present in the repository or
restored during the build. After deployment, verify the public URL, map worker,
GeoJSON response, attribution, indicator switching, inspector, and mobile layout
before announcing the site.

# Part V — PlanX pilot

## 21. Reproducible PlanX integration

The Navrangpura pilot uses the official PlanX QGIS Processing provider rather
than locally invented equivalents. The exact audited sources are pinned to:

| Component | Commit |
|---|---|
| PlanX QGIS plugin | `d24233790b0b93af25a5a9024c078f1ec04089fc` |
| PlanX SDK audit reference | `c7a69131f130bdc2387bf9e8bcff4f425a60381a` |

The pinned PlanX QGIS plugin includes the GNU General Public License version 3.
The separately audited PlanX SDK includes the MIT License. The scanner executes
the GPL-licensed plugin as an external QGIS Processing runtime and publishes
derived spatial results, not a browser copy of the plugin. Source-data
attribution and licence obligations remain independently applicable to Open
Buildings, OpenStreetMap, Landsat, and Sentinel-2 inputs.

Verified runtime:

```text
QGIS 3.42.1
/Applications/QGIS.app/Contents/MacOS/bin/qgis_process
.qgis/profiles/default/python/plugins/planx
```

The project-local `.qgis/` profile is ignored by Git. The runner validates the
plugin commit and Processing catalog before executing anything.

### 21.1 Build the projected PlanX input package

```bash
uv run python scripts/build_planx_inputs.py
```

Outputs:

```text
data/derived/planx/navrangpura-planx-inputs.gpkg
data/derived/planx/navrangpura-planx-inputs.json
```

The EPSG:32643 package contains the prepared source layers for PlanX, including
13,768 undirected input edges, 17,847 buildings, 17,847 centroids, 852 OSM
destinations split into eight category layers, 99 green spaces, 309
deterministically thinned representative origins, 936 candidate sites, eight
civic facilities, a bounded criticality-origin subset, and the study polygon.

The representative origins and candidate sites are computational sampling
devices, not population estimates. Their `demand_weight` is equal-weighted;
there is no resident-level population or socioeconomic inference.

### 21.2 Run and resume the pilot

Dry-run all default-enabled stages:

```bash
uv run python scripts/run_planx_pilot.py --dry-run
```

Run them while reusing verified outputs:

```bash
uv run python scripts/run_planx_pilot.py --reuse
```

Run one named stage:

```bash
uv run python scripts/run_planx_pilot.py --only networkcentrality --reuse
```

Every invocation writes a JSON record under
`data/derived/planx/logs/`, including the exact safe argument array, return
code, stdout, stderr, skipped outputs, and pinned plugin commit.

### 21.3 Verified pilot status

All default-enabled pilot stages have real outputs. Selected verified counts:

| Output | Count |
|---|---:|
| Prepared PlanX network segments | 14,098 |
| Network-centrality nodes | 10,576 |
| Building metrics | 17,847 |
| Morphological tessellation cells | 17,847 |
| Dead-end points | 2,331 |
| Nearest-facility demand origins | 309 |
| Green-access demand origins | 309 |
| Link-criticality segments | 14,098 |
| OD matrix rows | 87,394 |
| OD routes | 261 |
| Baseline multi-amenity origins | 309 |
| Facility-location candidates | 936 |
| Service-area polygons | 3 |

Other completed outputs include street morphology, green connectivity, the
100 m PlanX heat-risk screening grid, facility-location assignments, baseline
and intervention access scores, scenario snapshots, scenario comparison,
scenario ranking, and an HTML performance report.

The facility-location experiment adds three hypothetical civic facilities to
the eight mapped OSM civic facilities. It is a reproducible scenario test, not
a siting recommendation: candidate suitability, land ownership, capacity,
cost, demand, and implementation feasibility have not been validated.

The scenario score changed from a baseline mean access score of **79.61** to
**83.74** after adding the three hypothetical civic sites. Full-category access
among the 309 representative origins changed from **25.24%** to **42.07%**.
These are pilot-relative model results dependent on the current OSM inventory,
equal origin weights, and PlanX parameters.

### 21.4 Space syntax deferred

PlanX segment angular space syntax was started with radii `400,800,n` on the
14,098-segment prepared network. The exact global calculation remained active
for more than 30 minutes and was stopped at the user's request before an output
GeoPackage was written. It is now **disabled by default** in the runner, so a
normal full run will not restart it. It remains explicitly available with:

```bash
uv run python scripts/run_planx_pilot.py --only spacesyntax --reuse
```

For citywide work, the user has an existing GIS layer containing completed
space-syntax analysis. Before incorporation, verify its source software and
version, analysis radii, segment construction, CRS, field definitions, network
date/extent, topology, and licence. Do not merge it merely because fields have
similar names.

### 21.4.1 Audited external PlanX space-syntax layer

The user supplied `data/external/space-syntax/space-syntax.gpkg`, layer
`segment_analysis`, and reported that it was generated in QGIS with the PlanX
QGIS Processing provider. A preliminary structural and spatial audit is recorded
in:

```text
reports/space_syntax_audit.md
```

The layer contains 139,616 valid EPSG:32643 LineStrings with unique `seg_id`
values, no null syntax fields among the audited PlanX-style metrics, and no
declared-length mismatches against geometry length. The user confirms that the
`400` and `2500` suffixes represent PlanX distance radii of 400 m and 2,500 m.
The source network is reported as OpenStreetMap-
derived and was extracted in August 2026. The layer was produced with the same
PlanX setup used for the previous project runs; the shared plugin is pinned in
this project to commit `d24233790b0b93af25a5a9024c078f1ec04089fc`.

A field dictionary records what each field measures, its units, and whether it
is a count, distance, ratio, or normalized score. Normalisation records any
transformation used to make values comparable, such as a percentile, z-score,
or range rescaling. The exact field dictionary, normalisation, and topology
settings remain unverified.

The selected boundary is the user-defined
`data/external/boundary/ahmedabad-gandhinagar-black-line.gpkg` polygon. It is
recorded as approximate screenshot digitisation, not an official AMC boundary.
94,651 segments intersect it and 94,229 are fully within it. The source layer
extends beyond the boundary; the source was not modified. The clipped derivative
is published only for the static study-area webpage, not as a citywide result.

The selected assignment rule is to retain every segment intersecting the study
polygon, clip its geometry to the boundary, and remove segments wholly outside
it. The clipped derivative is written to
`data/derived/space_syntax/ahmedabad-gandhinagar-space-syntax-clipped.gpkg`.
Original PlanX attributes and source `length_m` values are preserved, while
`clipped_length_m` records the post-clip geometry length. The PlanX analysis was
not rerun.

Rebuild the clipped derivative with:

```bash
uv run python scripts/build_space_syntax_study_area.py
```

The external layer is therefore **structurally usable with partially confirmed
provenance**. Before publication or citywide integration, record the PlanX
algorithm parameters, field dictionary, normalisation, segment construction,
angular settings, topology/barrier treatment, and licence. Any publication must
attribute
OpenStreetMap contributors and include the OpenStreetMap copyright/licensing
reference, while identifying QGIS and the PlanX QGIS Processing provider. This
does not authorise citywide processing and does not replace the required audit
of a genuine AMC boundary.

### 21.5 Interpretation limits and visible scope classes

The web export does not treat every published layer as the same kind of evidence.
Every visible control, legend, active-layer summary, and report must preserve these
scope classes:

| Visible class | Meaning |
|---|---|
| **Full-study current** | Product covers the current Ahmedabad–Gandhinagar study boundary, subject to its method-specific caveat. |
| **Bounded current-study subset** | Product is limited to a documented tile or subset and is not a full-study result. Historical bounded artifacts remain archived in `data/derived`; they are not the current centrality publication. |
| **Sampled current-study** | Model output uses sampled origins, facilities, or destinations. |
| **Current-study morphology proxy** | Screening/modelled product, not direct observation. Heat-risk is based on 30,000 buildings and 35 green spaces; it is not observed heat. |
| **Archived/historical pilot** | Retained from an earlier workflow and not a current full-study result. Hypothetical civic sites are an archived historical scenario, not a siting recommendation. |
| **Contextual external / supplied external** | Context or externally supplied data, not a rerun or validated analytical finding for this study. |
| **Unverified** | Published for inspection but not validated for this study; it must not be treated as verified evidence. |

OSM destinations and green spaces are not complete official inventories. Network
centrality and criticality describe the modelled graph, not observed pedestrian
volume, safety, footpath quality, or street importance. OD and route outputs use
representative origins to control cardinality. Service areas use network distance
breaks of 400, 800, and 1,200 m, corresponding to 5, 10, and 15 minutes at 80
m/min. Missing data must remain `NO DATA`; it must not be converted to a poor score.

### 21.6 Selective browser publication

PlanX continues to run only in QGIS/headless preprocessing. The browser loads
static exports and does not execute PlanX algorithms. `scripts/build_web_data.py`
publishes only outputs that are interpretable at pilot scale:

| Browser product | Published meaning |
|---|---|
| Building compactness, convexity, elongation | PlanX footprint-form measures joined by stable building ID |
| Morphological cell area | Tessellation-cell area joined to the corresponding building |
| Network centrality | 135,115 published edges from the verified full prepared network; PlanX `networkcentrality` used radius 0, 500 sampled sources, and `cost_fwd`, so betweenness is not an all-pairs metric |
| Critical links | Sampled civic-access disruption screen using 198 origins and 10 facilities; only 9 positive links; no matching full-study execution log retained |
| Dead ends | Degree-one nodes and branch diagnostics in the archived prepared network |
| Civic service areas | Archived/historical network catchments at 400, 800, and 1,200 m |
| Proposed civic sites | Archived historical hypothetical three-facility scenario; not a siting recommendation |
| Green connectivity | Archived/historical OSM green-space components using a 100 m connection threshold |
| PlanX heat-risk morphology proxy | Current-study screening grid based on 30,000 buildings and 35 green spaces; not observed heat |
| Representative OD routes | Nearest mapped destination routes for sampled origins |
| Scenario access change | Baseline-to-intervention score change for 309 sampled origins |
| Space syntax dropdown | Raw connectivity, edge betweenness, mean closeness, mean straightness, plus NC, TD, MD, NAIN, CH, and NACH at 400 m and 2,500 m from the clipped user-supplied PlanX network |

The nine PlanX overlay controls remain independent and disabled by default. The
space-syntax dropdown is also off by default and activates one selected field at
a time. All remain visible when the contextual basemap is hidden because their
source and layer state are separate from OpenFreeMap. Multiple non-space-syntax
overlays may be combined for comparison; when more than three are active, the
map reports only the active count to avoid covering the evidence with a long
label.

The heat-risk morphology proxy is rendered from the published `heat_risk`
field using preprocessing-derived interior quantile thresholds and the
sequential Yellow–Orange–Red palette (`#ffffcc` through `#800026`). Its legend
shows the actual numeric ranges and the no-data color remains neutral gray.
The proxy is based on 30,000 buildings and 35 green spaces; it is not observed
heat or climate risk. Missing values are preserved as missing and are not
converted to a low-risk score.

The browser changes only symbology; it does not renormalise, recompute, or
alter the PlanX values. The compact control note updates to the selected
field's actual method and effective class count.

No local pilot space-syntax calculation was rerun. The audited external layer
is published as a raw-field dropdown for the selected study boundary. Its
topology and field dictionary remain unresolved, so it must not be interpreted
as a fully documented citywide space-syntax result. Any future citywide result
must pass the provenance and compatibility checks in Section 21.4 before it
can be added.

# Part VI — Quality assurance

## 22. Run all checks

```bash
uv run --group dev pytest tests/ -q
uv run python scripts/audit_inputs.py
uv run python scripts/build_pilot_buildings.py
uv run python scripts/build_accessibility.py --reuse
uv run python scripts/build_environment.py --reuse
uv run python scripts/build_study_area_extent.py
uv run python scripts/build_web_data.py
npm --prefix web test
npm --prefix web run build
git diff --check
```

Inspect both map files visually:

```text
outputs/navrangpura_open_buildings_v3_qa.png
outputs/accessibility/navrangpura_accessibility_summary.png
outputs/environment/navrangpura_environment_summary.png
```

A successful command alone is not proof of a valid map. Check for blank panels,
extent errors, extreme geometries, unreadable legends, and false claims.

## 23. Reproduction from a fresh checkout

1. Clone or copy the repository.
2. Install uv.
3. Run `uv sync --group dev`.
4. Download Open Buildings shard `395f` using Section 7.
5. Run `uv run python scripts/build_pilot_buildings.py`.
6. Run `uv run python scripts/build_accessibility.py` to acquire the current
   OSM snapshot, or restore the saved GraphML/GeoPackage and use `--reuse` for
   exact snapshot parity.
7. Run `uv run python scripts/build_environment.py` to query the recorded
   Landsat/Sentinel-2 period, or restore the saved composites and use `--reuse`.
8. Run `uv run python scripts/build_web_data.py`.
9. Run `npm --prefix web install`, `npm --prefix web test`, and
   `npm --prefix web run build`.
10. Run all Python tests.
11. Inspect the QA maps and interactive website.
12. Compare JSON summaries with the verified counts in this handbook.

## 24. Current data reset and GTFS audit

The web publication has been reset to the user-defined Ahmedabad–Gandhinagar
study boundary. The Navrangpura-derived analytical exports, pedestrian-network
export, and PlanX web GeoJSON files are no longer published. The current
building source is Google Research Open Buildings V3 polygon data from S2
level-6 tiles `395d` and `395f`, filtered by the study boundary. The current
static export contains 1,077,523 footprints.

The supplied `data/external/gtfs_compat.zip` was audited before publication.
It contains 3 agencies, 570 routes, 13,315 trips, 860 shapes, 6,737 stops,
and 580,293 stop-time rows. All routes use GTFS `route_type=3`. Referential
checks found 216 trips whose `shape_id` is absent from `shapes.txt`; route,
service, trip, and stop references otherwise resolved. The feed metadata names
BLRTransit and gives a feed period of August 13, 2026 to February 9, 2027,
while the agencies are Ahmedabad Municipal Transport Services, Ahmedabad
Janmarg Limited, and Gandhinagar Transport Services Limited. This provenance
inconsistency is retained as a warning and must be resolved before using the
feed for analysis.

GTFS route shapes, stops, and stop-level service intensity are separate web
layers, all off by default, with independent controls. Service intensity is
derived directly from `stop_times.txt` and `trips.txt`, rather than from route
shape availability, so the 216 trips with missing shapes still contribute their
scheduled stop departures.

### 24.1 GTFS stop service intensity

For stop $i$, service intensity is:

$$
S_i = \sum_{r=1}^{n} F_{ir}
$$

where $F_{ir}$ is the number of scheduled departures of route $r$ at stop $i$
during the specified period. The web map publishes four mutually exclusive
views: **whole service day**, **morning peak from 08:00 inclusive to 10:00
exclusive**, **evening peak from 17:00 inclusive to 19:00 exclusive**, and
**average departures per hour**. Whole-day counting includes GTFS extended-hour
times after 24:00. The hourly value divides each stop's whole-day departures by
the feed's observed 19.583-hour service span, from 04:55 to 24:30. Each view uses
its own data-derived quantile colors. The GeoJSON retains `routes_served` as a
separate attribute. Route count is not treated as a frequency measure: several
infrequent routes can provide less service than a small number of high-frequency
routes.

Verified feed result:

| Measure | Result |
|---|---:|
| Stops retained | 6,737 |
| Stops with at least one whole-day departure | 6,737 |
| Scheduled stop departures, whole service day | 580,293 |
| Scheduled stop departures, 08:00–10:00 | 80,648 |
| Scheduled stop departures, 17:00–19:00 | 79,715 |
| Median whole-day departures per stop | 39 |
| 90th percentile whole-day departures per stop | 211 |
| Maximum whole-day departures at one stop | 1,504 |
| Median average departures per hour | 1.99 |

The output is `web/public/data/gtfs-service-intensity.geojson`. The feed's
agency/provenance inconsistency remains unresolved, so this is scheduled-service
context rather than verified current operations, reliability, capacity, or
observed ridership.

### 24.2 Interactive route-reach walking catchment

The web map also publishes an interactive **15-minute route-reach walking
catchment**. After the control is enabled, clicking a GTFS stop performs these
steps:

1. retain the selected stop and add any other GTFS stops reachable within a
   five-minute walk on the prepared street network;
2. identify every GTFS route serving any of those seed stops;
3. collect every stop served by those routes; and
4. union the 15-minute walking catchments from each collected route stop.

Walking uses the 135,119-edge full-study prepared network in EPSG:32643 at
4.8 km/h. Stops and 250 m destination-grid cells are snapped to the network
within 400 m. Network shortest-path distance, rather than straight-line
distance, determines both the five-minute nearby-stop relationship and the
15-minute catchment. All 5,403 GTFS stops inside the study boundary fall within
the 400 m network-snap tolerance. The compact browser model contains 6,737 feed
stops, 564 unique route IDs, 33,374 directed nearby-stop links, 7,677 linked
destination cells, and 179,060 stop-to-cell walking links; its generated JSON is
approximately 5.20 MB.

This is deliberately **not** described as a total public-transport travel-time
isochrone. It does not constrain waiting time, in-vehicle time, service period,
or the time needed to traverse a bus route. It shows the urban area lying within
a 15-minute street-network walk of any stop on routes accessible from the
selected stop or a stop within a five-minute walk. The output model is
`web/public/data/transit-isochrone-model.json`.

The selected-stop inspector reports only the routes that directly serve the
clicked stop; routes introduced through the five-minute nearby-stop expansion
remain part of the wider catchment but are not presented as direct services.
For each direct route, the model stores scheduled departures in 21 clock-hour
buckets from 04:00 through 24:00. GTFS extended times such as 24:30 remain in
the hour-24 bucket. Average scheduled headway is the mean interval between
consecutive unique departure times over the service day; routes with fewer
than two unique departures report `Headway unavailable`.

The panel also reports two separate approximate areas. The green **direct
15-minute walk** is calculated from cells linked within 15 minutes of the
selected stop. The blue **route-reach catchment** uses the complete route-stop
expansion described above. Each value sums the projected `area_m2` of unique
selected cells and divides by 1,000,000; the values are not added because the
green area normally overlaps the blue area. A complete 250 m cell contributes
0.0625 km², while clipped boundary cells contribute their actual projected
area.

Directly serving route shapes are highlighted with deterministic colors shared
by the map, route list, and scheduled-departures graph. Stops with eight or
fewer direct routes show individual graph lines by default. Stops with more
than eight show one combined total-scheduled-departures line until a route is
selected; clicking a route isolates its line and geometry, and the reset action
restores all direct routes. All routes remain in the list even when no usable
shape exists; the current generated contract contains 564 routes, including 10
with no usable geometry, and `gtfs-shapes.geojson` contains 876 route-linked
shape features. Closing the inspector preserves the selected catchments;
turning the catchment layer off clears the selection, graph, highlights, and
dynamic cell sources.

The route-reach interaction is the first control in the sidebar, above the
building indicators. A shared opacity slider controls both blue and green
catchment fills, with a 35% default, while route lines and stop symbols remain
opaque. Non-seed route stops render as hollow purple circles to reduce map
clutter. The scheduled-service graph includes labelled service-hour and
scheduled-departures-per-hour axes with numeric ticks.

These panel values describe scheduled supply and route-linked walking reach.
They do not verify actual operations, reliability, capacity, ridership, waiting
time, or total public-transport journey time.

Public-interest POIs are published in one file, `web/public/data/pois.geojson`,
from an audited OpenStreetMap Overpass query. The public export is deliberately
restricted to the two retained categories: **676 parks and recreation features**
and **90 schools/universities**, for 766 points in total. Both categories have
independent off-by-default checkboxes and read the same filtered source file.
Other queried POI categories remain documented in the audit but are not
published because their mapped inventory is incomplete. The query, raw response,
category mapping, timestamp, and limitations are
recorded in `reports/poi_audit.md`. OSM attribution is required; these are
mapped OSM features rather than a complete official inventory.

The 390,304,730-byte building GeoJSON is no longer loaded by the browser. It
has been converted to `web/public/data/buildings.pmtiles` using Tippecanoe and
is read through the PMTiles MapLibre protocol as a vector source. The active
web data directory is now approximately 63 MB, including the 59,183,928-byte
PMTiles archive and the 302,351-byte POI GeoJSON. The original GeoJSON remains
an intermediate generated artifact only; after regenerating it, repeat the
documented Tippecanoe/PMTiles conversion before serving the web map.

The Google Open Buildings Temporal manifest was checked for 2016, 2020, and
2023 using the official public manifest scheme. The manifests were available,
but the intersecting GeoTIFF object URLs returned HTTP 404 during acquisition;
no fabricated temporal files were added. Reattempt the temporal download when
Google restores or replaces those public objects, or provide an authenticated
Earth Engine/GCS access route.

## 24.2 Current full-study PlanX building form
The current PlanX full-study building-metrics output covers all **1,077,523** selected Open Buildings V3 footprints. The reproducible input is `data/derived/planx/ahmedabad-gandhinagar-full-buildings-inputs.gpkg`, the metrics output is `data/derived/planx/ahmedabad-gandhinagar-full-building-outputs/building_metrics.gpkg`, and the latest successful run is `data/derived/planx/ahmedabad-gandhinagar-full-building-logs/run_20261018T005947Z.json`. The run's `buildingmetrics` return code is 0. Full-study report files are `reports/ahmedabad_gandhinagar_planx_full_building_form_audit.json` and `.md`.

The current web export publishes full-study footprint area and PlanX compactness, convexity, and elongation. Full-study tessellation is absent, so `planx_cell_m2` is not claimed or published. The report retains observed convexity and rectangularity values above 1.0, identifies their small positive excess as floating-point numerical overshoot of bounded ratios, and does not clip or normalize source values.

## 25. PlanX height-dependent analyses

The current PlanX buildings input covers 1,077,523 Open Buildings V3 footprints but has no height or floor-count field. Open Buildings V3 does not provide height. The saved OSM extract has sparse `height` and `building:levels` tags, but they are not joined to the exact PlanX footprints and therefore are not used as observed heights.

The exact stage matrix, source coverage, missing prerequisites, and reproducible commands are recorded in:

```text
reports/ahmedabad_gandhinagar_planx_height_audit.md
reports/ahmedabad_gandhinagar_planx_height_audit.json
```

Height-aware stages remain blocked until a verified numeric `height_m` field is joined to the current buildings layer and a terrain baseline is available for true DSM analyses. The independent 2-D `isovistfield` stage was run as a new Navrangpura pilot at 25 m cells and 36 rays; it produced 24,858 valid points and does not use building height. Its output is under `data/derived/planx/height-audit-pilot/` and is not a replacement for any prior output.

## 26. Change log

### 2026-10-17

- Created the dedicated Ahmedabad Urban Scanner project and Git branch.
- Configured the Navrangpura pilot and EPSG:32643 analysis CRS.
- Replaced Overture footprints with Google Open Buildings V3 at the user's
  request.
- Downloaded and verified S2 level-6 shard `395f`.
- Applied the level-4 cell `395` 85% precision threshold of 0.802.
- Produced and validated 17,847 pilot building footprints.
- Downloaded a buffered OSM walk network and eight destination categories.
- Produced building-level nearest walking times and 5/10/15-minute counts.
- Added automated tests for building preparation, S2 selection, chunked loading,
  destination classification, OSM identifiers, and network calculations.
- Queried and preserved 10 Landsat 8/9 and 10 Sentinel-2 hot-season STAC items.
- Produced cloud-masked median LST and NDVI composites with observation-count
  rasters and building-level 100 m/50 m neighbourhood indicators.
- Added tests for Landsat scaling/QA, Sentinel-2 reflectance/SCL masking, NDVI,
  and metric circular raster summaries.
- Exported a 17,847-feature browser GeoJSON with explicit no-data preservation.
- Built and browser-tested the static MapLibre urban scanner with thirteen
  indicators, dynamic legends, a building inspector, and a method dialog.
- Upgraded to MapLibre GL JS 6.14.0 and verified `npm audit` reports zero known
  vulnerabilities.
- Added an accessible background-map switch that removes streets, labels,
  water, and OpenFreeMap 3D buildings without hiding scanner footprints; added
  two unit tests for hide-and-restore layer visibility.
- Exported the accessibility study's deduplicated OSM pedestrian network and
  added it as an independently switchable street-line overlay in the web map.
- Pinned and installed the official PlanX plugin in an ignored local QGIS
  profile, built a validated projected input package, and completed every
  default-enabled high-readiness PlanX pilot stage.
- Deferred exact segment angular space syntax after a more-than-30-minute pilot
  run; normal runs now skip it unless it is selected explicitly.
- Recorded the existing citywide GIS space-syntax layer as a future candidate
  source requiring provenance, parameter, topology, CRS, and licence checks.
- Joined verified PlanX building-form results into the 17,847 browser
  footprints and published eight compact PlanX analytical GeoJSON files.
- Added seventeen building indicators and nine independently switchable PlanX
  overlays to the local MapLibre scanner, with explicit scenario and heat-proxy
  qualifications, basemap-independent visibility, tests, and browser QA.
- Digitised the user's black-line Ahmedabad–Gandhinagar scale-up extent into
  GeoJSON, GeoPackage, zipped Shapefile, bbox, TOML, metadata, and a screenshot
  QA preview; retained its approximate screenshot-derived status explicitly.
- Created this handbook as the authoritative living reproduction guide.

## Priority 3 classification and symbology

### Priority 3 web-loading contract

Optional analytical overlays are registered with MapLibre only when the user first activates them. Initial map loading registers the building PMTiles source and declared base-style layers, but not the large GeoJSON or raster overlay sources. Space-syntax line and point sources are likewise registered only when the selector changes from `Off`. Once registered, a source remains available for subsequent toggles during that browser session.

The building-height fine manifest distinguishes the 16 upstream source raster tiles (`source_raster_tile_count`) from the generated browser tile inventory (`published_web_tile_count`). The latter must equal the number of entries in `tiles`; validation rejects a mismatched count. This avoids presenting upstream acquisition tiles and published WebP map tiles as the same quantity.

Network and centrality betweenness, link criticality, and every selectable
space-syntax field are classified from the values actually written to the
browser GeoJSON. Varying continuous fields use deterministic seven-class
quantiles with duplicate thresholds removed; thresholds exclude the minimum
(base) class. Centrality and most space-syntax fields use Viridis. Strongly
right-tailed total-depth/choice fields (`td_*`, `ch_*`, `nach_*`) use Inferno.

Link criticality is exact categorical/binary when its published values are
binary, and connectivity is represented by exact categories. Constant fields
are explicitly marked as constant with no variation rather than receiving a
misleading graduated ramp. Raw published values remain unchanged. Missing or
null values render neutral gray and are never assigned to the lowest class.

The exported metadata stores these decisions under `overlay_classifications`,
including method, property, thresholds, class count, counts, zero count,
unique count, range, palette, and note. The existing space-syntax control
shows a concise classification/provenance note; the full numeric legend UI is
not part of this priority.

Supplied space-syntax remains an external clipped layer and was not rerun.
Closeness export precision was raised from three decimals to twelve decimal
places so small nonzero source values survive and classification breaks match
browser values exactly.

## 27. Local Area Profile

The static web application includes a draggable **Local Area Profile** for
400 m, 800 m, and 1,200 m radii. Full analysis runs when the circle is placed,
dragged, or its radius changes; movement preview remains lightweight. The
interactive dashboard and A2/A3 landscape print sheet consume the same
`local-area-profile.v1` normalized result. The print renderer does not
recalculate analytical values.

### 27.1 Analytical publication

The renderer PMTiles remain separate from the lossless analytical publication:

```text
web/public/data/buildings.pmtiles              # display only
web/public/data/local-profile/manifest.json    # analytical manifest
web/public/data/local-profile/*.fgb            # range-queryable vectors
web/public/data/local-profile/*.tif            # window-read rasters
```

Rebuild the analytical assets atomically with:

```bash
uv run python scripts/build_local_profile_assets.py
```

The publication contains 12 files totalling **544,421,907 bytes**. Its main
feature counts are:

| Asset | Count |
|---|---:|
| Buildings | 1,077,523 |
| Prepared streets | 135,115 |
| Network-centrality edges | 135,115 |
| Supplied space-syntax features | 94,723 |
| Heat-risk polygons | 49,422 |
| Flood-risk polygons | 7,020 |
| GTFS stops | 6,737 |
| Approved POIs | 766 (676 parks; 90 schools/universities) |

`buildings.fgb` preserves source polygons and fields and adds finite
`centroid_x` and `centroid_y` values calculated from the full source geometry
in EPSG:32643. It contains 1,077,523 records, is 357,613,072 bytes, and has
SHA-256
`1a1306762081db8d149d95ba9c10f39c7dbb08dbd14bad8a29ba7fb46c022b47`.
The display archive `buildings.pmtiles` remains 144,950,089 bytes with SHA-256
`fa7dfc5f79aa7a27295ed84dba4e0a5fb1101cd6b367bf3b70ad370ca9220fcf`.
`web/public/data/buildings.geojson` must remain absent.

### 27.2 Metric rules

- The analysis CRS is EPSG:32643. Browser input is longitude/latitude and is
  transformed before bounding-box reads or distance calculations.
- Circle and TPS building analytics use the published `buildingLocations`
  point asset with boundary-inclusive membership. Circle membership includes a
  point exactly on the selected radius. Central Zone records contribute to
  counts only; provisional height, stored area, derived volume and categorical
  SUHI use valid enriched records and report enriched denominators.
- Point mode does not report polygon building count, exact footprint-union
  coverage, footprint-area distributions or footprint shape metrics.
  `buildingLocations` is the sole production Buildings asset; if it is absent,
  the profile is explicitly unavailable and no polygon fallback is requested.
- Street topology uses authoritative `u`/`v` or source/target identifiers;
  clip-created boundary points are not counted as graph nodes.
- Space-syntax and centrality values are clipped spatially and summarized with
  clipped line length as the weight.
- Raster summaries use pixel-center circle inclusion and report mean, median,
  maximum, standard deviation, fixed-bin counts, and valid-data coverage.
  Surface-temperature distributions use 1 °C intervals from 30 °C through
  48 °C, with an explicit `Outside 30–48` category so valid observations are
  not silently discarded. LST and NDVI retain the one-scene caveat; 2023 height
  is modelled. Nodata, including height `-99` and environmental `-9999`, is
  excluded rather than converted to zero.
- Flood-risk polygons are clipped to the metric profile circle and unioned
  within each original `uf_risk` class before area is measured, preventing
  same-class overlap from being counted twice. The source has no Low class, so
  Low is reported as **Unavailable**, never as zero.
- Transit selects stops inside the profile, then unique directly serving
  routes, all stops on those routes, and unique existing 15-minute route-reach
  cells. Connected area sums projected cell `area_m2`. It describes scheduled
  supply and route-linked reach, not observed operations, reliability,
  ridership, capacity, or complete journey time.
- Parks and education use the approved 766 representative points. OSM-derived
  counts are mapped features, not a complete official inventory.
- Every section carries availability, provenance, valid denominator where
  applicable, and caveats. Optional-source failures remain explicit and do not
  reject the entire profile.

The profile presentation uses seven reader-facing sections: Overview,
Buildings, Streets/connectivity, Space syntax/centrality, Environment, Public
transport, and Parks and schools. Availability and Methods remain part of the
normalized analytical contract where supplied, but are intentionally omitted
from the inspector and print report. Buildings and environmental distributions
use vertical columns; aggregate street values remain KPIs; network weighted
means, transit reach, and parks/schools use compact semantic tables. The print
report includes LST, NDVI, and flood-risk area distributions, reports transit
route arrays as a route count, and uses a three-column environmental composition
so both A2 and A3 landscape sheets remain bounded.

### 27.3 Static-browser safeguards

FlatGeobuf reads use `{ rect: { minX, minY, maxX, maxY } }`, decoded-candidate
and estimated-memory guardrails, and cancellation checks around decoding and
assembly. Polygon unions are reduced in bounded chunks rather than passed as an
unbounded variadic argument. Profile requests have request identifiers,
timeouts, cancellation, and stale-result suppression. GeoTIFF URLs are resolved
relative to the manifest and read by window rather than intentionally decoded
as whole rasters.

At the fixed audit center `[72.5765716, 23.0921374]`, browser results match the
independent Python/Shapely baseline exactly:

| Radius | Centroid-selected buildings | Clipped footprint union |
|---:|---:|---:|
| 400 m | 1,064 | 111,636.25 m² |
| 800 m | 2,669 | 320,703.37 m² |
| 1,200 m | 8,862 | 971,959.11 m² |

Observed local vector-query runtimes were approximately 0.2 s, 0.6 s, and
2.4 s respectively; network, device, and cache conditions will change these
values. The FlatGeobuf browser API does not expose exact transferred-byte totals,
so decoded-byte diagnostics are recorded while request-byte status remains
explicitly unavailable rather than inferred.

### 27.4 Verification and rerun

Run the complete release gate from the project root:

```bash
uv run --group dev pytest tests/ -q
cd web
npm run dev -- --port 5173
LOCAL_PROFILE_BASE_URL=http://127.0.0.1:5173 npm test
npm run build
git diff --check
```

The browser gate must fresh-load the map, place all three radii at the audit
center, inspect readable dashboard sections, confirm the exact table above,
check the console, and inspect both A2 and A3 landscape print previews. The
print sheet is deliberately monochrome-safe through grayscale, hatching, dot
density, line weight, and explicit no-data labels; A2 is preferred for
legibility.

The final 2026-10-21 release gate passed **129 Python tests** and **170 frontend
tests across 25 files**, followed by a successful Vite production build and
clean `git diff --check`. The built `web/dist/` contains 2,383 files totalling
**947,879,915 bytes**. Vite reports a non-fatal warning that the main minified
JavaScript chunk exceeds 1,200 kB; this is a future code-splitting optimization,
not an analytical correctness failure.

### 27.5 Exact TPS and building-location prototype (2026-10-22)

The profile now also supports an optional, off-by-default provisional Town
Planning Scheme overlay. The published source is
`web/public/data/tps-provisional.geojson`, containing 312 valid Polygon or
MultiPolygon features in EPSG:4326. TPS clicks are resolved by internal
`source_id` to the authoritative full GeoJSON feature before analysis because
MapLibre-rendered geometry may be clipped or simplified. Reader-facing output
shows TPS name and number only; workflow status remains internal, the blue
selection summary does not repeat the number already present in the panel title,
missing values use explicit unavailable labels, and duplicated public
identifiers remain separate source features.

TPS selection replaces the active circle and uses the same normalized
`local-area-profile.v1` inspector and A2/A3 print path. Point membership is
boundary-inclusive, lines are clipped and length-weighted against the exact
polygon, polygons are clipped/unioned against the exact polygon, and raster
requests carry the TPS polygon for valid-cell masking. Circle selection remains
unchanged during this reversible prototype.

The canonical manifest now publishes:

```text
web/public/data/local-profile/building-locations.fgb
web/public/data/local-profile/building-locations-manifest.json
```

`building-locations.fgb` contains **162,421** EPSG:32643 points and is
**28,701,048 bytes** with SHA-256
`d31c94f8dacc0df1946d4ae8e2a88128bbf0dc9e031b8d071e82ca0ab69441f6`.
It excludes all **8,995** enriched records where
`conflict=true` and the four audited records outside their declared repaired
AMC source zones. Its analytical fields are `zone_objectid`, `zone_group`,
`height_m`, `area_m2`, `volume_m3`, and `suhi`; source IDs and conflict/audit
fields are not published. Central locations remain count-only, and enriched
attribute summaries report field-specific valid denominators. SUHI is preserved
as an unverified categorical source class rather than coerced to a number. The
published valid counts are Low 4,222, Moderate 10,130, High 27,747, Very High
81,343 and Extreme High 5,091; 128,533 enriched records have a valid class and
Central contributes none. Circle and TPS profiles use the point asset as the
primary and sole building result. The retired polygon is preserved only as one
external rollback copy at
`archive/local-profile-polygon-rollback-2026-10-23/buildings.fgb` (357,613,072
bytes; SHA-256
`1a1306762081db8d149d95ba9c10f39c7dbb08dbd14bad8a29ba7fb46c022b47`).

The frozen real-asset circle baseline at longitude 72.5765716, latitude
23.0921374 is: 146 locations and 83,913 m² summed stored area at 400 m; 386 and
193,363 m² at 800 m; and 1,365 and 650,801 m² at 1,200 m. All selected records
at this fixture are enriched and Central contributes zero.

The Buildings section presents numeric distributions for provisional stored
area, provisional height and derived volume, plus categorical SUHI counts,
coverage and dominant class. It also reports the summed stored area of
point-selected enriched records and divides that sum by the exact circle or TPS
selection area. This value is labelled a **point-selected stored-area share**:
each boundary-inclusive selected point contributes its full stored area, so the
measure is not clipped footprint-union coverage and must not be described as an
exact built-up percentage.

Street topology uses stable simplified `u`/`v` identifiers. Where an identifier
occurs on several prepared segments, Python and the browser both select the
endpoint associated with the lowest stable `seg_id`; this prevents FlatGeobuf
range-query order from changing node and intersection counts. Serialized GTFS
route arrays are parsed into individual route identifiers before stop/reach
matching.

The representative TPS-20/A comparison matched browser and Python values for
polygon area, all building-location counts and means, street length and all
three topology ratios, park/school counts, and flood-risk areas. Product paths
that the current Python invocation does not independently mirror—combined
prepared centrality, normalized route/reach arrays, and raster datasets—remain
explicitly documented rather than being represented by circle approximations.
See `reports/tps_building_location_release_qa.md` for the field table and
limitations.

The final 2026-10-22 enhancement gate passed **135 Python tests** and **192
frontend tests across 25 files**, including real-HTTP exact-TPS integration. The
Vite production
build and `git diff --check` passed. Production browser QA verified TPS Off → On
→ rendered → clicked → `Profile ready`; a FlatGeobuf probe returned HTTP 206
with `Accept-Ranges: bytes`. Live A2 and A3 exact-TPS reports matched their
configured page sizes, had no sheet or section overflow, included TPS public
identity, omitted workflow status and internal `source_id`, and rendered all
four Buildings charts. Small positive centrality values retain meaningful
precision (for example, `0.0018` is not displayed as `0`). Long print notes wrap
rather than clip.

After the build, `web/dist/` is approximately **967 MB** and
`web/dist/data/local-profile/` approximately **562 MB**. Public and production
hashes match for the canonical manifest, building-location FlatGeobuf and TPS
GeoJSON. The hosted polygon analytical asset is retired; only the dated external
rollback copy remains. No deployment, upload, display-tile replacement or commit was
performed.

TPS Overview is selection-aware: point-based TPS results show **Building
locations** from `totalLocationCount` and omit polygon-only footprint-coverage
metrics. Circle profiles continue to show Buildings and building-footprint
coverage. This prevents unsupported TPS footprint coverage from appearing as an
Unavailable metric.

### 27.6 Development-plan overlay and three-format print implementation (2026-10-23)

The supplied Development plan GeoTIFF is preserved at
`data/external/development-plan/development-plan-source.tiff`. Its browser
derivative, `web/public/data/development-plan.png`, is a 1,949 × 1,919 RGBA PNG
whose decoded pixels match source bands 1–4 exactly. The source and derivative
CRS, bounds, WGS84 image corners, dimensions, byte sizes and SHA-256 hashes are
recorded in `web/public/data/development-plan-manifest.json`. The layer is a MapLibre image/raster overlay, appears last under Experimental /
not validated, is off by default and is labelled supplied, unverified and
experimental. It is attributed to ARPM Studio as *Development Plan for
Ahmedabad 2041* (`https://arpm.studio/projects/ahmedabad-dp-2041`). The raster
is inserted below the first OSM road layer; OSM roads and all application
overlays therefore render above it. Its embedded cartography, legend and north
arrow are not reclassified or reinterpreted.

The print system now provides three independent fixed physical compositions:

- A2 landscape: 594 × 420 mm;
- A3 landscape: 420 × 297 mm; and
- A3 portrait: 297 × 420 mm.

The fixed grids are independent: A2 landscape uses 16 columns and 15 mm
margins, A3 landscape uses 12 columns and 12 mm margins, and A3 portrait uses
8 columns and 12 mm margins. Runtime rotation, shrinking and responsive
rearrangement are not part of the print contract. The hatched `Computed result`
box has been removed; monochrome fixed slots are used instead.

Every format uses the same frozen normalized profile result and contains a
monochrome key map with only the unioned Ahmedabad municipal boundary and the
selected 400/800/1,200 m circle or authoritative TPS Polygon/MultiPolygon. The
key map includes a north arrow, approximate 5 km scale bar and a locator halo
for small circles. No roads, labels, basemap, analytical layer or Development
plan raster enters the key map. Every sheet carries the visible disclaimer:
“Experimental prototype. The website and this report use unverified data. No
accuracy is guaranteed. The creator accepts no responsibility for the accuracy
of the data or derived outputs.”

Implementation and parent QA are complete for the documented overlay and fixed
print contracts. The final gate passed 140 Python tests and 206 frontend tests
with 4 skipped, a production build, `git diff --check`, and public/dist parity
for the Development-plan and Ahmedabad-boundary publications plus metadata.
Production browser QA confirmed ARPM Studio attribution in Method & sources,
the final default-off control, clean console state, and OSM roads/labels above
the active Development-plan raster. Live circle sheets had zero sheet/module/
key-map/footer overflow and zero module overlap in all formats. Headless Chrome
generated one-page circle and exact-TPS PDFs for A2 landscape, A3 landscape and
A3 portrait at the intended physical dimensions; rendered PDF thumbnails showed
complete sheets without clipping or overlap. The supplied Jantri file is
incorrect and remains excluded from the roadmap and publication. No deployment,
upload, commit or fallback retirement was performed.
