const BUILDING_METRICS = [
  ['compactness', 'Compactness'],
  ['convexity', 'Convexity'],
  ['elongation', 'Elongation'],
]

const ENVIRONMENT_METRICS = [
  ['lst', 'Surface temperature'],
  ['ndvi', 'NDVI'],
  ['vegetationFraction', 'Vegetation-positive fraction'],
  ['height2023', 'Modelled height (2023)'],
]

function sectionData(section) {
  if (!section) return { status: 'unavailable', data: null }
  if (Object.prototype.hasOwnProperty.call(section, 'data')) return section
  return { status: 'available', data: section }
}

function available(data) {
  return data != null && data.status !== 'unavailable'
}

function numberOrNull(value) {
  return value === null || value === undefined || !Number.isFinite(Number(value)) ? null : Number(value)
}

function display(value) {
  const number = numberOrNull(value)
  if (number === null) return 'No data'
  if (number !== 0 && Math.abs(number) < 0.01) return Number(number.toPrecision(3)).toString()
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 }).format(number)
}

function kpi(key, label, value, unit) {
  return { key, label, value: numberOrNull(value), displayValue: display(value), unit }
}

function metricSource(metric) {
  return metric?.status === 'unavailable' ? 'unavailable' : available(metric) ? 'available' : 'unavailable'
}

function coverageLabel(metric) {
  const coverage = metric?.coverage ?? metric?.validCoverage ?? metric?.coverageCount
  if (coverage && coverage.available != null && (coverage.total ?? coverage.denominator) != null) return `${coverage.available}/${coverage.total ?? coverage.denominator} valid`
  if (coverage && coverage.pct != null) return `${display(coverage.pct)}% valid`
  if (metric?.coveragePct != null) return `${display(metric.coveragePct)}% valid`
  if (metric?.coveragePercentage != null) return `${display(metric.coveragePercentage)}% valid`
  if (metric?.validCoveragePct != null) return `${display(metric.validCoveragePct)}% valid`
  return 'coverage unavailable'
}

function evidenceLabel(metric) {
  const provenance = metric?.provenance
  if (typeof provenance === 'string') return provenance
  if (provenance?.label) return String(provenance.label)
  if (metric?.accuracy) return String(metric.accuracy)
  return metricSource(metric)
}

function distributionOf(metric) {
  return metric?.distribution ?? metric?.histogram ?? null
}

function intervalLabel(lower, upper, isLast) {
  const left = display(lower)
  const right = display(upper)
  return `${left}–${isLast ? right : `<${right}`}`
}

function percentage(count, total) {
  return total > 0 ? Number((Number(count) / total * 100).toFixed(2)) : 0
}

function histogramModel(key, title, metric, unit = '', totalCount = null, outsideLabel = null) {
  const distribution = distributionOf(metric)
  const bins = distribution?.bins
  const counts = distribution?.counts
  if (!Array.isArray(bins) || !Array.isArray(counts) || bins.length < 2 || counts.length !== bins.length - 1) return null
  const observedTotal = numberOrNull(totalCount) ?? counts.reduce((sum, count) => sum + Number(count || 0), 0)
  const explicitUnderflow = Math.max(0, numberOrNull(distribution.underflow ?? distribution.underflowCount) ?? 0)
  const explicitOverflow = Math.max(0, numberOrNull(distribution.overflow ?? distribution.overflowCount) ?? 0)
  const modelBins = counts.map((count, index) => ({
    lower: numberOrNull(bins[index]),
    upper: numberOrNull(bins[index + 1]),
    count: numberOrNull(count) ?? 0,
    percentage: percentage(numberOrNull(count) ?? 0, observedTotal),
    label: intervalLabel(bins[index], bins[index + 1], index === counts.length - 1),
  }))
  const binnedCount = modelBins.reduce((sum, bin) => sum + bin.count, 0)
  const residual = Math.max(0, observedTotal - binnedCount - explicitUnderflow - explicitOverflow)
  if (explicitUnderflow > 0) modelBins.unshift({ lower: null, upper: numberOrNull(bins[0]), count: explicitUnderflow, percentage: percentage(explicitUnderflow, observedTotal), label: `<${display(bins[0])}` })
  if (explicitOverflow + residual > 0) modelBins.push({
    lower: numberOrNull(bins.at(-1)),
    upper: null,
    count: explicitOverflow + residual,
    percentage: percentage(explicitOverflow + residual, observedTotal),
    label: outsideLabel === 'overflow' ? `>${display(bins.at(-1))}` : `Outside ${display(bins[0])}–${display(bins.at(-1))}`,
  })
  return {
    key,
    title,
    orientation: 'vertical',
    unit: unit || metric?.unit || '',
    method: distribution.method ?? 'existing distribution',
    totalCount: observedTotal,
    bins: modelBins,
  }
}

