# Ahmedabad Urban Scanner

An experimental web-based urban analysis tool for Ahmedabad and the surrounding study area.

The scanner combines building data, pedestrian accessibility, environmental indicators, mapped facilities, transport context, and selected urban-analysis layers in an interactive MapLibre map.

> **Status:** Experimental research prototype. Data are incomplete and partly provisional. Accuracy is not guaranteed, and the scanner should not be treated as an official municipal, cadastral, planning, or decision-support system.

## Website

The interactive application is located in [`web/`](web/).

It provides:

- interactive building and urban-context mapping;
- Google Open Buildings V3 building footprints;
- building-location profiles using a separate provisional point dataset;
- 5-, 10-, and 15-minute pedestrian-accessibility analysis;
- mapped destinations and facility categories;
- heat and greenery context from Landsat and Sentinel-2 imagery;
- selected PlanX and space-syntax context layers;
- flood-risk and development-plan overlays;
- optional Town Planning Scheme boundary selection;
- local area profiles for circles and selected TPS polygons;
- A2 landscape, A3 landscape, and A3 portrait printable reports;
- source labels, methods, caveats, legends, and explicit no-data states.

## Run the website locally

From the repository root:

```bash
uv sync --group dev
uv run python scripts/build_web_data.py

npm --prefix web install
npm --prefix web run dev -- --port 4173
```

Open the local development URL shown by Vite.

To create a production build:

```bash
npm --prefix web run build
```

To run the frontend test suite:

```bash
npm --prefix web test
```

## Data and analytical scope

The active building-footprint source is **Google Research Open Buildings V3**.

Other project sources include:

- **OpenStreetMap** for pedestrian networks, roads, and mapped destinations;
- **Landsat Collection 2 Level-2** imagery for land-surface-temperature context;
- **Copernicus Sentinel-2 Level-2A** imagery for vegetation context;
- **GTFS** data for qualified scheduled-service and route-reach context;
- **VEDAS/ISRO-derived** building-location and flood-risk data;
- selected **PlanX** and supplied space-syntax layers;
- a supplied **Development Plan for Ahmedabad 2041** raster, attributed to ARPM Studio.

The website renders precomputed browser assets. Heavy data acquisition, spatial processing, auditing, and analytical calculations are performed through the Python workflow rather than in the browser.

## Important interpretation limits

The scanner does not directly measure:

- pedestrian activity;
- urban vitality;
- facility quality, capacity, or observed use;
- population, occupancy, tenure, or resident characteristics;
- air temperature or personal heat exposure;
- tree canopy or shade from NDVI alone;
- verified transit reliability, capacity, ridership, or service quality.

Accessibility results describe network proximity to mapped destinations. They do not establish that a facility is used, accessible to every person, open at a particular time, or of a particular quality.

The Ahmedabad–Gandhinagar study extent was digitised and approximately georeferenced from a supplied image. It is suitable as a reproducible clipping and acquisition extent, but it is not an official administrative, statutory, property, or development-plan boundary.

Some building-location attributes, including area, height, derived volume, and categorical SUHI values, are provisional and retain their source-specific caveats.

## Reproducibility documentation

For the full workflow, parameters, source URLs, commands, outputs, audits, and limitations, see:

- [`HANDBOOK.md`](HANDBOOK.md) — detailed reproduction manual;
- [`AHMEDABAD_SCANNER.md`](AHMEDABAD_SCANNER.md) — staged analytical design;
- [`reports/`](reports/) — data audits, QA reports, and release evidence;
- [`project-history-summary.md`](project-history-summary.md) — project history and verified state.

The primary pilot configuration is:

```text
config/ahmedabad_pilot.toml
```

The pilot uses:

- EPSG:4326 for source coordinates;
- EPSG:32643 for metric analysis;
- 5-, 10-, and 15-minute walking thresholds;
- a walking speed of 4.8 km/h;
- a maximum accepted building-to-network snap distance of 250 m.

## Project structure

```text
ahmedabad-urban-scanner/
├── ahmedabad_scanner/       # reusable Python analysis functions
├── config/                  # study areas and analytical parameters
├── data/                    # downloaded and generated data
├── outputs/                 # generated maps and analytical outputs
├── reports/                 # audits, summaries, and QA evidence
├── scripts/                 # acquisition and processing workflows
├── tests/                   # Python tests
├── web/                     # Vite/MapLibre web application
├── AHMEDABAD_SCANNER.md     # staged analytical design
├── HANDBOOK.md              # reproducibility handbook
├── pyproject.toml
└── uv.lock
```

Large raw datasets and generated files are intentionally kept outside normal source-control workflows where appropriate. The scripts, configurations, reports, and handbook document how to rebuild them.

## Attribution

Please follow the current attribution and licensing requirements of every source before sharing derived outputs.

Relevant sources include:

- Google Research Open Buildings V3;
- OpenStreetMap contributors;
- OpenMapTiles and the selected basemap provider;
- Landsat and USGS/NASA data;
- Copernicus Sentinel-2 data;
- Microsoft Planetary Computer;
- ARPM Studio, *Development Plan for Ahmedabad 2041*;
- supplied VEDAS/ISRO-derived datasets;
- PlanX and other upstream analytical tools.

## License and responsibility

This repository is maintained for research and experimental urban-analysis purposes.

The author accepts no responsibility for decisions, interpretations, maps, measurements, or derived outputs produced from this prototype. Verify all data, boundaries, sources, and calculations independently before using them for planning, policy, design, investment, or public communication.