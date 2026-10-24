# Ahmedabad Urban Scanner — staged build

This project will produce three connected outputs for Ahmedabad:

1. an interactive building-level visualisation;
2. a pedestrian-network 5/10/15-minute access study;
3. a heat, greenery, and environmental scanner.

## Evidence rule

A building is the visual and locational unit. A value is only described as
building-level when it is directly measured or calculated for that building.
Area statistics, modelled population, satellite pixels, and proximity measures
retain their actual source geography and evidence type.

## Study sequence

### Phase 1 — foundation and source audit

- Preserve existing Overture downloads.
- Record the study boundary, source CRS, metric CRS, and input paths.
- Audit geometry validity and spatial leakage before analysis.

### Phase 2 — bounded pilot buildings

- Use Google Research Open Buildings V3 polygons for the configured
  Navrangpura pilot bbox.
- Filter the official level-6 S2 shard by published building centroids.
- Apply the official level-4 cell's 85% precision confidence threshold.
- Retain Plus Codes, confidence values, and source metadata.
- Produce a compact GeoParquet building table and a visual QA map.

### Phase 3 — true 15-minute access

- Download or reuse a pedestrian OSM network for the buffered pilot.
- Build explicit destination categories.
- Snap buildings and destinations to the network.
- Calculate nearest travel time and reachable counts at 5, 10, and 15 minutes.
- Keep proximity separate from facility quality, capacity, and observed use.

### Phase 4 — heat and greenery

- Completed for the pilot using 10 Landsat 8/9 and 10 Sentinel-2 L2A scenes
  from 2026-04-01 through 2026-05-31.
- Calculated cloud-masked median daytime land-surface temperature and NDVI.
- Calculated 100 m LST, 50 m NDVI, and 50 m vegetated-pixel context for each
  building while preserving scene IDs, resolution, masks, and observation counts.
- Retained pedestrian-network access to mapped green spaces from Phase 3.
- Did not label NDVI as tree canopy because no canopy-classification validation
  has yet been completed.

### Phase 5 — interactive scanner

- Completed for the pilot as a static Vite and MapLibre GL JS application in
  `web/`.
- Exported 17,847 simplified footprints and selected indicators as compact
  browser GeoJSON plus metadata.
- Added thirteen map layers, dynamic legends, a building inspector, a methods
  dialog, source/period/context labels, explicit no-data display, and responsive
  controls.
- Verified the production build, browser interactions, and zero known npm
  vulnerabilities. Public deployment awaits a configured static-host account.

### Phase 6 — Ahmedabad municipal scale

Scale only after the pilot completes end to end. The current citywide Overture
place-name download covers an area much larger than the Ahmedabad municipal
extent, so it must not be treated as the final city boundary.

## Current pilot configuration

`config/ahmedabad_pilot.toml` is the source of truth. Bounding boxes use
`[min_lon, min_lat, max_lon, max_lat]`; metric analysis uses EPSG:32643.

Run the non-destructive source audit with:

```bash
uv run python scripts/audit_inputs.py
```