function categoricalCountModel(key, title, metric) {
  const categories = metric?.distribution?.categories
  const totalCount = numberOrNull(metric?.distribution?.totalCount) ?? numberOrNull(metric?.availability?.available) ?? 0
  if (!Array.isArray(categories)) return null
  return {
    key, title, type: 'categorical-counts', orientation: 'vertical', unit: 'classes', method: 'categorical source classes', totalCount,
    categories: categories.map((category) => ({ key: category.key, label: category.label, count: numberOrNull(category.count) ?? 0, percentage: percentage(numberOrNull(category.count) ?? 0, totalCount) })),
  }
}

function validity(status, metrics, charts) {
  const availableMetrics = metrics.filter((metric) => metric.evidenceLabel !== 'unavailable').length
  const total = metrics.length
  return {
    status: status === 'unavailable' ? 'unavailable' : availableMetrics === total ? 'complete' : availableMetrics ? 'partial' : 'unavailable',
    available: availableMetrics,
    total,
    chartCount: charts.length,
  }
}

function unavailableBase() {
  return { status: 'unavailable', kpis: [], charts: [], details: { rows: [] }, caveats: [], validity: { status: 'unavailable', available: 0, total: 0, chartCount: 0 } }
}

export function buildBuildingsPresentation(section) {
  const normalized = sectionData(section)
  if (normalized.status === 'unavailable' || !normalized.data) return unavailableBase()
  const data = normalized.data
  if (Object.hasOwn(data, 'totalLocationCount')) {
    const metricRows = [['provisionalHeightM', 'Provisional height'], ['provisionalAreaM2', 'Provisional area'], ['derivedVolumeM3', 'Derived volume'], ['suhi', 'SUHI']].map(([key, label]) => {
      const metric = data[key] ?? {}
      const coverage = metric.availability ?? {}
      const validCount = numberOrNull(coverage.available) ?? 0
      const denominator = numberOrNull(coverage.denominator) ?? 0
      return {
        key, label, kind: metric.kind ?? 'numeric', value: key === 'suhi' ? null : numberOrNull(metric.summary?.mean), displayValue: key === 'suhi' ? metric.summary?.dominantClass ?? 'No data' : display(metric.summary?.mean), unit: metric.unit ?? '',
        mean: numberOrNull(metric.summary?.mean), median: numberOrNull(metric.summary?.median), min: numberOrNull(metric.summary?.min), max: numberOrNull(metric.summary?.max),
        validCount, denominator, coverageLabel: `${validCount}/${denominator} valid`, evidenceLabel: key === 'derivedVolumeM3' ? 'Derived from provisional fields' : 'Provisional',
      }
    })
    const chartSpecs = [
      ['provisionalAreaM2', 'Provisional area', 'm²'],
      ['provisionalHeightM', 'Provisional height', 'm'],
      ['derivedVolumeM3', 'Derived volume', 'm³'],
    ]
    const charts = chartSpecs.map(([key, title, unit]) => {
      const metric = data[key]
      if (!metric || metric.status === 'unavailable') return null
      const validCount = numberOrNull(metric.availability?.available)
      return histogramModel(key, title, metric, metric.unit ?? unit, validCount, 'overflow')
    }).filter(Boolean)
    const suhiChart = categoricalCountModel('suhi', 'SUHI class distribution', data.suhi)
    if (suhiChart) charts.push(suhiChart)
    const storedAreaBasis = data.storedAreaSelectionBasis
    const storedAreaKpis = [
      kpi('summedStoredAreaM2', 'Summed stored building area', data.summedStoredAreaM2, 'm²'),
      kpi('storedAreaSharePct', 'Stored building area share', data.storedAreaSharePct, '%'),
    ].filter(({ value }) => value !== null)
    return {
      status: 'available',
      kpis: [kpi('totalLocationCount', 'Building locations', data.totalLocationCount, 'locations'), kpi('centralLocationCount', 'Central locations', data.centralLocationCount, 'locations'), kpi('enrichedLocationCount', 'Enriched locations', data.enrichedLocationCount, 'locations'), ...storedAreaKpis],
      metrics: metricRows, charts, details: { rows: metricRows },
      caveats: ['VEDAS/ISRO-derived prototype building-point dataset; counts are not a verified census of unique physical buildings.', 'Central Zone 181 is count-only. Height and area are provisional; SUHI is an unverified categorical class; volume is derived area × height.', storedAreaBasis].filter(Boolean),
      validity: { status: metricRows.some(({ value }) => value !== null) ? 'partial' : 'unavailable', available: metricRows.filter(({ value }) => value !== null).length, total: metricRows.length, chartCount: charts.length },
    }
  }
  const chart = histogramModel('footprintAreaM2', 'Building footprint area', data.footprintAreaM2, 'm²', data.buildingCount, 'overflow')
  const rows = BUILDING_METRICS.map(([key, label]) => {
    const metric = data.buildingMetrics?.[key]
    const summary = metric?.summary ?? metric
    return { key, label, mean: numberOrNull(summary?.mean), median: numberOrNull(summary?.median), min: numberOrNull(summary?.min), max: numberOrNull(summary?.max), unit: 'unitless' }
  })
  return {
    status: 'available',
    kpis: [
      kpi('buildingCount', 'Buildings', data.buildingCount, 'buildings'),
      kpi('footprintCoverageM2', 'Footprint coverage area', data.footprintCoverageM2, 'm²'),
      kpi('footprintCoveragePct', 'Footprint coverage share', data.footprintCoveragePct, '%'),
      kpi('medianFootprintAreaM2', 'Median footprint area', data.footprintAreaM2?.median, 'm²'),
      kpi('meanFootprintAreaM2', 'Mean footprint area', data.footprintAreaM2?.mean, 'm²'),
    ],
    charts: chart ? [chart] : [],
    details: { rows },
    caveats: [data.buildingInclusionRule ? `Building inclusion: ${data.buildingInclusionRule}` : null, data.footprintCoverageAccuracy ? `Footprint coverage accuracy: ${data.footprintCoverageAccuracy}` : null].filter(Boolean),
    validity: { status: 'available', available: 1, total: 1, chartCount: chart ? 1 : 0 },
  }
}

