import { describe, expect, it } from 'vitest'

import { PLANX_OVERLAYS, PLANX_SOURCES, SPACE_SYNTAX_FIELDS, activateExclusiveOverlay, applicationLayerOrder, buildClassificationExpression, orderedPlanxOverlays, overlayControlCategory, overlayControlSubheading, overlayRegistration, planxSummaryLabel, planxVisibilityUpdates, reorderPlanxLayers, spaceSyntaxPaint, spaceSyntaxVisibilityUpdates, spaceSyntaxClassificationNote } from './planx_layers.js'

describe('map overlay definitions', () => {
  it('keeps every published layer off by default', () => {
    expect(PLANX_OVERLAYS.length).toBeGreaterThan(2)
    for (const overlay of PLANX_OVERLAYS) {
      expect(overlay.key).toBeTruthy()
      expect(overlay.label).toBeTruthy()
      expect(overlay.layers.every((layer) => layer.layout?.visibility === 'none')).toBe(true)
    }
  })

  it('publishes separate GTFS sources', () => {
    expect(PLANX_SOURCES.gtfsStops.data).toBe('./data/gtfs-stops.geojson')
    expect(PLANX_SOURCES.gtfsShapes.data).toBe('./data/gtfs-shapes.geojson')
    expect(PLANX_SOURCES.gtfsServiceIntensity.data).toBe('./data/gtfs-service-intensity.geojson')
    expect(PLANX_SOURCES.publicPois.data).toBe('./data/pois.geojson')
  })

  it('publishes the supplied development-plan image unchanged as an unverified experimental overlay', () => {
    expect(PLANX_SOURCES.developmentPlan).toEqual({
      type: 'image',
      url: './data/development-plan.png',
      coordinates: [
        [72.175196139126, 23.364584536618],
        [72.860609370435, 23.364584536618],
        [72.860609370435, 22.74362328497],
        [72.175196139126, 22.74362328497],
      ],
    })
    const overlay = PLANX_OVERLAYS.find(({ key }) => key === 'developmentPlan')
    expect(overlay).toMatchObject({
      contextKey: 'supplied-unverified-experimental',
      label: 'Development plan',
      description: expect.stringContaining('supplied'),
      layers: [{ id: 'development-plan-raster', type: 'raster', source: 'planx-developmentPlan', layout: { visibility: 'none' } }],
    })
    expect(overlayRegistration(PLANX_OVERLAYS, PLANX_SOURCES, new Set(['developmentPlan']))).toMatchObject({
      sources: [['developmentPlan', PLANX_SOURCES.developmentPlan]],
      layers: [overlay.layers[0]],
    })
    expect(overlay.description).toContain('ARPM Studio')
    expect(overlay.description).toContain('Development Plan for Ahmedabad 2041')
    expect(overlay.description).toContain('https://arpm.studio/projects/ahmedabad-dp-2041')
  })

  it('excludes Jantri from published sources and overlays', () => {
    expect(Object.keys(PLANX_SOURCES).some((key) => key.toLowerCase().includes('jantri'))).toBe(false)
    expect(PLANX_OVERLAYS.some(({ key }) => key.toLowerCase().includes('jantri'))).toBe(false)
  })

  it('orders the development-plan raster below every application-controlled layer', () => {
    const ordered = applicationLayerOrder(PLANX_OVERLAYS, new Set(['developmentPlan', 'gtfsStops', 'centrality']))
    expect(ordered[0]).toBe('development-plan-raster')
    expect(ordered).toEqual(['development-plan-raster', 'gtfs-stops-circle', 'planx-centrality-line'])
  })

  it('moves only the development plan below the first OSM road anchor', () => {
    const calls = []
    const map = { getLayer: () => true, moveLayer: (...args) => calls.push(args) }
    reorderPlanxLayers(map, PLANX_OVERLAYS, new Set(['developmentPlan', 'gtfsStops', 'centrality']), 'road_minor')
    expect(calls).toEqual([['development-plan-raster', 'road_minor']])
  })

  it('keeps the development-plan control final regardless of category sorting', () => {
    const ordered = orderedPlanxOverlays(PLANX_OVERLAYS)
    expect(ordered.at(-1).key).toBe('developmentPlan')
  })

  it('publishes VEDAS flood-risk zones with their source risk classes intact', () => {
    expect(PLANX_SOURCES.floodRiskZones).toEqual({ type: 'geojson', data: './data/ahm-urban-flood-risk-zones.geojson' })
    const overlay = PLANX_OVERLAYS.find(({ key }) => key === 'floodRiskZones')
    expect(overlay).toMatchObject({
      contextKey: 'contextual-vedas',
      label: 'Urban flood-risk zones',
    })
    expect(overlay.layers).toEqual([
      expect.objectContaining({
        id: 'flood-risk-zones-fill',
        type: 'fill',
        source: 'planx-floodRiskZones',
        layout: { visibility: 'none' },
        paint: expect.objectContaining({
          'fill-color': [
            'match', ['get', 'uf_risk'],
            'Very High Risk Areas', '#7f0000',
            'High Risk Areas', '#d7301f',
            'Moderate Risk Areas', '#fdbb84',
            '#9ca3af',
          ],
        }),
      }),
    ])
  })

  it('places the urban flood-risk control under Environment', () => {
    expect(overlayControlCategory(PLANX_OVERLAYS.find(({ key }) => key === 'floodRiskZones'))).toBe('Environment')
  })

  it('publishes four mutually exclusive service-intensity measures', () => {
    const keys = ['gtfsServiceDay', 'gtfsMorningPeak', 'gtfsEveningPeak', 'gtfsDeparturesPerHour']
    const overlays = keys.map((key) => PLANX_OVERLAYS.find((overlay) => overlay.key === key))
    expect(overlays.map(({ label }) => label)).toEqual([
      'Whole service day',
      'Morning peak (08:00–10:00)',
      'Evening peak (17:00–19:00)',
      'Average departures per hour',
    ])
    expect(new Set(overlays.map(({ exclusiveGroup }) => exclusiveGroup))).toEqual(new Set(['gtfs-service-intensity']))
    expect(JSON.stringify(overlays.map(({ layers }) => layers))).toContain('daily_departures')
    expect(JSON.stringify(overlays.map(({ layers }) => layers))).toContain('morning_peak_departures')
    expect(JSON.stringify(overlays.map(({ layers }) => layers))).toContain('evening_peak_departures')
    expect(JSON.stringify(overlays.map(({ layers }) => layers))).toContain('departures_per_hour')
    expect(PLANX_OVERLAYS.some(({ key }) => key === 'gtfsServiceIntensity')).toBe(false)
    expect(PLANX_OVERLAYS.some(({ key }) => key === 'transitFrequency')).toBe(false)
  })

  it('places GTFS routes and stops before a service-intensity subgroup', () => {
    const transit = orderedPlanxOverlays(PLANX_OVERLAYS).filter(({ key }) => key.startsWith('gtfs'))
    expect(transit.map(({ key }) => key)).toEqual([
      'gtfsShapes',
      'gtfsStops',
      'gtfsServiceDay',
      'gtfsMorningPeak',
      'gtfsEveningPeak',
      'gtfsDeparturesPerHour',
    ])
    expect(transit.map(overlayControlSubheading)).toEqual([
      'GTFS network',
      'GTFS network',
      'Service intensity',
      'Service intensity',
      'Service intensity',
      'Service intensity',
    ])
  })

  it('activates only one overlay from an exclusive service-intensity group', () => {
    const active = activateExclusiveOverlay(new Set(['centrality', 'gtfsMorningPeak']), PLANX_OVERLAYS, 'gtfsEveningPeak')
    expect([...active]).toEqual(['centrality', 'gtfsEveningPeak'])
    expect([...activateExclusiveOverlay(active, PLANX_OVERLAYS, 'gtfsEveningPeak')]).toEqual(['centrality'])
  })

  it('publishes building height as a raster overlay, never a building attribute', () => {
    expect(PLANX_SOURCES.buildingHeight).toMatchObject({ type: 'image', url: './data/building-height-2023.png' })
    expect(PLANX_OVERLAYS.find(({ key }) => key === 'buildingHeight')).toMatchObject({
      contextKey: 'modelled-building-height',
      label: '2023 modelled building height',
    })
    expect(PLANX_OVERLAYS.find(({ key }) => key === 'buildingHeight').description).toContain('30 m')
  })

  it('publishes only parks and schools from the categorized POI source', () => {
    const poiOverlays = PLANX_OVERLAYS.filter(({ key }) => key.startsWith('poi-'))
    expect(poiOverlays.map(({ key }) => key)).toEqual(['poi-parks', 'poi-schools'])
    expect(new Set(poiOverlays.map(({ layers: [layer] }) => layer.source))).toEqual(new Set(['planx-publicPois']))
    expect(poiOverlays.every(({ layers: [layer] }) => layer.filter?.[0] === '==')).toBe(true)
    expect(PLANX_OVERLAYS.some(({ key }) => key === 'transitAccess')).toBe(false)
    expect(PLANX_SOURCES.transitAccess).toBeUndefined()
    expect(PLANX_OVERLAYS.some(({ key }) => key === 'greenAccess')).toBe(false)
    expect(PLANX_SOURCES.greenAccess).toBeUndefined()
  })

  it('publishes click-selectable route-reach walking catchment layers', () => {
    const overlay = PLANX_OVERLAYS.find(({ key }) => key === 'transitIsochrones')
    expect(overlay.label).toContain('15-minute')
    expect(overlay.featured).toBe(true)
    expect(overlay.layers.map(({ id }) => id)).toEqual([
      'transit-isochrone-15-fill',
      'transit-isochrone-direct-15-fill',
      'transit-isochrone-selected-route-line',
      'transit-isochrone-origin-circle',
      'transit-isochrone-route-stops-circle',
      'transit-isochrone-selected-circle',
    ])
    expect(overlay.layers.find(({ id }) => id === 'transit-isochrone-15-fill').paint['fill-opacity']).toBe(0.35)
    expect(overlay.layers.find(({ id }) => id === 'transit-isochrone-15-fill').paint).toMatchObject({ 'fill-color': '#94412f', 'fill-outline-color': '#6f2f24' })
    expect(overlay.layers.find(({ id }) => id === 'transit-isochrone-direct-15-fill').paint['fill-opacity']).toBe(0.35)
    expect(overlay.layers.find(({ id }) => id === 'transit-isochrone-route-stops-circle').paint).toMatchObject({
      'circle-color': ['case', ['get', 'seed_stop'], '#f59e0b', 'rgba(148, 65, 47, 0)'],
      'circle-stroke-color': ['case', ['get', 'seed_stop'], '#ffffff', '#6f2f24'],
      'circle-stroke-width': ['case', ['get', 'seed_stop'], 1, 2],
      'circle-stroke-opacity': ['case', ['get', 'seed_stop'], 1, 0.6],
    })
    expect(PLANX_SOURCES.transitIsochrone15.data).toEqual({ type: 'FeatureCollection', features: [] })
    expect(PLANX_SOURCES.transitIsochroneRouteStops.data).toEqual({ type: 'FeatureCollection', features: [] })
  })

  it('uses the brand brown for provisional TPS fill and line without changing opacity or width', () => {
    const layers = PLANX_OVERLAYS.find(({ key }) => key === 'tpsProvisional').layers
    expect(layers[0].paint).toMatchObject({ 'fill-color': '#94412f', 'fill-opacity': 0.12, 'fill-outline-color': '#6f2f24' })
    expect(layers[1].paint).toMatchObject({ 'line-color': '#6f2f24', 'line-width': 1.3 })
  })

  it('builds independent on/off visibility updates', () => {
    const updates = planxVisibilityUpdates(PLANX_OVERLAYS, new Set(['gtfsShapes']))
    expect(updates.find(([id]) => id === 'gtfs-shapes-line')).toEqual(['gtfs-shapes-line', 'visible'])
    expect(updates.find(([id]) => id === 'gtfs-stops-circle')).toEqual(['gtfs-stops-circle', 'none'])
  })

  it('registers only the selected overlay sources and layers', () => {
    const height = overlayRegistration(PLANX_OVERLAYS, PLANX_SOURCES, new Set(['buildingHeight']))
    expect(height.sources.map(([key]) => key)).toEqual(['buildingHeight', 'buildingHeightFine8', 'buildingHeightFine11', 'buildingHeightFine14', 'buildingHeightFine16'])
    expect(height.layers.map(({ id }) => id)).toEqual(PLANX_OVERLAYS.find(({ key }) => key === 'buildingHeight').layers.map(({ id }) => id))

    const transit = overlayRegistration(PLANX_OVERLAYS, PLANX_SOURCES, new Set(['gtfsStops']))
    expect(transit.sources.map(([key]) => key)).toEqual(['gtfsStops'])
    expect(transit.layers.map(({ id }) => id)).toEqual(['gtfs-stops-circle'])
  })

  it('summarizes active layers with visible scope and supports all-off state', () => {
    expect(planxSummaryLabel(PLANX_OVERLAYS, new Set())).toBe('Map layers: ')
    const metadata = {
      overlay_contexts: { gtfsShapes: 'contextual-gtfs', gtfsStops: 'contextual-gtfs' },
      contexts: { 'contextual-gtfs': { scopeLabel: 'Contextual external', statusLabel: 'Supplied feed' } },
    }
    expect(planxSummaryLabel(PLANX_OVERLAYS, new Set(['gtfsShapes', 'gtfsStops']), metadata)).toBe('Map layers: GTFS routes [Contextual external · Supplied feed] · GTFS stops [Contextual external · Supplied feed]')
  })

  it('uses truthful quantified labels for full-study, proxy, and scenario products', () => {
    expect(PLANX_OVERLAYS.find(({ key }) => key === 'centrality')).toMatchObject({ label: 'Network centrality (full prepared network)', description: expect.stringContaining('135,115 analysed edges') })
    expect(PLANX_OVERLAYS.find(({ key }) => key === 'heatRisk')).toMatchObject({ label: 'Heat-risk morphology proxy' })

    expect(PLANX_OVERLAYS.some(({ key }) => key === 'linkCriticality')).toBe(false)
    expect(PLANX_SOURCES.linkCriticality).toBeUndefined()
  })

  it('uses metadata overlay assignments when summarizing active layers', () => {
    const metadata = {
      overlay_contexts: { gtfsShapes: 'current-study-bounded', gtfsStops: 'current-study-bounded', centrality: 'current-study-bounded' },
      contexts: {
        'current-study-bounded': { scopeLabel: 'Current-study bounded' },
        'contextual-gtfs': { scopeLabel: 'Contextual GTFS' },
      },
    }
    expect(planxSummaryLabel(PLANX_OVERLAYS, new Set(['gtfsShapes', 'gtfsStops', 'centrality', 'heatRisk']), metadata)).toContain('Current-study bounded: 3')
  })

  it('builds a no-data-safe step expression from quantile metadata', () => {
    const expression = buildClassificationExpression('betweenness', { method: 'quantile', breaks: [2, 4], palette: ['a', 'b', 'c'] })
    expect(expression).toEqual(['case', ['any', ['!', ['has', 'betweenness']], ['==', ['get', 'betweenness'], null]], '#9ca3af', ['step', ['to-number', ['get', 'betweenness']], 'a', 2, 'b', 4, 'c']])
  })

  it('builds a no-data-safe heat-risk step expression from published metadata', () => {
    const expression = buildClassificationExpression('heat_risk', { method: 'quantile', breaks: [50, 75], palette: ['#ffffcc', '#fd8d3c', '#800026'] })
    expect(expression).toEqual(['case', ['any', ['!', ['has', 'heat_risk']], ['==', ['get', 'heat_risk'], null]], '#9ca3af', ['step', ['to-number', ['get', 'heat_risk']], '#ffffcc', 50, '#fd8d3c', 75, '#800026']])
  })


  it('renders betweenness as points and every other selected field as lines', () => {
    expect(spaceSyntaxVisibilityUpdates('betweenness')).toEqual([['space-syntax-line', 'none'], ['space-syntax-point', 'visible']])
    expect(spaceSyntaxVisibilityUpdates('closeness')).toEqual([['space-syntax-line', 'visible'], ['space-syntax-point', 'none']])
    expect(spaceSyntaxVisibilityUpdates('off')).toEqual([['space-syntax-line', 'none'], ['space-syntax-point', 'none']])
  })

  it('describes the selected field method and effective class count', () => {
    const metadata = { overlay_classifications: { spaceSyntax: { closeness: { method: 'constant', class_count: 1, note: 'Constant field; no variation.' } } } }
    expect(spaceSyntaxClassificationNote('closeness', metadata)).toContain('constant')
    expect(spaceSyntaxClassificationNote('closeness', metadata)).toContain('1 effective class')
  })

  it('changes selected space-syntax property and shared classification thresholds', () => {
    const metadata = { overlay_classifications: { spaceSyntax: { betweenness: { method: 'quantile', breaks: [1], palette: ['a', 'b'] } } } }
    const paint = spaceSyntaxPaint('betweenness', metadata)
    expect(paint.property).toBe('betweenness')
    expect(JSON.stringify(paint.color)).toContain('1')
  })

  it('has no fixed 0/0.5/1 domain in target renderer definitions', () => {
    expect(JSON.stringify(PLANX_OVERLAYS.filter(({ key }) => ['centrality', 'centrality'].includes(key)))).not.toContain('0.5')
  })
})
