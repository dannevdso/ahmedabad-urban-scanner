import { resolveContext, resolveItemContextKey } from './context.js'
import { BUILDING_HEIGHT_TILE_ZOOMS, buildingHeightLayers, buildingHeightSources } from './building_height.js'

const emptyFeatureCollection = () => ({ type: 'FeatureCollection', features: [] })

export const PLANX_SOURCES = {
  gtfsStops: { type: 'geojson', data: './data/gtfs-stops.geojson' },
  gtfsShapes: { type: 'geojson', data: './data/gtfs-shapes.geojson' },
  gtfsServiceIntensity: { type: 'geojson', data: './data/gtfs-service-intensity.geojson' },
  transitIsochrone15: { type: 'geojson', data: emptyFeatureCollection() },
  transitIsochroneDirect15: { type: 'geojson', data: emptyFeatureCollection() },
  transitIsochroneRouteStops: { type: 'geojson', data: emptyFeatureCollection() },
  publicPois: { type: 'geojson', data: './data/pois.geojson' },
  floodRiskZones: { type: 'geojson', data: './data/ahm-urban-flood-risk-zones.geojson' },
  tpsProvisional: { type: 'geojson', data: './data/tps-provisional.geojson' },
  centrality: { type: 'geojson', data: './data/planx-centrality.geojson' },

  heatRisk: { type: 'geojson', data: './data/planx-heat-risk.geojson' },

  shadowCasting: { type: 'image', url: './data/planx-shadow-casting.png', coordinates: [[72.4109191373896, 23.263714341096108], [72.73796268185004, 23.268770122568007], [72.74379212245495, 22.920265285330075], [72.41758925179329, 22.915293725211118]] },
  sunHours: { type: 'image', url: './data/planx-sun-hours.png', coordinates: [[72.4109191373896, 23.263714341096108], [72.73796268185004, 23.268770122568007], [72.74379212245495, 22.920265285330075], [72.41758925179329, 22.915293725211118]] },
  skyViewFactor: { type: 'image', url: './data/planx-sky-view-factor.png', coordinates: [[72.4109191373896, 23.263714341096108], [72.73796268185004, 23.268770122568007], [72.74379212245495, 22.920265285330075], [72.41758925179329, 22.915293725211118]] },
  solarIrradiation: { type: 'image', url: './data/planx-solar-irradiation.png', coordinates: [[72.4109191373896, 23.263714341096108], [72.73796268185004, 23.268770122568007], [72.74379212245495, 22.920265285330075], [72.41758925179329, 22.915293725211118]] },
  environmentSurfaceTemperature: { type: 'image', url: './data/environment-surface-temperature.png', coordinates: [[72.41079345037157, 23.26372886950044], [72.73813009009197, 23.268789141198738], [72.7439591048386, 22.920284264487098], [72.41746389304392, 22.915308288895066]] },
  environmentNdvi: { type: 'image', url: './data/environment-ndvi.png', coordinates: [[72.41089111961816, 23.263730481209777], [72.73813009009197, 23.268789141198738], [72.7439591048386, 22.920284264487098], [72.41756131135291, 22.915309873756836]] },
  environmentVegetationFraction: { type: 'image', url: './data/environment-vegetation-fraction.png', coordinates: [[72.41089111961816, 23.263730481209777], [72.73813009009197, 23.268789141198738], [72.7439591048386, 22.920284264487098], [72.41756131135291, 22.915309873756836]] },
  environmentHeatGreenPriority: { type: 'image', url: './data/environment-heat-green-priority.png', coordinates: [[72.41079345037157, 23.26372886950044], [72.73813009009197, 23.268789141198738], [72.7439591048386, 22.920284264487098], [72.41746389304392, 22.915308288895066]] },
  buildingHeight: buildingHeightSources.overview,
  ...Object.fromEntries(BUILDING_HEIGHT_TILE_ZOOMS.map((zoom, index) => [`buildingHeightFine${zoom}`, buildingHeightSources.fine[index]])),

  spaceSyntax: { type: 'geojson', data: './data/space-syntax.geojson' },
  spaceSyntaxPoints: { type: 'geojson', data: './data/space-syntax-points.geojson' },
  developmentPlan: { type: 'image', url: './data/development-plan.png', coordinates: [[72.175196139126, 23.364584536618], [72.860609370435, 23.364584536618], [72.860609370435, 22.74362328497], [72.175196139126, 22.74362328497]] },
}

