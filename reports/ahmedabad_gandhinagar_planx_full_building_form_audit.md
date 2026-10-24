# Ahmedabad–Gandhinagar full-study PlanX building-form audit

Status: **ok**
Generated UTC: `2026-10-18T13:40:53.263226+00:00`
Scope: **full-study**

## Provenance

- `input`: `data/derived/planx/ahmedabad-gandhinagar-full-buildings-inputs.gpkg`
- `output`: `data/derived/planx/ahmedabad-gandhinagar-full-building-outputs/building_metrics.gpkg`
- `config`: `config/ahmedabad_gandhinagar_planx_full_buildings.toml`
- `log`: `data/derived/planx/ahmedabad-gandhinagar-full-building-logs/run_20261018T005947Z.json`
- Run `20261018T005947Z`: status `ok`, return code `0`

## Counts and identifiers

- Input buildings: **1077523**
- Output building metrics: **1077523**
- Source-building duplicate excess rows: **16**

## Required-field contract

| Field | Present | Non-null | Numeric | Finite | Min | P10 | Median | P90 | Max |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `area_m2` | True | 1077523 | 1077523 | 1077523 | 2.5069728205886745 | 18.94013574604922 | 67.41551453917388 | 202.8598688093239 | 31566.51362757148 |
| `perim_m` | True | 1077523 | 1077523 | 1077523 | 6.336115191675055 | 17.998799884039325 | 34.48760395381578 | 62.38735473148094 | 2226.372097779845 |
| `compact` | True | 1077523 | 1077523 | 1077523 | 0.06130960136488579 | 0.5644579524908228 | 0.7393382867786048 | 0.7840195836148196 | 0.946812552535724 |
| `convexity` | True | 1077523 | 1077523 | 1077523 | 0.2419835582055846 | 0.9353645189523547 | 1.0 | 1.0 | 1.0000360685302074 |
| `rectang` | True | 1077523 | 1077523 | 1077523 | 0.181080409414925 | 0.8810384678205943 | 0.9999990798709831 | 1.000003538093016 | 1.000116318787288 |
| `elongation` | True | 1077523 | 1077523 | 1077523 | 0.0 | 0.06567981983333637 | 0.3190945049078169 | 0.6292345924824021 | 0.9698771485385026 |
| `orient_deg` | True | 1077523 | 1077523 | 1077523 | 0.0 | 4.967568044120585 | 87.78104422112229 | 171.15262621233202 | 179.9999999994697 |
| `court_m2` | True | 1077523 | 1077523 | 1077523 | 0.0 | 0.0 | 0.0 | 0.0 | 2409.89422592983 |
| `court_idx` | True | 1077523 | 1077523 | 1077523 | 0.0 | 0.0 | 0.0 | 0.0 | 0.2923431327193012 |
| `fractal` | True | 1077523 | 1077523 | 1077523 | 0.9522561670139549 | 1.0004497885094281 | 1.0149884710822574 | 1.0772372615626944 | 2.5196150800685233 |
| `corners` | True | 1077523 | 1077523 | 1077523 | 3.0 | 4.0 | 4.0 | 6.0 | 241.0 |
| `sharedwall` | True | 1077523 | 1077523 | 1077523 | 0.0 | 0.0 | 0.0 | 0.0 | 0.83247258829547 |

## Quantiles

- Exact deterministic nearest-rank quantiles: ceil(q*N)-1 zero-based offset after ascending ORDER BY; values are unrounded SQLite REAL values.

## Convexity and rectangularity above 1

- Convexity semantics: `outer-ring area / convex-hull area`.
- Rectangularity semantics (`rectang`): `outer-ring area / minimum-oriented-rectangle area`.
- Both ratios have a theoretical upper bound of **1.0** for valid planar geometry. The PlanX implementation uses floating-point area calculations, so these small overshoots are numerical artifacts, not a new metric meaning.
- Source values are retained without clipping or normalization.
- `convexity > 1`: **715**; maximum excess: **3.6068530207e-05**.
- `rectang > 1`: **406965**; maximum excess: **0.000116318787288**.

## Stage truthfulness

| Stage | Status | Reason |
|---|---|---|
| `buildingmetrics` | **completed** | — |
| `tessellation` | **not_run** | No full-study tessellation output is present or claimed. |
| `spacematrix` | **blocked** | No verified floor-count/levels field is available; no DEFAULT_LEVELS assumption was supplied. |
| `space_syntax` | **not_run** | Space syntax was not rerun for this full-study report. |

## Limitations

- Shape metrics are footprint geometry measures in projected EPSG:32643; they are not height, floor-area, land-use, occupancy, or quality measures.
- Values above 1.0 are retained as observed PlanX outputs and counted; their small positive excess is reported as floating-point numerical overshoot of bounded ratios, with no clipping or normalization.
- No planx_cell_m2 is reported because full-study tessellation is absent.
