import { describe, expect, it } from 'vitest'

import {
  buildBuildingsPresentation,
  buildEnvironmentPresentation,
  buildParksEducationPresentation,
  buildPublicTransportPresentation,
  buildSpaceSyntaxPresentation,
  buildStreetsPresentation,
} from './profile_presentations.js'

const histogram = {
  bins: [0, 25, 100],
  counts: [2, 1],
  method: 'fixed',
  interval: 'left_closed_right_open_except_last',
}

const sections = {
  buildings: {
    status: 'available',
    data: {
      buildingCount: 4,
      footprintCoverageM2: 1250,
      footprintCoveragePct: 12.5,
      footprintAreaM2: { status: 'available', mean: 41.5, median: 36, histogram },
      buildingMetrics: {
        compactness: { status: 'available', mean: 0.71, median: 0.7, min: 0.4, max: 0.9 },
        convexity: { status: 'available', mean: 0.88, median: 0.9, min: 0.7, max: 1 },
        elongation: { status: 'available', mean: 0.22, median: 0.2, min: 0.1, max: 0.4 },
      },
    },
  },
  streetsConnectivity: {
    status: 'available',
    data: {
      clippedLengthKm: 4.2,
      intersectionDensityPerKm2: 18,
      linkNodeRatio: 1.4,
      connectedNodeRatio: 0.8,
      fixedBins: {
        streetLengthKm: { bins: [0, 1, 3], counts: [0, 0], method: 'fixed' },
      },
    },
  },
  environment: {
    status: 'available',
    data: {
      heatRisk: { status: 'available', mean: 0.6 },
      lst: { status: 'available', mean: 42, median: 41.5, unit: '°C', coveragePercentage: 90, distribution: { bins: [35, 40, 45], counts: [3, 2] }, provenance: { label: 'one-scene' } },
      ndvi: { status: 'available', mean: 0.31, median: 0.28, unit: 'index', validCoveragePct: 80, distribution: { bins: [-1, 0, 0.5, 1], counts: [1, 4, 2] }, provenance: { label: 'one-scene' } },
      vegetationFraction: { status: 'available', mean: 0.42, median: 0, unit: 'fraction', coveragePercentage: 80, provenance: { label: 'derived', threshold: 0.3 }, distribution: { bins: [0, 1, 2], counts: [2, 8] } },
      height2023: { status: 'available', mean: 8.2, median: 7.5, unit: 'm', coveragePercentage: 65, distribution: { bins: [0, 5, 10], counts: [4, 6] }, provenance: { label: 'modelled' } },
    },
  },
}