export const SPACE_SYNTAX_FIELDS = [
  ['off', 'Off'], ['connectivity', 'Connectivity'], ['betweenness', 'Edge betweenness'],
  ['closeness', 'Mean closeness'], ['straightness', 'Mean straightness'],
  ['nc_400', 'NC 400 m'], ['td_400', 'TD 400 m'], ['md_400', 'MD 400 m'], ['nain_400', 'NAIN 400 m'], ['ch_400', 'CH 400 m'], ['nach_400', 'NACH 400 m'],
  ['nc_2500', 'NC 2,500 m'], ['td_2500', 'TD 2,500 m'], ['md_2500', 'MD 2,500 m'], ['nain_2500', 'NAIN 2,500 m'], ['ch_2500', 'CH 2,500 m'], ['nach_2500', 'NACH 2,500 m'],
]

const hidden = { visibility: 'none' }
const line = (id, source, property, color = '#440154') => ({ id, type: 'line', source, layout: hidden, paint: {
  'line-color': color,
  'line-width': ['interpolate', ['linear'], ['zoom'], 10, 0.6, 16, 2.4], 'line-opacity': 0.8,
} })

const POI_DEFINITIONS = [
  ['parks', 'Parks and recreation', '#15803d'],
  ['schools', 'Schools and universities', '#2563eb'],
]

const serviceIntensityLayer = (id, property) => ({ id, type: 'circle', source: 'planx-gtfsServiceIntensity', layout: hidden, paint: {
  'circle-radius': ['interpolate', ['linear'], ['to-number', ['get', property]], 0, 2, 20, 6, 100, 11],
  'circle-color': '#440154', 'circle-opacity': 0.82, 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 0.4,
} })