export function buildStreetsPresentation(section) {
  const normalized = sectionData(section)
  if (normalized.status === 'unavailable' || !normalized.data) return unavailableBase()
  const data = normalized.data
  return {
    status: 'available',
    kpis: [
      kpi('clippedLengthKm', 'Clipped street length', data.clippedLengthKm, 'km'),
      kpi('intersectionDensityPerKm2', 'Intersection density', data.intersectionDensityPerKm2, 'intersections/km²'),
      kpi('linkNodeRatio', 'Link–node ratio', data.linkNodeRatio, 'ratio'),
      kpi('connectedNodeRatio', 'Connected-node share', numberOrNull(data.connectedNodeRatio) == null ? null : Number(data.connectedNodeRatio) * 100, '%'),
    ],
    charts: [],
    details: { rows: [] },
    caveats: [data.topologyRule, 'Fixed-bin street observations are not charted because they contain a single aggregate observation.'].filter(Boolean),
    validity: { status: 'available', available: 1, total: 1, chartCount: 0 },
  }
}

function categoricalAreaChart(data) {
  const floodRiskArea = data?.floodRiskArea
  if (floodRiskArea?.status === 'unavailable' || !Array.isArray(floodRiskArea?.categories)) return null
  const categories = floodRiskArea.categories.map((category) => {
    const value = numberOrNull(category.areaM2)
    return { key: category.key, label: category.label, value, displayValue: value === null ? 'Unavailable' : display(value), status: category.status === 'unavailable' || value === null ? 'unavailable' : 'available' }
  })
  return {
    key: 'floodRiskArea', title: 'Flood-risk area by category', type: 'categorical-area', orientation: 'vertical', unit: floodRiskArea.unit ?? 'm²',
    xAxisLabel: 'Risk category', yAxisLabel: `Area (${floodRiskArea.unit ?? 'm²'})`, totalValue: numberOrNull(floodRiskArea.totalClassifiedAreaM2), categories,
  }
}

