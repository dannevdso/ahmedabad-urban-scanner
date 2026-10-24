const NO_DATA_COLOR = '#8d8d8d'

export const indicators = {
  buildingArea: {
    group: 'Buildings',
    label: 'Open Buildings footprint area',
    shortLabel: 'Footprint area',
    property: 'footprint_area_m2',
    unit: ' m²',
    decimals: 1,
    stops: [[0, '#f7fbff'], [50, '#c6dbef'], [150, '#6baed6'], [400, '#2171b5'], [1000, '#08306b']],
    source: 'Google Research Open Buildings V3',
    contextKey: 'full-study-current',
    context: 'Published building-footprint area from the current study-area download.',
    method: 'Area supplied by Google Open Buildings V3; no analytical model is applied in this interim map.',
    period: 'Current V3 polygon release',
  },
  categories: {
    group: 'Access',
    label: 'Essential categories within 15 minutes',
    shortLabel: '15-minute access',
    property: 'categories_15min',
    unit: ' of 8',
    decimals: 0,
    stops: [[0, '#f4f4f4'], [2, '#d0e2ff'], [4, '#78a9ff'], [6, '#0f62fe'], [8, '#002d9c']],
    source: 'OpenStreetMap contributors via OSMnx/Overpass',
    contextKey: 'contextual-osm',
    context: 'Pedestrian-network travel from the building to eight mapped destination categories.',
    method: 'Count of categories whose nearest mapped destination is reachable within 15 minutes at 4.8 km/h.',
    period: 'OSM snapshot acquired 2026',
  },
  health: accessIndicator('Healthcare walking time', 'health_min'),
  education: accessIndicator('Education walking time', 'education_min'),
  food: accessIndicator('Food and market walking time', 'food_min'),
  transport: accessIndicator('Public transport walking time', 'transport_min'),
  green: accessIndicator('Green-space walking time', 'green_min'),
  civic: accessIndicator('Civic facility walking time', 'civic_min'),
  culture: accessIndicator('Culture and learning walking time', 'culture_min'),
  sport: accessIndicator('Sport and recreation walking time', 'sport_min'),
  lst: {
    group: 'Environment',
    label: 'Hot-season land surface temperature',
    shortLabel: 'Surface temperature',
    property: 'lst_c',
    unit: ' °C',
    decimals: 2,
    stops: [[40, '#2d004b'], [42, '#54278f'], [44, '#f768a1'], [46, '#fdbb84'], [48, '#fff7bc']],
    source: 'USGS Landsat 8/9 Collection 2 Level-2 via Microsoft Planetary Computer',
    contextKey: 'full-study-current',
    context: 'Median satellite-observed daytime surface temperature within 100 m of the building.',
    method: 'Median of ten QA-masked scenes from April–May 2026; not air or indoor temperature.',
    period: '2026-04-01 to 2026-05-31',
  },
  ndvi: {
    group: 'Environment',
    label: 'Hot-season vegetation index',
    shortLabel: 'NDVI',
    property: 'ndvi',
    unit: '',
    decimals: 3,
    stops: [[0, '#a6611a'], [0.1, '#dfc27d'], [0.2, '#f5f5f5'], [0.3, '#80cdc1'], [0.5, '#018571']],
    source: 'Copernicus Sentinel-2 L2A via Microsoft Planetary Computer',
    contextKey: 'full-study-current',
    context: 'Median NDVI within 50 m of the building representative point.',
    method: 'Median of ten SCL-masked scenes with processing-baseline reflectance offsets applied.',
    period: '2026-04-01 to 2026-05-31',
  },
  vegetation: {
    group: 'Environment',
    label: 'Vegetated pixels within 50 metres',
    shortLabel: 'Vegetation fraction',
    property: 'vegetation_fraction',
    unit: '%',
    decimals: 1,
    percent: true,
    stops: [[0, '#f7fcf5'], [0.1, '#c7e9c0'], [0.25, '#74c476'], [0.5, '#238b45'], [0.75, '#00441b']],
    source: 'Derived from Copernicus Sentinel-2 L2A NDVI',
    contextKey: 'full-study-current',
    context: 'Fraction of valid 10 m pixels within 50 m whose NDVI is at least 0.3.',
    method: 'Operational vegetation threshold; it is not a validated tree-canopy classification.',
    period: '2026-04-01 to 2026-05-31',
  },
  priority: {
    group: 'Environment',
    label: 'Relative heat–greenery priority',
    shortLabel: 'Heat–green priority',
    property: 'heat_green_priority',
    unit: '',
    decimals: 2,
    stops: [[0, '#2c105c'], [0.25, '#711f81'], [0.5, '#b73779'], [0.75, '#ed7953'], [0.9, '#fbd467']],
    source: 'Derived from pilot-relative Landsat heat and Sentinel-2 greenery percentiles',
    contextKey: 'full-study-current',
    context: 'Relative rank within this pilot only. Higher values combine hotter and less-green surroundings.',
    method: 'Mean of heat percentile and inverse greenery percentile. Recalculate for any new study extent.',
    period: '2026 hot-season pilot reference',
  },
  planxCompactness: planxBuildingIndicator(
    'PlanX footprint compactness', 'Compactness', 'planx_compactness', '', 3,
    [[0, '#f7fcf5'], [0.25, '#c7e9c0'], [0.5, '#74c476'], [0.75, '#238b45'], [0.9, '#00441b']],
    'Area relative to perimeter; a descriptive footprint-geometry measure, not a quality score.', 'full-study-current',
  ),
  planxConvexity: planxBuildingIndicator(
    'PlanX footprint convexity', 'Convexity', 'planx_convexity', '', 3,
    [[0, '#fff7ec'], [0.5, '#fee8c8'], [0.7, '#fdbb84'], [0.85, '#e34a33'], [0.95, '#7f0000']],
    'Footprint area divided by convex-hull area; it describes geometric indentation and irregularity. In the full-study export, 715 values exceed 1.0 by small numerical overshoots from floating-point area calculations; source values are retained and not clipped.', 'full-study-current',
  ),
  planxElongation: planxBuildingIndicator(
    'PlanX footprint elongation', 'Elongation', 'planx_elongation', '', 2,
    [[0, '#f7fbff'], [0.2, '#c6dbef'], [0.4, '#6baed6'], [0.6, '#2171b5'], [0.8, '#08306b']],
    'PlanX elongation score; values near 0 indicate compact plans and values near 1 indicate long, thin plans.', 'full-study-current',
  ),
  planxCellArea: planxBuildingIndicator(
    'PlanX morphological tessellation area (30,000-building pilot)', 'Tessellation cell area (pilot)', 'planx_cell_m2', ' m²', 1,
    [[0, '#f7fcfd'], [250, '#ccece6'], [500, '#66c2a4'], [1000, '#238b45'], [2000, '#005824']],
    'Pilot-only morphological cell area; not full-study coverage, parcel ownership, or plot area.', 'archived-navrangpura',
  ),
}