export const PLANX_OVERLAYS = [
  { key: 'gtfsShapes', contextKey: 'contextual-gtfs', label: 'GTFS routes', description: 'Ahmedabad transit route shapes', layers: [
    { id: 'gtfs-shapes-line', type: 'line', source: 'planx-gtfsShapes', layout: hidden, paint: { 'line-color': '#6b7280', 'line-opacity': 0.28, 'line-width': 1.5 } },
    { id: 'gtfs-shapes-selected-line', type: 'line', source: 'planx-gtfsShapes', layout: hidden, filter: ['==', ['get', 'route_id'], '__no_selected_route__'], paint: { 'line-color': '#6f2f24', 'line-opacity': 0.95, 'line-width': 3 } },
  ] },
  { key: 'gtfsStops', contextKey: 'contextual-gtfs', label: 'GTFS stops', description: 'Transit stops from the supplied GTFS feed', layers: [{ id: 'gtfs-stops-circle', type: 'circle', source: 'planx-gtfsStops', layout: hidden, paint: { 'circle-radius': 4, 'circle-color': '#b45309', 'circle-opacity': 0.9 } }] },
  { key: 'gtfsServiceDay', exclusiveGroup: 'gtfs-service-intensity', contextKey: 'contextual-gtfs', label: 'Whole service day', description: 'All scheduled departures per stop across the GTFS service day', layers: [serviceIntensityLayer('gtfs-service-day-circle', 'daily_departures')] },
  { key: 'gtfsMorningPeak', exclusiveGroup: 'gtfs-service-intensity', contextKey: 'contextual-gtfs', label: 'Morning peak (08:00–10:00)', description: 'Scheduled departures per stop from 08:00 to before 10:00', layers: [serviceIntensityLayer('gtfs-morning-peak-circle', 'morning_peak_departures')] },
  { key: 'gtfsEveningPeak', exclusiveGroup: 'gtfs-service-intensity', contextKey: 'contextual-gtfs', label: 'Evening peak (17:00–19:00)', description: 'Scheduled departures per stop from 17:00 to before 19:00', layers: [serviceIntensityLayer('gtfs-evening-peak-circle', 'evening_peak_departures')] },
  { key: 'gtfsDeparturesPerHour', exclusiveGroup: 'gtfs-service-intensity', contextKey: 'contextual-gtfs', label: 'Average departures per hour', description: 'Whole-day departures per stop divided by the GTFS service-day span', layers: [serviceIntensityLayer('gtfs-departures-per-hour-circle', 'departures_per_hour')] },
  { key: 'transitIsochrones', featured: true, contextKey: 'contextual-gtfs', label: '15-minute route-reach walking catchment', description: 'Click a GTFS stop: include stops within a 5-minute street-network walk, then map 15-minute street-network walking isochrones from every stop on their routes', layers: [
    { id: 'transit-isochrone-15-fill', type: 'fill', source: 'planx-transitIsochrone15', layout: hidden, paint: { 'fill-color': '#94412f', 'fill-opacity': 0.35, 'fill-outline-color': '#6f2f24' } },
    { id: 'transit-isochrone-direct-15-fill', type: 'fill', source: 'planx-transitIsochroneDirect15', layout: hidden, paint: { 'fill-color': '#16a34a', 'fill-opacity': 0.35, 'fill-outline-color': '#15803d' } },
    { id: 'transit-isochrone-selected-route-line', type: 'line', source: 'planx-gtfsShapes', layout: hidden, filter: ['==', ['get', 'route_id'], '__no_selected_route__'], paint: { 'line-color': '#6f2f24', 'line-opacity': 0.95, 'line-width': 3 } },
    { id: 'transit-isochrone-origin-circle', type: 'circle', source: 'planx-gtfsStops', layout: hidden, paint: { 'circle-radius': 3, 'circle-color': '#ffffff', 'circle-stroke-color': '#6f2f24', 'circle-stroke-width': 0.8, 'circle-opacity': 0.45, 'circle-stroke-opacity': 0.75 } },
    { id: 'transit-isochrone-route-stops-circle', type: 'circle', source: 'planx-transitIsochroneRouteStops', layout: hidden, paint: { 'circle-radius': 4, 'circle-color': ['case', ['get', 'seed_stop'], '#f59e0b', 'rgba(148, 65, 47, 0)'], 'circle-stroke-color': ['case', ['get', 'seed_stop'], '#ffffff', '#6f2f24'], 'circle-stroke-width': ['case', ['get', 'seed_stop'], 1, 2], 'circle-stroke-opacity': ['case', ['get', 'seed_stop'], 1, 0.6] } },
    { id: 'transit-isochrone-selected-circle', type: 'circle', source: 'planx-gtfsStops', layout: hidden, filter: ['==', ['get', 'stop_id'], ''], paint: { 'circle-radius': 8, 'circle-color': '#f97316', 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 2 } },
  ] },
  { key: 'floodRiskZones', contextKey: 'contextual-vedas', label: 'Urban flood-risk zones', description: 'Provisional VEDAS/ISRO zones classified by the supplied uf_risk attribute', layers: [{
    id: 'flood-risk-zones-fill', type: 'fill', source: 'planx-floodRiskZones', layout: hidden, paint: {
      'fill-color': ['match', ['get', 'uf_risk'], 'Very High Risk Areas', '#7f0000', 'High Risk Areas', '#d7301f', 'Moderate Risk Areas', '#fdbb84', '#9ca3af'],
      'fill-opacity': 0.42,
      'fill-outline-color': '#6b1d16',
    },
  }] },
  { key: 'tpsProvisional', contextKey: 'supplied-external', label: 'Provisional town-planning schemes', description: 'Optional provisional TPS boundaries; click a boundary for an exact polygon Local Area Profile.', layers: [
    { id: 'tps-provisional-fill', type: 'fill', source: 'planx-tpsProvisional', layout: hidden, paint: { 'fill-color': '#94412f', 'fill-opacity': 0.12, 'fill-outline-color': '#6f2f24' } },
    { id: 'tps-provisional-line', type: 'line', source: 'planx-tpsProvisional', layout: hidden, paint: { 'line-color': '#6f2f24', 'line-width': 1.3 } },
  ] },
  { key: 'centrality', contextKey: 'full-study-current', label: 'Network centrality (full prepared network)', description: '135,115 analysed edges; betweenness uses 500 sampled sources and is not an all-pairs metric', layers: [line('planx-centrality-line', 'planx-centrality', 'betweenness', '#2563eb')] },


  { key: 'heatRisk', contextKey: 'current-study-proxy', label: 'Heat-risk morphology proxy', description: 'Published heat_risk morphology proxy based on 30,000 buildings and 35 green spaces; not observed heat', layers: [{ id: 'planx-heat-risk-fill', type: 'fill', source: 'planx-heatRisk', layout: hidden, paint: { 'fill-color': '#ea580c', 'fill-opacity': 0.3 } }] },
  { key: 'shadowCasting', contextKey: 'unverified-height', label: 'Shadow casting', description: 'DSM shadow mask at 08:00 local time on June 21, 2026', layers: [{ id: 'planx-shadow-casting-raster', type: 'raster', source: 'planx-shadowCasting', layout: hidden, paint: { 'raster-opacity': 0.55 } }] },
  { key: 'sunHours', contextKey: 'unverified-height', label: 'Sun hours', description: 'DSM direct-sun hours on June 21, 2026', layers: [{ id: 'planx-sun-hours-raster', type: 'raster', source: 'planx-sunHours', layout: hidden, paint: { 'raster-opacity': 0.5 } }] },
  { key: 'skyViewFactor', contextKey: 'unverified-height', label: 'Sky view factor', description: 'DSM sky-hemisphere visibility at 30 m resolution', layers: [{ id: 'planx-sky-view-factor-raster', type: 'raster', source: 'planx-skyViewFactor', layout: hidden, paint: { 'raster-opacity': 0.5 } }] },
  { key: 'solarIrradiation', contextKey: 'unverified-height', label: 'Solar irradiation', description: 'Clear-sky daily irradiation on June 21, 2026', layers: [{ id: 'planx-solar-irradiation-raster', type: 'raster', source: 'planx-solarIrradiation', layout: hidden, paint: { 'raster-opacity': 0.5 } }] },
  { key: 'environmentSurfaceTemperature', contextKey: 'full-study-current', label: 'Surface temperature raster', description: 'Existing Landsat hot-season surface-temperature raster', layers: [{ id: 'environment-surface-temperature-raster', type: 'raster', source: 'planx-environmentSurfaceTemperature', layout: hidden, paint: { 'raster-opacity': 0.5 } }] },
  { key: 'environmentNdvi', contextKey: 'full-study-current', label: 'NDVI raster', description: 'Existing Sentinel-2 hot-season NDVI raster', layers: [{ id: 'environment-ndvi-raster', type: 'raster', source: 'planx-environmentNdvi', layout: hidden, paint: { 'raster-opacity': 0.5 } }] },
  { key: 'environmentVegetationFraction', contextKey: 'full-study-current', label: 'Vegetation fraction raster', description: 'Focal fraction of NDVI-positive pixels in the surrounding raster window', layers: [{ id: 'environment-vegetation-fraction-raster', type: 'raster', source: 'planx-environmentVegetationFraction', layout: hidden, paint: { 'raster-opacity': 0.5 } }] },
  { key: 'environmentHeatGreenPriority', contextKey: 'full-study-current', label: 'Heat–green priority raster', description: 'Relative heat and greenery priority derived from the existing environment rasters', layers: [{ id: 'environment-heat-green-priority-raster', type: 'raster', source: 'planx-environmentHeatGreenPriority', layout: hidden, paint: { 'raster-opacity': 0.5 } }] },
  { key: 'buildingHeight', contextKey: 'modelled-building-height', label: '2023 modelled building height', description: 'Overview at 30 m; fine detail appears when zoomed in at ~4 m effective resolution', layers: [
    { ...buildingHeightLayers.overview, source: 'planx-buildingHeight' },
    ...buildingHeightLayers.fine,
  ] },


  ...POI_DEFINITIONS.map(([type, label, color]) => ({ key: `poi-${type}`, contextKey: 'contextual-osm', label, description: `Mapped OpenStreetMap ${label.toLowerCase()}`, layers: [{ id: `poi-${type}-circle`, type: 'circle', source: 'planx-publicPois', layout: hidden, filter: ['==', ['get', 'poi_type'], type], paint: { 'circle-radius': 4, 'circle-color': color, 'circle-opacity': 0.9 } }] })),
  { key: 'developmentPlan', controlFinal: true, contextKey: 'supplied-unverified-experimental', label: 'Development plan', description: 'ARPM Studio, Development Plan for Ahmedabad 2041 (https://arpm.studio/projects/ahmedabad-dp-2041). Visually unchanged supplied raster; supplied, unverified experimental context only.', layers: [{ id: 'development-plan-raster', type: 'raster', source: 'planx-developmentPlan', layout: hidden, paint: { 'raster-opacity': 1 } }] },
]