describe('profile presentation models', () => {
  it('builds building KPIs, detail rows, and a vertical footprint histogram without changing counts', () => {
    const model = buildBuildingsPresentation(sections.buildings)
    expect(model.kpis).toEqual([
      { key: 'buildingCount', label: 'Buildings', value: 4, displayValue: '4', unit: 'buildings' },
      { key: 'footprintCoverageM2', label: 'Footprint coverage area', value: 1250, displayValue: '1,250', unit: 'm²' },
      { key: 'footprintCoveragePct', label: 'Footprint coverage share', value: 12.5, displayValue: '12.5', unit: '%' },
      { key: 'medianFootprintAreaM2', label: 'Median footprint area', value: 36, displayValue: '36', unit: 'm²' },
      { key: 'meanFootprintAreaM2', label: 'Mean footprint area', value: 41.5, displayValue: '41.5', unit: 'm²' },
    ])
    expect(model.details.rows.map((row) => row.key)).toEqual(['compactness', 'convexity', 'elongation'])
    expect(model.charts[0]).toMatchObject({ key: 'footprintAreaM2', orientation: 'vertical', unit: 'm²' })
    expect(model.charts[0].bins).toEqual([
      { lower: 0, upper: 25, count: 2, percentage: 50, label: '0–<25' },
      { lower: 25, upper: 100, count: 1, percentage: 25, label: '25–100' },
      { lower: 100, upper: null, count: 1, percentage: 25, label: '>100' },
    ])
    expect(model.charts[0].totalCount).toBe(4)
  })

  it('returns unavailable buildings cleanly', () => {
    expect(buildBuildingsPresentation({ status: 'unavailable', data: null })).toEqual(expect.objectContaining({ status: 'unavailable', kpis: [], charts: [], details: { rows: [] } }))
  })

  it('presents provisional building-location metrics with Central/enriched denominators and caveats', () => {
    const model = buildBuildingsPresentation({ status: 'available', data: {
      totalLocationCount: 3, centralLocationCount: 1, enrichedLocationCount: 2,
      provisionalHeightM: { status: 'available', unit: 'm', summary: { mean: 12, median: 10, min: 4, max: 20 }, availability: { available: 2, denominator: 2 } },
      provisionalAreaM2: { status: 'available', unit: 'm²', summary: { mean: 24 }, availability: { available: 2, denominator: 2 } },
      derivedVolumeM3: { status: 'available', unit: 'm³', summary: { mean: 288 }, availability: { available: 2, denominator: 2 } },
      suhi: { status: 'unavailable', summary: {}, availability: { available: 0, denominator: 2 } },
    } })
    expect(model.kpis.map(({ label, value }) => ({ label, value }))).toEqual(expect.arrayContaining([
      { label: 'Building locations', value: 3 }, { label: 'Central locations', value: 1 }, { label: 'Enriched locations', value: 2 },
    ]))
    expect(model.metrics).toEqual(expect.arrayContaining([expect.objectContaining({ key: 'provisionalHeightM', denominator: 2 }), expect.objectContaining({ key: 'suhi', value: null, denominator: 2 })]))
    expect(model.details.rows).toEqual(expect.arrayContaining([expect.objectContaining({ key: 'provisionalHeightM', mean: 12, median: 10, min: 4, max: 20, coverageLabel: '2/2 valid', evidenceLabel: 'Provisional' })]))
    expect(model.details.rows.every((row) => row.coverageLabel && row.evidenceLabel)).toBe(true)
    expect(model.caveats.join(' ')).toMatch(/unverified/i)
  })

  it('builds three numeric distributions plus a categorical SUHI distribution and stored-area KPIs without recalculation', () => {
    const distribution = { bins: [0, 10, 20], counts: [1, 1], method: 'fixed' }
    const model = buildBuildingsPresentation({ status: 'available', data: {
      totalLocationCount: 5, centralLocationCount: 2, enrichedLocationCount: 3,
      provisionalHeightM: { unit: 'm', summary: { mean: 8 }, availability: { available: 3, denominator: 3 }, distribution },
      provisionalAreaM2: { unit: 'm²', summary: { mean: 40 }, availability: { available: 3, denominator: 3 }, distribution },
      derivedVolumeM3: { unit: 'm³', summary: { mean: 320 }, availability: { available: 3, denominator: 3 }, distribution },
      suhi: { kind: 'categorical', unit: 'unverified categorical class', summary: { dominantClass: 'High' }, availability: { available: 3, denominator: 3 }, distribution: { categories: [{ key: 'low', label: 'Low', count: 1 }, { key: 'moderate', label: 'Moderate', count: 0 }, { key: 'high', label: 'High', count: 2 }, { key: 'veryHigh', label: 'Very High', count: 0 }, { key: 'extremeHigh', label: 'Extreme High', count: 0 }], totalCount: 3 } },
      summedStoredAreaM2: 1200, storedAreaSharePct: 12.5,
      storedAreaSelectionBasis: 'Full stored area values of point-selected enriched records divided by exact circle/TPS area; Central is count-only; not footprint-union coverage.',
    } })
    expect(model.charts.map(({ key }) => key)).toEqual(['provisionalAreaM2', 'provisionalHeightM', 'derivedVolumeM3', 'suhi'])
    expect(model.charts.find(({ key }) => key === 'suhi')).toEqual(expect.objectContaining({ type: 'categorical-counts', totalCount: 3, categories: expect.arrayContaining([expect.objectContaining({ label: 'High', count: 2 })]) }))
    expect(model.charts.filter(({ key }) => key !== 'suhi').every((chart) => chart.totalCount === 3)).toBe(true)
    expect(model.charts[0].bins.at(-1)).toMatchObject({ label: '>20', count: 1 })
    expect(model.kpis).toEqual(expect.arrayContaining([
      expect.objectContaining({ key: 'summedStoredAreaM2', value: 1200 }),
      expect.objectContaining({ key: 'storedAreaSharePct', label: 'Stored building area share', value: 12.5 }),
    ]))
    expect(model.caveats).toContain('Full stored area values of point-selected enriched records divided by exact circle/TPS area; Central is count-only; not footprint-union coverage.')
  })

  it('preserves readable precision for tiny non-zero closeness values', () => {
    const model = buildSpaceSyntaxPresentation({ status: 'available', data: { centrality: { closeness: { weightedMean: 0.0018 } } } })
    expect(model.details.rows[0].displayValue).toBe('0.0018')
  })

  it('exposes street KPIs and omits misleading fixed-bin charts', () => {
    const model = buildStreetsPresentation(sections.streetsConnectivity)
    expect(model.kpis.map(({ key, value, unit }) => ({ key, value, unit }))).toEqual([
      { key: 'clippedLengthKm', value: 4.2, unit: 'km' },
      { key: 'intersectionDensityPerKm2', value: 18, unit: 'intersections/km²' },
      { key: 'linkNodeRatio', value: 1.4, unit: 'ratio' },
      { key: 'connectedNodeRatio', value: 80, unit: '%' },
    ])
    expect(model.charts).toEqual([])
  })

  it('builds environment charts, evidence labels, and two-column vegetation threshold detail', () => {
    const model = buildEnvironmentPresentation(sections.environment)
    expect(model.charts.map(({ key }) => key)).toEqual(['lst', 'ndvi', 'height2023'])
    expect(model.charts[1].bins[0]).toMatchObject({ label: '-1–<0', count: 1 })
    expect(model.metrics.find(({ key }) => key === 'lst')).toMatchObject({ label: 'Surface temperature', value: 41.5, coverageLabel: '90% valid', evidenceLabel: 'one-scene' })
    expect(model.metrics.find(({ key }) => key === 'height2023')).toMatchObject({ label: 'Modelled height (2023)', value: 7.5, coverageLabel: '65% valid', evidenceLabel: 'modelled' })
    expect(model.metrics.find(({ key }) => key === 'vegetationFraction')).toMatchObject({ value: 42, unit: '%' })
    expect(model.kpis[0]).toMatchObject({ key: 'heatRisk', unit: 'relative proxy index' })
    expect(model.charts[0]).toMatchObject({ totalCount: 5 })
    expect(model.charts[0].bins[0]).toMatchObject({ percentage: 60 })
    expect(model.details.rows).toEqual([])
    expect(model.vegetationThreshold).toEqual({
      threshold: 0.3,
      thresholdLabel: '≥ 0.3',
      unit: 'fraction',
      columns: [
        { key: 'below', label: '< 0.3', count: 2 },
        { key: 'atOrAbove', label: '≥ 0.3', count: 8 }
      ],
    })
  })

  it('builds a categorical flood-risk area chart with an explicit unavailable low class', () => {
    const model = buildEnvironmentPresentation({ status: 'available', data: {
      floodRiskArea: {
        status: 'available', unit: 'm²',
        categories: [
          { key: 'veryHigh', label: 'Very high', sourceClass: 'Very High Risk Areas', areaM2: 1200, status: 'available' },
          { key: 'high', label: 'High', sourceClass: 'High Risk Areas', areaM2: 3400, status: 'available' },
          { key: 'moderate', label: 'Moderate', sourceClass: 'Moderate Risk Areas', areaM2: 5600, status: 'available' },
          { key: 'low', label: 'Low', sourceClass: null, areaM2: null, status: 'unavailable' },
        ],
        totalClassifiedAreaM2: 10200,
        caveat: 'Low is not a source class.',
      },
    } })
    expect(model.charts.at(-1)).toEqual({
      key: 'floodRiskArea', title: 'Flood-risk area by category', type: 'categorical-area', orientation: 'vertical', unit: 'm²',
      xAxisLabel: 'Risk category', yAxisLabel: 'Area (m²)', totalValue: 10200,
      categories: [
        { key: 'veryHigh', label: 'Very high', value: 1200, displayValue: '1,200', status: 'available' },
        { key: 'high', label: 'High', value: 3400, displayValue: '3,400', status: 'available' },
        { key: 'moderate', label: 'Moderate', value: 5600, displayValue: '5,600', status: 'available' },
        { key: 'low', label: 'Low', value: null, displayValue: 'Unavailable', status: 'unavailable' },
      ],
    })
    expect(model.caveats).toContain('Low is not a source class.')
  })

  it('omits unavailable or no-bin charts and heat-risk chart when bins are absent', () => {
    const model = buildEnvironmentPresentation({ status: 'available', data: {
      heatRisk: { status: 'available', mean: 0.5 },
      lst: { status: 'unavailable', reason: 'missing' },
      ndvi: { status: 'available', mean: 0.2, distribution: { bins: [], counts: [] } },
    } })
    expect(model.charts).toEqual([])
    expect(model.validity).toEqual(expect.objectContaining({ status: 'partial' }))
  })

  it('builds separate weighted centrality and space-syntax rows with valid counts and no chart', () => {
    const model = buildSpaceSyntaxPresentation({ status: 'available', data: {
      centrality: {
        betweenness: { weightedMean: 2.5, availability: { available: 3, denominator: 4 }, weightTotal: 1200 },
        closeness: { weightedMean: 0.8, availability: { available: 4, denominator: 4 }, weightTotal: 1500 },
      },
      spaceSyntax: {
        betweenness: { weightedMean: 1.5, availability: { available: 2, denominator: 3 }, weightTotal: 900 },
      },
    } })
    expect(model.charts).toEqual([])
    expect(model.details.rows).toEqual([
      expect.objectContaining({ key: 'centrality.betweenness', source: 'centrality', metric: 'betweenness', value: 2.5, validCount: 3, denominator: 4 }),
      expect.objectContaining({ key: 'centrality.closeness', source: 'centrality', metric: 'closeness', value: 0.8, validCount: 4, denominator: 4 }),
      expect.objectContaining({ key: 'spaceSyntax.betweenness', source: 'spaceSyntax', metric: 'betweenness', value: 1.5, validCount: 2, denominator: 3 }),
    ])
    expect(model.caveats.join(' ')).toContain('clipped')
  })

  it('builds local transport metrics separately from route-associated reach in square kilometres', () => {
    const model = buildPublicTransportPresentation({ status: 'available', data: {
      stopsInsideCircle: 2,
      routesServingStopsInsideCircle: ['R1', 'R2'],
      routeStopIndexes: [1, 2, 3, 4],
      routeReachAreaM2: 1250000,
      routeReachCells: 7,
      caveats: { scheduledService: 'scheduled feed' },
    } })
    expect(model.details.rows).toEqual(expect.arrayContaining([
      expect.objectContaining({ key: 'local.stopsInsideCircle', value: 2, unit: 'stops' }),
      expect.objectContaining({ key: 'local.routesServingStopsInsideCircle', value: 2, unit: 'routes' }),
      expect.objectContaining({ key: 'routeReach.area', value: 1.25, unit: 'km²' }),
      expect.objectContaining({ key: 'routeReach.routeStopCount', value: 4, unit: 'route-stops' }),
    ]))
    expect(model.caveats.join(' ')).toContain('scheduled')
  })

  it('builds table-ready parks and schools rows with representative-point caveat', () => {
    const model = buildParksEducationPresentation({ status: 'available', data: {
      parks: { count: 5, availability: { available: 5, denominator: 6 } },
      schools: { count: 3, availability: { available: 3, denominator: 4 } },
    } })
    expect(model.details.rows).toEqual([
      expect.objectContaining({ key: 'parks', label: 'Parks', value: 5, unit: 'parks' }),
      expect.objectContaining({ key: 'schools', label: 'Schools', value: 3, unit: 'schools' }),
    ])
    expect(model.caveats.join(' ').toLowerCase()).toContain('representative')
  })

  it('handles null and omitted sections as unavailable serializable models', () => {
    expect(buildStreetsPresentation(null)).toEqual(expect.objectContaining({ status: 'unavailable', kpis: [], charts: [] }))
    expect(buildEnvironmentPresentation()).toEqual(expect.objectContaining({ status: 'unavailable', metrics: [], charts: [] }))
    expect(() => JSON.stringify(buildBuildingsPresentation(null))).not.toThrow()
  })

  it('preserves raster observations outside the displayed bin range', () => {
    const model = buildEnvironmentPresentation({ status: 'available', data: {
      lst: { status: 'available', median: 42, unit: '°C', validPixelCount: 6, distribution: { bins: [35, 40, 45], counts: [3, 2] } },
    } })
    expect(model.charts[0].bins.at(-1)).toMatchObject({ label: 'Outside 35–45', count: 1, percentage: 16.67 })
  })
})