function accessIndicator(label, property) {
  return {
    group: 'Access',
    label,
    shortLabel: label.replace(' walking time', ''),
    property,
    unit: ' min',
    decimals: 1,
    stops: [[0, '#005a32'], [5, '#41ab5d'], [10, '#addd8e'], [15, '#ffffcc'], [25, '#fd8d3c'], [40, '#bd0026']],
    source: 'OpenStreetMap contributors via OSMnx/Overpass',
    contextKey: 'contextual-osm',
    context: 'Modelled travel time over the mapped pedestrian network from the building to the nearest destination.',
    method: 'Shortest-path time at 4.8 km/h plus the building-to-network connection. No-data is not treated as poor access.',
    period: 'OSM snapshot acquired 2026',
  }
}

function planxBuildingIndicator(label, shortLabel, property, unit, decimals, stops, context, contextKey) {
  return {
    group: 'PlanX building form',
    label,
    shortLabel,
    property,
    unit,
    decimals,
    stops,
    source: 'PlanX QGIS plugin, pinned commit d2423379',
    contextKey,
    context,
    method: 'Derived from the Google Open Buildings footprint geometry by the official PlanX building-metrics or tessellation algorithm.',
    period: 'Current Ahmedabad–Gandhinagar Open Buildings V3 footprints, 2026',
  }
}

export function getIndicator(key) {
  const indicator = indicators[key]
  if (!indicator) throw new Error(`Unknown indicator: ${key}`)
  return indicator
}

export function availableIndicators(availableProperties = []) {
  const properties = new Set(availableProperties)
  return Object.entries(indicators).filter(([, indicator]) => properties.has(indicator.property))
}

export function formatIndicatorValue(key, value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return 'No data'
  const indicator = getIndicator(key)
  const numeric = Number(value)
  if (indicator.percent) return `${(numeric * 100).toFixed(indicator.decimals)}%`
  return `${numeric.toFixed(indicator.decimals)}${indicator.unit}`
}

export function makeStepExpression(key) {
  const indicator = getIndicator(key)
  const [first, ...rest] = indicator.stops
  const step = ['step', ['to-number', ['get', indicator.property]], first[1]]
  for (const [threshold, color] of rest) step.push(threshold, color)
  return [
    'case',
    ['all', ['has', indicator.property], ['!=', ['get', indicator.property], null]],
    step,
    NO_DATA_COLOR,
  ]
}

export function legendEntries(key) {
  const indicator = getIndicator(key)
  return indicator.stops.map(([value, color], index) => {
    const next = indicator.stops[index + 1]?.[0]
    const label = next === undefined
      ? `≥ ${formatIndicatorValue(key, value)}`
      : `${formatIndicatorValue(key, value)}–${formatIndicatorValue(key, next)}`
    return { value, color, label }
  })
}

export { NO_DATA_COLOR }