export function buildEnvironmentPresentation(section) {
  const normalized = sectionData(section)
  if (normalized.status === 'unavailable' || !normalized.data) return { ...unavailableBase(), metrics: [], vegetationThreshold: null }
  const data = normalized.data
  const fallbackUnits = { lst: '°C', ndvi: 'unitless', vegetationFraction: '%', height2023: 'm' }
  const metrics = ENVIRONMENT_METRICS.map(([key, label]) => {
    const rawValue = key === 'vegetationFraction' ? data[key]?.mean : data[key]?.median ?? data[key]?.mean
    const value = key === 'vegetationFraction' && numberOrNull(rawValue) != null ? Number(rawValue) * 100 : rawValue
    return { key, label, value: numberOrNull(value), displayValue: display(value), unit: key === 'vegetationFraction' ? '%' : data[key]?.unit ?? fallbackUnits[key], coverageLabel: coverageLabel(data[key]), evidenceLabel: evidenceLabel(data[key]), reason: data[key]?.reason ?? null }
  })
  const floodRiskChart = categoricalAreaChart(data)
  const charts = [...ENVIRONMENT_METRICS.filter(([key]) => key !== 'vegetationFraction').map(([key, label]) => histogramModel(key, label, data[key], fallbackUnits[key], data[key]?.validPixelCount)).filter(Boolean), floodRiskChart].filter(Boolean)
  const vegetation = data.vegetationFraction
  const distribution = distributionOf(vegetation)
  const threshold = numberOrNull(vegetation?.threshold ?? vegetation?.provenance?.threshold)
  let vegetationThreshold = null
  if (threshold !== null && Array.isArray(distribution?.bins) && Array.isArray(distribution?.counts) && distribution.bins.length === distribution.counts.length + 1) {
    const isBinaryDistribution = distribution.bins.length === 3 && Number(distribution.bins[0]) === 0 && Number(distribution.bins[1]) === 1
    const below = isBinaryDistribution ? Number(distribution.counts[0] ?? 0) : distribution.counts.reduce((sum, count, index) => sum + (Number(distribution.bins[index + 1]) <= threshold ? Number(count) : 0), 0)
    const atOrAbove = isBinaryDistribution ? Number(distribution.counts[1] ?? 0) : distribution.counts.reduce((sum, count, index) => sum + (Number(distribution.bins[index + 1]) > threshold ? Number(count) : 0), 0)
    vegetationThreshold = { threshold, thresholdLabel: `≥ ${display(threshold)}`, unit: vegetation.unit ?? '', columns: [{ key: 'below', label: `< ${display(threshold)}`, count: below }, { key: 'atOrAbove', label: `≥ ${display(threshold)}`, count: atOrAbove }] }
  }
  return {
    status: 'available',
    kpis: [kpi('heatRisk', 'Heat-risk proxy', data.heatRisk?.mean, data.heatRisk?.unit ?? 'relative proxy index'), ...metrics],
    metrics,
    charts,
    vegetationThreshold,
    details: { rows: [] },
    caveats: [data.heatRisk?.caveat, data.floodRiskArea?.caveat, data.selectionRule].filter(Boolean),
    validity: validity(normalized.status, metrics, charts),
  }
}

const SPACE_SYNTAX_METRICS = [
  ['betweenness', 'Betweenness'],
  ['closeness', 'Closeness'],
  ['straightness', 'Straightness'],
]

function availabilityParts(metric) {
  const coverage = metric?.availability ?? metric?.coverage ?? {}
  return {
    validCount: numberOrNull(coverage.available ?? coverage.valid ?? coverage.count),
    denominator: numberOrNull(coverage.denominator ?? coverage.total ?? coverage.expected),
  }
}

function weightedMetricRows(group, source) {
  return SPACE_SYNTAX_METRICS.map(([metric, label]) => {
    const value = group?.[metric]
    if (!value) return null
    const { validCount, denominator } = availabilityParts(value)
    return {
      key: `${source}.${metric}`,
      label: `${source === 'centrality' ? 'Centrality' : 'Space syntax'} — ${label}`,
      source,
      metric,
      value: numberOrNull(value.weightedMean ?? value.mean ?? value.value),
      displayValue: display(value.weightedMean ?? value.mean ?? value.value),
      unit: value.unit ?? 'weighted index',
      validCount,
      denominator,
      weightTotal: numberOrNull(value.weightTotal),
      weightField: value.weightField ?? 'clippedLengthM',
    }
  }).filter(Boolean)
}