export const SPACE_SYNTAX_CONTEXT_KEY = 'supplied-external'
export const SPACE_SYNTAX_LAYER = { id: 'space-syntax-line', type: 'line', source: 'planx-spaceSyntax', layout: hidden, paint: { 'line-color': '#440154', 'line-width': 1.6, 'line-opacity': 0.82 } }
export const SPACE_SYNTAX_POINT_LAYER = { id: 'space-syntax-point', type: 'circle', source: 'planx-spaceSyntaxPoints', layout: hidden, paint: { 'circle-radius': 3, 'circle-color': '#440154', 'circle-opacity': 0.85 } }

export const NO_DATA_COLOR = '#9ca3af'

export function buildClassificationExpression(property, classification) {
  if (!classification) return NO_DATA_COLOR
  const value = ['to-number', ['get', property]]
  let expression
  if (classification.method === 'categorical') {
    expression = ['case', ...classification.values.flatMap((item, index) => [['==', value, item], classification.palette[index]]), NO_DATA_COLOR]
  } else if (classification.method === 'constant') {
    expression = classification.palette?.[0] || NO_DATA_COLOR
  } else if (classification.method === 'quantile') {
    expression = ['step', value, classification.palette[0], ...(classification.breaks || []).flatMap((breakValue, index) => [breakValue, classification.palette[index + 1]])]
  } else {
    return NO_DATA_COLOR
  }
  return ['case', ['any', ['!', ['has', property]], ['==', ['get', property], null]], NO_DATA_COLOR, expression]
}

