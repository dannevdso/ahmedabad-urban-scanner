# Ahmedabad Urban Scanner

The active project is a staged Ahmedabad building scanner covering building
footprints, pedestrian-network 5/10/15-minute access, heat, greenery, and an
interactive web visualisation. See `AHMEDABAD_SCANNER.md` for the evidence
rules, phases, and current pilot configuration.

See `HANDBOOK.md` for the continuously maintained manual reproduction guide,
including source URLs, exact commands, parameters, outputs, results, and
limitations.

The interactive pilot is in `web/`. Rebuild its browser data and run it with:

```bash
uv run python scripts/build_web_data.py
npm --prefix web install
npm --prefix web run dev -- --port 4173
```

The current reversible prototype also publishes 162,421 conflict-filtered
VEDAS/ISRO-derived building locations and an optional off-by-default layer of
312 provisional Town Planning Scheme polygons. Clicking a TPS runs the Local
Area Profile against its authoritative exact boundary and feeds the same
inspector and A2 landscape, A3 landscape and A3 portrait print model used by circle profiles. Internal TPS
`source_id` and workflow status values are used only internally; readers see the
TPS name and number without repeated status text. Building profiles report
field-specific area, height and derived-volume distributions, categorical SUHI
composition, and a qualified point-selected stored-area share. Circles and TPS
use boundary-inclusive building-location membership without polygon-only
footprint-coverage claims. The legacy building-polygon analytical asset remains
available only as a rollback fallback when the point asset is unavailable. See
`reports/tps_building_location_release_qa.md` for the verified counts, parity
table, browser/range-request evidence and print gate.

All three print formats are fixed one-page physical sheets: A2 landscape
594 × 420 mm with 16 columns and 15 mm margins, A3 landscape 420 × 297 mm with
12 columns and 12 mm margins, and A3 portrait 297 × 420 mm with 8 columns and
12 mm margins. Each contains one square boundary-only key map with the
selected circle or exact TPS geometry, plus a north arrow, approximate 5 km
scale and a visible experimental/unverified/no-accuracy-guarantee disclaimer.
The supplied georeferenced Development plan is attributed to ARPM Studio,
*Development Plan for Ahmedabad 2041* (<https://arpm.studio/projects/ahmedabad-dp-2041>),
published as a visually unchanged contextual raster, and remains the final
default-off control. Its raster is below the first OSM road layer so OSM roads
and all application overlays render above it. The hatched Computed result box
has been removed. The supplied Jantri file is incorrect and is explicitly
excluded from the roadmap and publication; it is not deferred.

The active building source is **Google Research Open Buildings V3**. Overture
transport data and earlier City2Graph experiments remain available for source
comparison, but Overture footprints are not used in the pilot building table.

The existing Overture/City2Graph experiments below are preserved as source
exploration. Their POI proximity graphs are not the project's final
pedestrian-accessibility model.

## Earlier Overture Maps with City2Graph experiment

This project reproduces the Overture Maps workflow from the City2Graph tutorial and the linked Medium article: download `segment`, `building`, and `connector` data, process road barriers, build a morphological graph, and save a map.

## Setup

Requires Python 3.12–3.14. The commands below use [`uv`](https://docs.astral.sh/uv/), which creates an isolated `.venv` and locks dependencies.

```bash
uv sync
# Optional: install PyTorch + PyTorch Geometric for GNN conversion
uv sync --extra gnn
```

## Run

The default is Liverpool, UK, matching the City2Graph example. It downloads data from Overture Maps and geocodes the place through Nominatim.

```bash
uv run python run_overture.py
```

For a smaller or different study area:

```bash
uv run python run_overture.py --place "Kyoto, Japan" --distance 500 --clipping-buffer 300
```

Reuse downloaded GeoJSON files without downloading again:

```bash
uv run python run_overture.py --place "Liverpool, UK" --skip-download
```

For a locality without a polygon boundary in Nominatim, use a WGS84 bounding
box as `min_lon min_lat max_lon max_lat`. This is the Navrangpura, Ahmedabad
example used in testing:

```bash
uv run python run_overture.py \
  --bbox 72.5443429 23.0159998 72.5843429 23.0559998 \
  --distance 2000 --clipping-buffer 300 --plot-all-buildings \
  --output-dir data/navrangpura-ahmedabad
```

The interrupted citywide Ahmedabad download is preserved in
`data/ahmedabad/`; it contains the segment, building, and connector GeoJSON
files downloaded before graph construction was interrupted.

For a high-resolution graph-focused PNG from the already downloaded
Navrangpura data:

```bash
uv run python run_overture.py \
  --bbox 72.5443429 23.0159998 72.5843429 23.0559998 \
  --distance 2000 --clipping-buffer 300 \
  --plot-all-buildings --focus-graph --dpi 300 \
  --figure-name navrangpura_graph_focused_300dpi.png \
  --skip-download --output-dir data/navrangpura-ahmedabad
```

Law Garden was run with a separate 2 km x 2 km surrounding box centered on
the geocoded park location, using a 1 km graph radius. Its output is in
`data/law-garden-ahmedabad/law_garden_graph_focused_300dpi.png`.

### Reading the morphology map

- Light grey polygons are the raw downloaded building footprints.
- Red dots are place-space nodes created by the morphological graph; they are
  not guaranteed to be one dot per building.
- Red lines represent place-to-place adjacency (`touched_to`).
- Blue dots are movement-space nodes, representing processed street segments.
- Blue lines represent movement-to-movement street connectivity
  (`connected_to`).
- Purple lines represent place-to-movement interfaces (`faced_to`).

This graph describes spatial structure and connectivity. It does not by itself
measure pedestrian activity, vitality, traffic volume, land-use intensity, or
street quality. Those interpretations require additional attributes or field
data.

Outputs are written to `data/overturemaps/`, including the downloaded GeoJSON files and a `*_city2graph.png` map. The data request requires internet access and may take time or be rate-limited by Overture Maps/Nominatim.

## Data and attribution

The script uses Overture Maps data and Nominatim geocoding. Follow their current attribution, licensing, and usage policies when sharing outputs. Downloaded data and generated images are intentionally kept outside version control.