export function buildSpaceSyntaxPresentation(section) {
  const normalized = sectionData(section)
  if (normalized.status === 'unavailable' || !normalized.data) return unavailableBase()
  const rows = [...weightedMetricRows(normalized.data.centrality, 'centrality'), ...weightedMetricRows(normalized.data.spaceSyntax, 'spaceSyntax')]
  const groups = ['centrality', 'spaceSyntax'].map((source) => ({ caption: source === 'centrality' ? 'Centrality' : 'Space syntax', rows: weightedMetricRows(normalized.data[source], source) })).filter(({ rows: groupRows }) => groupRows.length)
  return {
    status: rows.length ? 'available' : 'unavailable',
    kpis: [], charts: [], details: { rows }, groups,
    caveats: [
      'Centrality and space-syntax values are separate clipped-length-weighted means; they are not interchangeable.',
      'Valid counts and denominators describe source features with valid values; clipped boundary lengths can change the weighting total.',
    ],
    validity: { status: rows.length ? (rows.every((row) => row.value !== null) ? 'complete' : 'partial') : 'unavailable', available: rows.filter((row) => row.value !== null).length, total: rows.length, chartCount: 0 },
  }
}

function transportRow(key, label, value, unit, extra = {}) {
  const number = numberOrNull(value)
  return { key, label, value: number, displayValue: display(number), unit, ...extra }
}

export function buildPublicTransportPresentation(section) {
  const normalized = sectionData(section)
  if (normalized.status === 'unavailable' || !normalized.data) return unavailableBase()
  const data = normalized.data
  const routeCount = Array.isArray(data.routesServingStopsInsideCircle) ? data.routesServingStopsInsideCircle.length : data.routesServingStopsInsideCircle
  const routeStopCount = Array.isArray(data.routeStopIndexes) ? data.routeStopIndexes.length : Array.isArray(data.routeStops?.features) ? data.routeStops.features.length : null
  const routeReachAreaM2 = data.routeReachAreaM2 ?? data.connectedAreaM2
  const rows = [
    transportRow('local.stopsInsideCircle', 'Stops inside profile boundary', data.stopsInsideCircle, 'stops', { group: 'local' }),
    transportRow('local.routesServingStopsInsideCircle', 'Routes serving profile stops', routeCount, 'routes', { group: 'local' }),
    transportRow('routeReach.area', 'Route-associated reach area', routeReachAreaM2 == null ? null : Number(routeReachAreaM2) / 1e6, 'km²', { group: 'routeReach' }),
    transportRow('routeReach.routeStopCount', 'Stops on selected routes', routeStopCount, 'route-stops', { group: 'routeReach' }),
    transportRow('routeReach.cells', 'Route-associated reach cells', data.routeReachCells ?? data.shared15MinuteCellIndexes?.length, 'cells', { group: 'routeReach' }),
  ].filter((row) => row.value !== null)
  const scheduled = data.caveats?.scheduledService ?? data.scheduledServiceCaveat
  const caveats = [scheduled, data.caveats?.feed, data.routeSelectionRule ? `Wider reach uses the existing route association: ${data.routeSelectionRule}.` : null].filter(Boolean)
  const localReach = rows.filter((row) => row.group === 'local')
  const routeReach = rows.filter((row) => row.group === 'routeReach')
  return { status: rows.length ? 'available' : 'unavailable', kpis: [], charts: [], details: { rows }, reachGroups: [{ label: 'Local profile', rows: localReach }, { label: 'Wider route-associated reach', rows: routeReach }].filter(({ rows: groupRows }) => groupRows.length), caveats, validity: { status: rows.length ? 'complete' : 'unavailable', available: rows.length, total: rows.length, chartCount: 0 } }
}

export function buildParksSchoolsPresentation(section) {
  return buildParksEducationPresentation(section)
}

export function buildParksEducationPresentation(section) {
  const normalized = sectionData(section)
  if (normalized.status === 'unavailable' || !normalized.data) return unavailableBase()
  const rows = [['parks', 'Parks', 'parks'], ['schools', 'Schools', 'schools']].map(([key, label, unit]) => {
    const item = normalized.data[key]
    if (!item) return null
    const value = numberOrNull(item.count ?? item.value)
    const { validCount, denominator } = availabilityParts(item)
    return { key, label, value, displayValue: display(value), unit, validCount, denominator }
  }).filter(Boolean)
  return { status: rows.length ? 'available' : 'unavailable', kpis: [], charts: [], details: { rows }, groups: [{ caption: 'Parks and schools', rows }], caveats: ['Counts use representative points for parks and schools; they do not establish full polygon coverage or access.'], validity: { status: rows.length ? 'complete' : 'unavailable', available: rows.filter((row) => row.value !== null).length, total: rows.length, chartCount: 0 } }
}