export function spaceSyntaxPaint(property, metadata) {
  const classification = metadata?.overlay_classifications?.spaceSyntax?.[property]
  return { property, color: buildClassificationExpression(property, classification) }
}

export function spaceSyntaxVisibilityUpdates(property) {
  return [
    ['space-syntax-line', property !== 'off' && property !== 'betweenness' ? 'visible' : 'none'],
    ['space-syntax-point', property === 'betweenness' ? 'visible' : 'none'],
  ]
}

export function spaceSyntaxClassificationNote(property, metadata) {
  const classification = metadata?.overlay_classifications?.spaceSyntax?.[property]
  if (!classification) return 'No classification metadata.'
  const count = Number(classification.class_count ?? 0)
  const noun = count === 1 ? 'class' : 'classes'
  return `${classification.method} method; ${count} effective ${noun}. ${classification.note ?? ''}`.trim()
}

export function overlayRegistration(overlays, sources, activeKeys) {
  const activeOverlays = overlays.filter(({ key }) => activeKeys.has(key))
  const sourceNames = new Set(activeOverlays.flatMap(({ layers }) => layers.map(({ source }) => source.replace(/^planx-/, ''))))
  return {
    sources: Object.entries(sources).filter(([key]) => sourceNames.has(key)),
    layers: activeOverlays.flatMap(({ layers }) => layers),
  }
}

export function applyPlanxClassifications(map, metadata) {
  for (const [layerId, overlayKey, property] of [
    ['planx-centrality-line', 'centrality', 'betweenness'],
    ['planx-heat-risk-fill', 'heatRisk', 'heat_risk'],
    ['gtfs-service-day-circle', 'gtfsServiceDay', 'daily_departures'],
    ['gtfs-morning-peak-circle', 'gtfsMorningPeak', 'morning_peak_departures'],
    ['gtfs-evening-peak-circle', 'gtfsEveningPeak', 'evening_peak_departures'],
    ['gtfs-departures-per-hour-circle', 'gtfsDeparturesPerHour', 'departures_per_hour'],
  ]) {
    if (!map.getLayer(layerId)) continue
    const paintProperty = layerId === 'planx-heat-risk-fill' ? 'fill-color' : layerId.startsWith('gtfs-') ? 'circle-color' : 'line-color'
    map.setPaintProperty(layerId, paintProperty, buildClassificationExpression(property, metadata?.overlay_classifications?.[overlayKey]?.[property]))
  }
}

