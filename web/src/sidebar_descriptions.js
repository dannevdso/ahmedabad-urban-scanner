const INDICATOR_DESCRIPTIONS = {
  buildingArea: 'Building footprint size in square metres.',
  categories: 'Number of essential destination types reachable in 15 minutes.',
  health: 'Walking time to the nearest healthcare destination.',
  education: 'Walking time to the nearest education destination.',
  food: 'Walking time to the nearest food or market destination.',
  transport: 'Walking time to the nearest public transport stop.',
  green: 'Walking time to the nearest green space.',
  civic: 'Walking time to the nearest civic facility.',
  culture: 'Walking time to the nearest culture or learning destination.',
  sport: 'Walking time to the nearest sport or recreation destination.',
  lst: 'Hot-season surface temperature around each building.',
  ndvi: 'Hot-season satellite measure of nearby vegetation.',
  vegetation: 'Share of nearby pixels classified as vegetation.',
  priority: 'Relative priority from heat and surrounding greenery.',
  planxCompactness: 'How compact each building footprint is.',
  planxConvexity: 'How closely each footprint follows its convex hull.',
  planxElongation: 'How long and narrow each building footprint is.',
  planxCellArea: 'Area of the surrounding morphological cell.',
}

const OVERLAY_DESCRIPTIONS = {
  gtfsShapes: 'Transit route lines.',
  gtfsStops: 'Locations of transit stops.',
  gtfsServiceDay: 'All scheduled departures across the GTFS service day.',
  gtfsMorningPeak: 'Scheduled departures from 08:00 to before 10:00.',
  gtfsEveningPeak: 'Scheduled departures from 17:00 to before 19:00.',
  gtfsDeparturesPerHour: 'Whole-day departures divided by the service-day span.',
  transitIsochrones: 'Show 15-minute walks from stops on routes reached directly or within a 5-minute walk.',
  floodRiskZones: 'Provisional urban flood-risk classes from VEDAS/ISRO.',
  centrality: 'Relative importance of streets in the network.',
  heatRisk: 'Screening proxy for heat-related urban form.',
  shadowCasting: 'Areas reached by building shadows.',
  sunHours: 'Estimated direct sunlight duration.',
  skyViewFactor: 'Visibility of the sky above each location.',
  solarIrradiation: 'Estimated daily solar energy received.',
  environmentSurfaceTemperature: 'Satellite-derived surface temperature.',
  environmentNdvi: 'Satellite-derived vegetation index.',
  environmentVegetationFraction: 'Nearby share of vegetation-positive pixels.',
  environmentHeatGreenPriority: 'Relative heat and greenery priority.',
  buildingHeight: 'Modelled 2023 height: 30 m overview, ~4 m effective detail when zoomed in.',
  spaceSyntax: 'Network structure and street accessibility.',
  ...Object.fromEntries([
    ['parks', 'Parks and recreation locations.'],
    ['schools', 'Schools and university locations.'],
  ].map(([type, description]) => [`poi-${type}`, description])),
}

export const baseControlDescriptions = {
  buildings: 'Show or hide building footprints.',
  basemap: 'Show or hide streets and the background map.',
}

const SPACE_SYNTAX_DESCRIPTIONS = {
  connectivity: 'Number of street segments directly connected to a particular segment. Higher is generally better for accessibility.',
  betweenness: 'How frequently a street link forms part of shortest network paths; indicates its importance as a connector. Higher indicates movement potential.',
  straightness: 'Average ratio of straight-line distance to shortest network distance; higher values indicate more direct routes. Higher is generally better for accessibility.',
  nc: 'Number of street segments reachable within the specified analysis radius. Higher is generally better for accessibility.',
  ch: 'How frequently a street segment lies on the least-angular-change routes between other segments; indicates potential through-movement. Higher indicates movement potential.',
  md: 'Average angular cost needed to reach other segments; lower values indicate better integration. Lower indicates greater integration.',
  td: 'Sum of angular costs from a segment to all reachable segments; measures cumulative separation. This depends on the number of reachable segments, so compare cautiously.',
}

export function spaceSyntaxSidebarDescription(key) {
  if (SPACE_SYNTAX_DESCRIPTIONS[key]) return SPACE_SYNTAX_DESCRIPTIONS[key]
  const radialMeasure = key?.match(/^(nc|ch|md|td)_\d+$/)?.[1]
  return SPACE_SYNTAX_DESCRIPTIONS[radialMeasure] ?? 'Choose a network measure to color the street layer.'
}

export function indicatorSidebarDescription(key, indicator) {
  return INDICATOR_DESCRIPTIONS[key] ?? `${indicator.shortLabel || indicator.label}.`
}

export function overlaySidebarDescription(overlay) {
  return OVERLAY_DESCRIPTIONS[overlay.key] ?? `${overlay.label}.`
}