export function activateExclusiveOverlay(activeKeys, overlays, key) {
  const next = new Set(activeKeys)
  if (next.has(key)) {
    next.delete(key)
    return next
  }
  const selected = overlays.find((overlay) => overlay.key === key)
  if (selected?.exclusiveGroup) {
    for (const overlay of overlays) {
      if (overlay.exclusiveGroup === selected.exclusiveGroup) next.delete(overlay.key)
    }
  }
  next.add(key)
  return next
}

const GTFS_CONTROL_ORDER = new Map([
  ['gtfsShapes', 0],
  ['gtfsStops', 1],
  ['gtfsServiceDay', 2],
  ['gtfsMorningPeak', 3],
  ['gtfsEveningPeak', 4],
  ['gtfsDeparturesPerHour', 5],
  ['transitIsochrones', 6],
])

export function overlayControlCategory(overlay) {
  if (overlay.key.startsWith('poi-')) return 'Public-interest POIs'
  if (overlay.key.startsWith('gtfs') || overlay.key.startsWith('transit')) return 'Transit'
  if (overlay.key.startsWith('environment') || overlay.key === 'buildingHeight' || ['floodRiskZones', 'heatRisk', 'shadowCasting', 'sunHours', 'skyViewFactor', 'solarIrradiation'].includes(overlay.key)) return 'Environment'
  return 'Networks'
}

export function orderedPlanxOverlays(overlays) {
  return [...overlays].sort((a, b) => {
    const finalOrder = Number(Boolean(a.controlFinal)) - Number(Boolean(b.controlFinal))
    if (finalOrder) return finalOrder
    const categoryOrder = overlayControlCategory(a).localeCompare(overlayControlCategory(b))
    if (categoryOrder) return categoryOrder
    const rankOrder = (GTFS_CONTROL_ORDER.get(a.key) ?? 100) - (GTFS_CONTROL_ORDER.get(b.key) ?? 100)
    return rankOrder || a.label.localeCompare(b.label)
  })
}

export function applicationLayerOrder(overlays, activeKeys) {
  const active = overlays.filter(({ key }) => activeKeys.has(key))
  const developmentPlan = active.filter(({ key }) => key === 'developmentPlan')
  const otherOverlays = active.filter(({ key }) => key !== 'developmentPlan')
  return [...developmentPlan, ...otherOverlays].flatMap(({ layers }) => layers.map(({ id }) => id))
}

export function reorderPlanxLayers(map, overlays, activeKeys, baseLayerAnchorId) {
  const layerIds = applicationLayerOrder(overlays, activeKeys)
  const developmentPlanLayerId = layerIds.find((layerId) => layerId === 'development-plan-raster')
  if (!developmentPlanLayerId || (map.getLayer && !map.getLayer(developmentPlanLayerId))) return
  const firstOtherApplicationLayerId = layerIds.find((layerId) => layerId !== developmentPlanLayerId)
  map.moveLayer(developmentPlanLayerId, baseLayerAnchorId ?? firstOtherApplicationLayerId)
}

export function overlayControlSubheading(overlay) {
  if (['gtfsShapes', 'gtfsStops'].includes(overlay.key)) return 'GTFS network'
  if (overlay.exclusiveGroup === 'gtfs-service-intensity') return 'Service intensity'
  if (overlay.key === 'transitIsochrones') return 'Route-reach walking catchment'
  return null
}

export function planxVisibilityUpdates(overlays, activeKeys) { return overlays.flatMap((overlay) => overlay.layers.map((layer) => [layer.id, activeKeys.has(overlay.key) ? 'visible' : 'none'])) }
export function planxSummaryLabel(overlays, activeKeys, metadata) {
  const active = overlays.filter((overlay) => activeKeys.has(overlay.key))
  if (active.length > 3) {
    const counts = new Map()
    for (const overlay of active) {
      const contextKey = resolveItemContextKey(metadata, overlay, 'overlay')
      const label = resolveContext(metadata, contextKey).scopeLabel
      counts.set(label, (counts.get(label) ?? 0) + 1)
    }
    const scopes = [...counts].map(([label, count]) => `${label}: ${count}`).join(' · ')
    return `Map layers: ${active.length} active — ${scopes}`
  }
  const labels = active.map((overlay) => {
    const contextKey = resolveItemContextKey(metadata, overlay, 'overlay')
    const context = resolveContext(metadata, contextKey)
    return `${overlay.label} [${context.scopeLabel} · ${context.statusLabel}]`
  })
  return `Map layers: ${labels.join(' · ')}`
}
