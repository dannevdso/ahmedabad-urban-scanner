import { buildEnvironmentPresentation, buildBuildingsPresentation } from './profile_presentations.js'
import { profileSelectionPresentation } from './local_area_profile.js'
import { renderA3AtlasHTML } from './print_profile_a3.js'

export const PRINT_PAGE_SIZES = {
  A2: { width: '594mm', height: '420mm', orientation: 'landscape' },
  A3: { width: '420mm', height: '297mm', orientation: 'landscape' },
  A3_PORTRAIT: { width: '297mm', height: '420mm', orientation: 'portrait' },
}

const SLOT_IDS = ['header', 'key-map', 'overview', 'buildings', 'streets-connectivity', 'space-syntax-centrality', 'environment', 'public-transport', 'parks-education', 'footer']
const slot = (id, x, y, width, height) => ({ id, x, y, width, height })

export const PRINT_TEMPLATES = {
  A2: { widthMm: 594, heightMm: 420, columns: 16, marginMm: 15, gapMm: 4, slots: [
    slot('header', 0, 0, 16, 2), slot('key-map', 0, 2, 5, 5), slot('overview', 6, 2, 5, 2), slot('buildings', 6, 4, 10, 4),
    slot('streets-connectivity', 0, 7, 5, 2), slot('space-syntax-centrality', 0, 9, 5, 2), slot('environment', 0, 11, 8, 4),
    slot('public-transport', 9, 8, 7, 3), slot('parks-education', 9, 11, 7, 4), slot('footer', 0, 15, 16, 2),
  ] },
  A3: { widthMm: 420, heightMm: 297, columns: 12, marginMm: 12, gapMm: 3, slots: [
    slot('header', 0, 0, 12, 2), slot('key-map', 0, 2, 4, 4), slot('overview', 5, 2, 3, 2), slot('buildings', 5, 4, 7, 3),
    slot('streets-connectivity', 0, 6, 4, 2), slot('space-syntax-centrality', 0, 8, 4, 2), slot('environment', 0, 10, 6, 3),
    slot('public-transport', 7, 7, 5, 3), slot('parks-education', 7, 10, 5, 3), slot('footer', 0, 13, 12, 2),
  ] },
  A3_PORTRAIT: { widthMm: 297, heightMm: 420, columns: 8, marginMm: 12, gapMm: 3, slots: [
    slot('header', 0, 0, 8, 2), slot('key-map', 0, 2, 4, 4), slot('overview', 5, 2, 3, 2), slot('buildings', 0, 6, 8, 3),
    slot('streets-connectivity', 0, 9, 4, 2), slot('space-syntax-centrality', 5, 9, 3, 2), slot('environment', 0, 11, 8, 3),
    slot('public-transport', 0, 14, 4, 3), slot('parks-education', 5, 14, 3, 3), slot('footer', 0, 17, 8, 2),
  ] },
}

export const PRINT_DISCLAIMER = 'Experimental prototype. The website and this report use unverified data. No accuracy is guaranteed. The creator accepts no responsibility for the accuracy of the data or derived outputs.'
const AHMEDABAD_BOUNDS = [72.437031, 22.914348, 72.728602, 23.140865]

export const PRINT_SECTION_LABELS = {
  overview: 'Overview',
  buildings: 'Buildings',
  streetsConnectivity: 'Streets / connectivity',
  spaceSyntaxCentrality: 'Space syntax / centrality',
  environment: 'Environment',
  publicTransport: 'Public transport',
  parksEducation: 'Parks and schools',
}

const PRINT_SECTION_KEYS = Object.keys(PRINT_SECTION_LABELS)

function formatProfileId(value) {
  if (value === null || value === undefined || value === '') return null
  if (typeof value === 'number' || /^\d+$/.test(String(value))) return `ID ${String(value).padStart(2, '0')}`
  return String(value)
}

function formatProfileDate(value) {
  if (value) {
    const date = new Date(value)
    if (!Number.isNaN(date.getTime())) return date.toISOString().slice(0, 10)
  }
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
}

export function getPrintAvailability(profileState) {
  const available = profileState?.status === 'ready' && profileState?.result != null
  return { available, reason: available ? '' : 'Profile is not ready.' }
}

export function buildPrintSnapshot(profileState, pageSize = 'A3', boundaryGeometry = profileState?.boundaryGeometry ?? null) {
  const { available, reason } = getPrintAvailability(profileState)
  if (!available) throw new Error(reason)
  const normalizedPageSize = Object.hasOwn(PRINT_PAGE_SIZES, pageSize) ? pageSize : 'A3'
  const result = profileState.result
  const center = result.center ?? profileState.center ?? null
  const radiusM = result.radiusM ?? profileState.radiusM ?? null
  const selectionPresentation = profileSelectionPresentation(result)
  return {
    result,
    pageSize: normalizedPageSize,
    pageClass: `print-page-${normalizedPageSize.toLowerCase().replace('_', '-')}`,
    center,
    radiusM,
    selectionPresentation,
    selectionType: result.selection?.type ?? 'circle',
    profileId: formatProfileId(result.profileId ?? result.profile_id ?? result.id ?? profileState.profileId ?? result.requestId),
    date: formatProfileDate(result.date ?? result.generatedAt ?? result.generated_at ?? result.metadata?.generatedAt ?? profileState.printDate),
    provenance: result.provenance ?? result.sources ?? null,
    boundaryGeometry,
  }
}

export function renderPrintProfileHTML(snapshot) {
  if (snapshot.pageSize === 'A3') return renderA3AtlasHTML(snapshot, PRINT_DISCLAIMER)
  const { result } = snapshot
  const sections = PRINT_SECTION_KEYS.map((key) => renderSection(key, getSection(result, key), sectionSlotId(key))).join('')
  const isTps = snapshot.selectionType === 'tps'
  const selectionLines = snapshot.selectionPresentation.metricValue.split('\n')
  const tpsNumber = snapshot.result.selection?.tps_no == null || String(snapshot.result.selection.tps_no).trim() === '' ? 'unavailable' : String(snapshot.result.selection.tps_no)
  return `<article class="print-sheet ${snapshot.pageClass}" data-page-size="${escapeAttribute(snapshot.pageSize)}" data-template="${escapeAttribute(snapshot.pageSize)}">
    <header class="print-header" data-slot="header">
      <div><p class="print-kicker">AHMEDABAD URBAN SCANNER / LOCAL AREA PROFILE</p><h1>Local Area Profile</h1><p class="print-subtitle">Standardized monochrome one-sheet report</p></div>
      <div class="print-meta-grid">
        ${isTps ? metaItem('TPS name', selectionLines[0]) + metaItem('TPS number', tpsNumber) : metaItem('Center', formatCenter(snapshot.center)) + metaItem('Radius', formatValue(snapshot.radiusM, ' m'))}
        ${metaItem('Date', formatValue(snapshot.date))}
        ${metaItem('Profile ID', formatValue(snapshot.profileId))}
      </div>
    </header>
    <section class="print-anchor-grid" aria-label="Profile map" data-slot="key-map">
      ${renderKeyMap(snapshot, isTps, selectionLines)}
    </section>
    <section class="print-sections" aria-label="Profile sections">${sections}</section>
    <footer class="print-footer" data-slot="footer"><div><strong>Source / provenance</strong><span>${escapeHtml(formatProvenance(snapshot.provenance))}</span><span>Profile ID: ${escapeHtml(formatValue(snapshot.profileId))}</span></div><div><strong>Print specification</strong><span>A2 landscape · A3 landscape · A3 portrait · grayscale-safe vector key map</span></div><div class="print-disclaimer"><strong>Experimental data limitation</strong><span>${PRINT_DISCLAIMER}</span></div></footer>
  </article>`
}

function renderKeyMap(snapshot, isTps, selectionLines) {
  const boundary = snapshot.boundaryGeometry ?? bboxGeometry(AHMEDABAD_BOUNDS)
  const selected = isTps ? snapshot.result.selection?.geometry : circleGeometry(snapshot.center, snapshot.radiusM)
  const all = [...coordinatesFromGeometry(boundary), ...coordinatesFromGeometry(selected)]
  const bounds = extent(all.length ? all : coordinatesFromGeometry(bboxGeometry(AHMEDABAD_BOUNDS)))
  const project = ([lon, lat]) => `${(((lon - bounds[0]) / (bounds[2] - bounds[0] || 1)) * 100).toFixed(2)},${(100 - ((lat - bounds[1]) / (bounds[3] - bounds[1] || 1)) * 100).toFixed(2)}`
  const path = (geometry) => geometryPaths(geometry).map((ring) => `M ${ring.map(project).join(' L ')} Z`).join(' ')
  const selectedClass = isTps ? 'selected-tps' : 'selected-circle'
  const markerPoint = !isTps && Array.isArray(snapshot.center) ? project(snapshot.center).split(',') : null
  const marker = !isTps && snapshot.radiusM < 600 && markerPoint ? `<circle class="locator-halo" cx="${markerPoint[0]}" cy="${markerPoint[1]}" r="2.8" />` : ''
  return `<div class="print-key-map" data-map-kind="print-map-placeholder" aria-label="Ahmedabad boundary-only locator map"><span class="print-map-title">${isTps ? 'TPS boundary key map' : 'Profile catchment key map'}</span><svg viewBox="0 0 100 100" role="img" aria-label="Ahmedabad municipal boundary and selected geometry"><path id="ahmedabad-boundary" class="ahmedabad-boundary" d="${path(boundary)}"/><path class="${selectedClass}" d="${path(selected)}"/>${marker}<g class="north-arrow"><path d="M 92 16 L 92 7 M 92 7 L 89 12 M 92 7 L 95 12"/></g><g class="scale-bar"><path d="M 8 92 H 28 M 8 90 V 94 M 28 90 V 94"/><text x="8" y="88">approx. 5 km</text></g></svg><span class="print-map-note">Ahmedabad boundary only; selected geometry is highlighted. Approximate scale, not survey accuracy.</span>${isTps ? selectionLines.map((line) => `<span class="print-map-selection">${escapeHtml(line)}</span>`).join('') : `<span class="print-map-center">Center: ${escapeHtml(formatCenter(snapshot.center))}</span>`}</div>`
}

function bboxGeometry([west, south, east, north]) { return { type: 'Polygon', coordinates: [[[west, south], [east, south], [east, north], [west, north], [west, south]]] } }
function circleGeometry(center, radiusM) {
  if (!Array.isArray(center) || center.length !== 2 || !Number.isFinite(Number(radiusM))) return null
  const [lon, lat] = center.map(Number); const latDelta = Number(radiusM) / 111320; const lonDelta = Number(radiusM) / (111320 * Math.cos(lat * Math.PI / 180))
  return { type: 'Polygon', coordinates: [Array.from({ length: 48 }, (_, i) => { const a = i / 48 * Math.PI * 2; return [lon + Math.cos(a) * lonDelta, lat + Math.sin(a) * latDelta] }).concat([[lon + lonDelta, lat]])] }
}
function geometryPaths(geometry) { if (!geometry) return []; if (geometry.type === 'Polygon') return geometry.coordinates; if (geometry.type === 'MultiPolygon') return geometry.coordinates.flat(); return [] }
function coordinatesFromGeometry(geometry) { return geometryPaths(geometry).flat().filter((point) => Array.isArray(point) && point.length === 2) }
function extent(points) { return [Math.min(...points.map(([x]) => x)), Math.min(...points.map(([, y]) => y)), Math.max(...points.map(([x]) => x)), Math.max(...points.map(([, y]) => y))] }

function renderSection(key, section, slotId) {
  const available = section?.status === 'available'
  const body = available ? renderSectionData(section.data, key) : '<div class="no-data pattern-diagonal"><strong>Unavailable in this result</strong><span>No normalized value was supplied for this section.</span></div>'
  return `<section class="print-section ${available ? 'section-available' : 'section-unavailable'}" data-slot="${slotId}" data-section="${key}"><h2>${PRINT_SECTION_LABELS[key]}</h2>${body}</section>`
}

function sectionSlotId(key) {
  return key.replace(/[A-Z]/g, (character) => `-${character.toLowerCase()}`)
}

function renderSectionData(data, sectionKey) {
  if (data == null) return '<div class="no-data pattern-diagonal">No data</div>'
  if (isCuratedSectionData(data, sectionKey)) return renderCuratedSectionData(data, sectionKey)
  if (isPhase1BSectionData(data, sectionKey)) return renderPhase1BSectionData(data, sectionKey)
  const { metrics, charts, notes } = curateSectionData(data)
  const chunks = PRINT_SECTION_KEYS.includes(sectionKey) ? [] : charts.map((chart, index) => renderChart(chart, index))
  if (metrics.length) chunks.push(`<dl class="print-metrics">${metrics.map(({ label, value }) => `<div><dt>${escapeHtml(label)}</dt><dd class="${value == null ? 'no-data-value' : ''}">${escapeHtml(formatValue(value))}</dd></div>`).join('')}</dl>`)
  if (notes.length) chunks.push(`<div class="print-notes">${notes.map((note) => `<span>${escapeHtml(note)}</span>`).join('')}</div>`)
  if (!chunks.length) return '<div class="no-data pattern-diagonal">No data</div>'
  return chunks.join('')
}

function isCuratedSectionData(data, sectionKey) {
  if (sectionKey === 'buildings') return 'buildingCount' in data || 'totalLocationCount' in data || 'footprintCoveragePct' in data || data.footprintAreaM2?.histogram || data.provisionalAreaM2?.distribution
  if (sectionKey === 'streetsConnectivity') return 'clippedLengthKm' in data || 'intersectionDensityPerKm2' in data || 'linkNodeRatio' in data
  if (sectionKey === 'environment') return ['lst', 'ndvi', 'vegetationFraction', 'height2023'].some((key) => data[key]?.distribution || data[key]?.mean != null) || data.floodRiskArea != null
  return false
}

function isPhase1BSectionData(data, sectionKey) {
  return sectionKey === 'spaceSyntaxCentrality' || sectionKey === 'publicTransport' || sectionKey === 'parksEducation'
}

const PHASE1B_METRICS = {
  spaceSyntaxCentrality: [
    ['centrality.betweenness.weightedMean', 'Betweenness / weighted mean'],
    ['centrality.closeness.weightedMean', 'Closeness / weighted mean'],
    ['centrality.straightness.weightedMean', 'Straightness / weighted mean'],
    ['spaceSyntax.betweenness.weightedMean', 'Space syntax betweenness / weighted mean'],
  ],
  publicTransport: [
    ['stopsInsideCircle', 'Stops inside selected area'],
    ['routesServingStopsInsideCircle', 'Routes serving stops'],
    ['routeReachAreaM2', 'Route-associated reach area (km²)'],
    ['routeReachCells', 'Route-reach cells'],
  ],
  parksEducation: [
    ['parks.count', 'Parks / count'],
    ['schools.count', 'Schools / count'],
  ],
}

function renderPhase1BSectionData(data, sectionKey) {
  const metrics = PHASE1B_METRICS[sectionKey]
    .map(([path, label]) => ({ label, value: phase1BMetricValue(data, sectionKey, path) }))
    .filter(({ value }) => value != null)
  const notes = phase1BCaveats(data, sectionKey)
  const chunks = []
  if (metrics.length) chunks.push(`<dl class="print-metrics">${metrics.map(({ label, value }) => `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(formatValue(value))}</dd></div>`).join('')}</dl>`)
  if (notes.length) chunks.push(`<div class="print-notes">${notes.map((note) => `<span>${escapeHtml(note)}</span>`).join('')}</div>`)
  return chunks.length ? chunks.join('') : '<div class="no-data pattern-diagonal">No data</div>'
}

function phase1BMetricValue(data, sectionKey, path) {
  const value = readPath(data, path)
  if (sectionKey !== 'publicTransport') return value
  if (path === 'routesServingStopsInsideCircle' && Array.isArray(value)) return value.length
  if (path === 'routeReachAreaM2' && Number.isFinite(Number(value))) return Number(value) / 1e6
  return value
}

function phase1BCaveats(data, sectionKey) {
  if (sectionKey === 'spaceSyntaxCentrality') {
    const fields = ['centrality', 'spaceSyntax'].filter((key) => data[key]?.betweenness?.weightedMean != null)
    const weightField = data[fields[0]]?.betweenness?.weightField
    return [weightField ? `Weighted by ${humanize(weightField)}.` : fields.length ? 'Weighted means are reported from normalized network values.' : 'No normalized network metric was supplied.']
  }
  if (sectionKey === 'publicTransport') return data.routeSelectionRule ? [String(data.routeSelectionRule).replaceAll('circle', 'selected area')] : ['Routes are reported only where normalized stop-to-route relationships are supplied.']
  return ['Counts are limited to normalized park and school point sources inside the selected area.']
}

const CURATED_METRICS = {
  buildings: [['buildingCount', 'Buildings'], ['footprintCoverageM2', 'Building-footprint coverage (m²)'], ['footprintCoveragePct', 'Building-footprint coverage (%)'], ['footprintAreaM2.mean', 'Mean footprint area (m²)']],
  streetsConnectivity: [['clippedLengthKm', 'Street length (km)'], ['intersectionDensityPerKm2', 'Intersection density (per km²)'], ['linkNodeRatio', 'Link / node ratio'], ['connectedNodeRatio', 'Connected-node ratio']],
  environment: [['lst.mean', 'LST mean'], ['lst.coveragePercentage', 'LST coverage (%)'], ['ndvi.mean', 'NDVI mean'], ['vegetationFraction.mean', 'Vegetation threshold coverage']],
}

function renderBuildingPresentationData(data) {
  const model = buildBuildingsPresentation({ status: 'available', data })
  const charts = model.charts.map((chart) => ({
    title: chart.title,
    method: `${chart.method} · n=${chart.totalCount}`,
    bins: (chart.type === 'categorical-counts' ? chart.categories : chart.bins).map((bin) => ({ label: bin.label, value: bin.count })),
  }))
  const metrics = model.kpis.map(({ label, value, unit }) => ({ label: `${label}${unit ? ` (${unit})` : ''}`, value }))
  const chunks = []
  if (charts.length) chunks.push(charts.map((chart, index) => renderVerticalChart(chart, index)).join(''))
  if (metrics.some(({ value }) => value != null)) chunks.push(`<dl class="print-metrics">${metrics.map(({ label, value }) => `<div><dt>${escapeHtml(label)}</dt><dd class="${value == null ? 'no-data-value' : ''}">${escapeHtml(formatValue(value))}</dd></div>`).join('')}</dl>`)
  if (model.caveats.length) chunks.push(`<div class="print-notes">${model.caveats.map((note) => `<span>${escapeHtml(String(note).replaceAll('circle', 'selected area'))}</span>`).join('')}</div>`)
  return chunks.length ? chunks.join('') : '<div class="no-data pattern-diagonal">No data</div>'
}

function renderCuratedSectionData(data, sectionKey) {
  if (sectionKey === 'buildings' && ('totalLocationCount' in data || data.provisionalAreaM2?.distribution)) return renderBuildingPresentationData(data)
  const metrics = CURATED_METRICS[sectionKey].map(([path, label]) => ({ label, value: readPath(data, path) }))
  const charts = sectionKey === 'buildings'
    ? [histogramChart('Footprint area (m²)', data.footprintAreaM2?.histogram)].filter(Boolean)
    : sectionKey === 'environment'
      ? [...['lst', 'ndvi', 'vegetationFraction', 'height2023'].map((key) => distributionChart(key, data[key])).filter(Boolean).slice(0, 2), printFloodRiskChart(data)].filter(Boolean)
      : []
  const chunks = []
  if (charts.length) chunks.push(charts.map((chart, index) => renderVerticalChart(chart, index)).join(''))
  if (metrics.some(({ value }) => value != null)) chunks.push(`<dl class="print-metrics">${metrics.map(({ label, value }) => `<div><dt>${escapeHtml(label)}</dt><dd class="${value == null ? 'no-data-value' : ''}">${escapeHtml(formatValue(value))}</dd></div>`).join('')}</dl>`)
  return chunks.length ? chunks.join('') : '<div class="no-data pattern-diagonal">No data</div>'
}

function readPath(value, path) { return path.split('.').reduce((current, key) => current == null ? null : current[key], value) }
function histogramChart(title, histogram) {
  if (!histogram || !Array.isArray(histogram.bins) || !Array.isArray(histogram.counts) || !histogram.counts.some((count) => Number(count) > 0)) return null
  return { title, method: histogram.method, bins: histogram.counts.map((count, index) => ({ label: binLabel(histogram.bins, index), value: count })) }
}
function printFloodRiskChart(data) {
  const chart = buildEnvironmentPresentation({ status: 'available', data }).charts.find(({ key }) => key === 'floodRiskArea')
  if (!chart) return null
  return { title: chart.title, method: `${chart.xAxisLabel} · ${chart.yAxisLabel}`, bins: chart.categories.map((category) => ({ label: category.label, value: category.value == null ? 'Unavailable' : category.value })) }
}

function distributionChart(key, metric) {
  const labels = { lst: 'LST', ndvi: 'NDVI', vegetationFraction: 'Vegetation threshold', height2023: 'Height (2023)' }
  const distribution = metric?.distribution
  if (!distribution || !Array.isArray(distribution.bins) || !Array.isArray(distribution.counts) || !distribution.counts.some((count) => Number(count) > 0)) return null
  const bins = distribution.counts.map((count, index) => ({ label: binLabel(distribution.bins, index), value: count }))
  const binnedCount = distribution.counts.reduce((sum, count) => sum + Number(count || 0), 0)
  const validPixelCount = Number(metric.validPixelCount)
  if (Number.isFinite(validPixelCount) && validPixelCount > binnedCount) {
    bins.push({ label: `Outside ${formatValue(distribution.bins[0])}–${formatValue(distribution.bins.at(-1))}`, value: validPixelCount - binnedCount })
  }
  return { title: labels[key] ?? humanize(key), method: metric.provenance?.threshold != null ? `threshold ${formatValue(metric.provenance.threshold)}` : metric.provenance?.label, bins }
}
function binLabel(edges, index) { return `${formatValue(edges[index])}–${formatValue(edges[index + 1])}` }

const MAX_METRICS = 4
const MAX_CHARTS = 2
const MAX_BINS = 6
const MAX_TEXT = 180
const SKIP_KEYS = new Set(['diagnostics', 'metadata', 'geometry', 'features', 'assets', 'raw', 'source', 'provenance', 'sha256', 'bounds', 'transform'])
const NOTE_KEYS = new Set(['method', 'methods', 'caveat', 'caveats', 'note', 'notes', 'limitation', 'limitations'])

function curateSectionData(data) {
  const metrics = []
  const charts = []
  const notes = []
  const visit = (value, path = []) => {
    if (metrics.length >= MAX_METRICS && charts.length >= MAX_CHARTS) return
    if (value == null) return
    const parentKey = path.at(-1) ?? ''
    const label = path.map(humanize).join(' / ')
    if (typeof value === 'string') {
      if (NOTE_KEYS.has(parentKey.toLowerCase()) && value.length > 20 && notes.length < 2) notes.push(boundText(value))
      else if (metrics.length < MAX_METRICS && label) metrics.push({ label, value: boundText(value) })
      return
    }
    if (typeof value === 'number' || typeof value === 'boolean') {
      if (metrics.length < MAX_METRICS && !SKIP_KEYS.has(parentKey)) metrics.push({ label, value })
      return
    }
    if (Array.isArray(value)) {
      const chartModels = value.filter((item) => item && typeof item === 'object' && Array.isArray(item.bins))
      if (chartModels.length && charts.length < MAX_CHARTS) {
        charts.push(...chartModels.slice(0, MAX_CHARTS - charts.length).map((chart) => ({ title: chart.title ?? (label || 'Chart'), method: chart.method, bins: chart.bins.filter((bin) => bin && bin.label != null && Number.isFinite(Number(bin.value))).slice(0, MAX_BINS) })))
        return
      }
      const bins = value.filter((item) => item && typeof item === 'object' && item.label != null && Number.isFinite(Number(item.value)))
      if (bins.length && charts.length < MAX_CHARTS) charts.push({ title: label || 'Distribution', bins: bins.slice(0, MAX_BINS) })
      return
    }
    if (typeof value !== 'object') return
    for (const [key, child] of Object.entries(value)) {
      if (SKIP_KEYS.has(key)) continue
      visit(child, [...path, key])
      if (metrics.length >= MAX_METRICS && charts.length >= MAX_CHARTS) break
    }
  }
  visit(data)
  return { metrics, charts, notes }
}

function renderVerticalChart(chart = {}, index) {
  const bins = Array.isArray(chart.bins) ? chart.bins : []
  const dense = bins.length > 12
  return `<div class="print-chart print-chart-vertical"><div class="print-chart-heading"><strong>${escapeHtml(chart.title ?? 'Chart')}</strong><span>${escapeHtml(chart.method ?? '')}</span></div><div class="print-chart-columns${dense ? ' print-chart-columns-dense' : ''}" style="grid-template-columns:repeat(${bins.length}, minmax(0, 1fr))">${bins.map((bin, binIndex) => `<div class="print-chart-column"><i class="pattern-${(index + binIndex) % 2 ? 'dots' : 'hatch'}" style="--bar-value:${barValue(bin.value, bins)}" aria-label="${escapeAttribute(`${bin.label}: ${formatValue(bin.value)}`)}"></i><b>${escapeHtml(formatPrintChartValue(bin.value, dense))}</b><span title="${escapeAttribute(bin.label)}">${escapeHtml(formatPrintChartLabel(bin.label, dense))}</span></div>`).join('')}</div></div>`
}

function formatPrintChartValue(value, dense) {
  const numeric = Number(value)
  if (dense && Number.isFinite(numeric) && Math.abs(numeric) >= 1000) return `${Number((numeric / 1000).toFixed(1))}k`
  return formatValue(value)
}

function formatPrintChartLabel(value, dense) {
  const label = String(value ?? '')
  return dense && label.startsWith('Outside ') ? 'Out' : label
}

function renderChart(chart = {}, index) {
  const bins = Array.isArray(chart.bins) ? chart.bins : []
  if (!bins.length) return `<div class="print-chart no-data pattern-diagonal"><strong>${escapeHtml(chart.title ?? 'Chart')}</strong><span>No data</span></div>`
  return `<div class="print-chart"><div class="print-chart-heading"><strong>${escapeHtml(chart.title ?? 'Chart')}</strong><span>${escapeHtml(chart.method ?? '')}</span></div><div class="print-chart-rows">${bins.map((bin, binIndex) => `<div class="print-chart-row"><span>${escapeHtml(bin.label)}</span><i class="pattern-${(index + binIndex) % 2 ? 'dots' : 'hatch'}" style="--bar-value:${barValue(bin.value, bins)}" aria-label="${escapeAttribute(`${bin.label}: ${formatValue(bin.value)}`)}"></i><b>${escapeHtml(formatValue(bin.value))}</b></div>`).join('')}</div></div>`
}

function getSection(result, key) {
  return result.sections?.[key] ?? (result[key] == null ? { status: 'unavailable', data: null } : { status: 'available', data: result[key] })
}

function metaItem(label, value) { return `<div><dt>${label}</dt><dd>${escapeHtml(value)}</dd></div>` }
function formatCenter(center) { return Array.isArray(center) && center.length === 2 ? `${formatNumber(Number(center[0]), 6)}, ${formatNumber(Number(center[1]), 6)}` : 'No data' }
function formatNumber(value, maximumFractionDigits = 2) {
  if (!Number.isFinite(value)) return 'No data'
  if (Number.isInteger(value)) return value.toLocaleString('en-US')
  if (value !== 0 && Math.abs(value) < 0.01) return Number(value.toPrecision(2)).toString()
  return value.toLocaleString('en-US', { maximumFractionDigits })
}
function formatValue(value, suffix = '') {
  if (value == null || value === '') return 'No data'
  if (Array.isArray(value)) return `${value.map((item) => formatValue(item)).join(', ')}${suffix}`
  if (typeof value === 'object') return 'No data'
  return `${typeof value === 'number' ? formatNumber(value) : String(value)}${suffix}`
}
function formatProvenance(provenance) {
  if (provenance == null) return 'No provenance supplied in this result.'
  if (typeof provenance === 'string') return boundText(provenance)
  return Object.entries(provenance).filter(([key]) => !SKIP_KEYS.has(key) || key === 'source').slice(0, 4).map(([key, value]) => `${humanize(key)}: ${boundText(formatValue(value))}`).join(' · ').slice(0, MAX_TEXT)
}
function boundText(value) { const text = String(value ?? '').replace(/\s+/g, ' ').trim(); return text.length > MAX_TEXT ? `${text.slice(0, MAX_TEXT - 1)}…` : text }
const METRIC_LABELS = { buildingCount: 'Buildings', totalLocationCount: 'Building locations', buildingFootprintCoveragePct: 'Building-footprint coverage (%)', intersectionDensityPerKm2: 'Intersection density (per km²)', vegetationFractionMean: 'Vegetation fraction (mean)', publicTransportStops: 'Public-transport stops', directlyServingRoutes: 'Directly serving routes' }
function humanize(value) { return METRIC_LABELS[value] ?? String(value).replace(/([a-z])([A-Z])/g, '$1 $2').replace(/[_-]+/g, ' ').replace(/^./, (char) => char.toUpperCase()) }
function barValue(value, bins) { const numeric = Number(value); const max = Math.max(1, ...bins.map((bin) => Number(bin.value)).filter(Number.isFinite)); return Number.isFinite(numeric) ? `${Math.max(0, Math.min(100, numeric / max * 100))}%` : '0%' }
function escapeHtml(value) { return String(value).replace(/[&<>'"]/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[character]) }
function escapeAttribute(value) { return escapeHtml(value) }

function fitPrintPreview(previewMount) {
  const sheet = previewMount.querySelector('.print-sheet')
  if (!sheet || !previewMount.clientWidth || !previewMount.clientHeight || !sheet.offsetWidth || !sheet.offsetHeight) return
  const scale = Math.min(previewMount.clientWidth / sheet.offsetWidth, previewMount.clientHeight / sheet.offsetHeight)
  sheet.style.transform = `scale(${scale})`
}

export function openPrintProfilePreview({ profileState, mount = document.body, print = () => window.print() } = {}) {
  const availability = getPrintAvailability(profileState)
  if (!availability.available) return { available: false, reason: availability.reason }
  const overlay = document.createElement('div')
  overlay.className = 'print-preview-overlay'
  overlay.innerHTML = `<div class="print-preview-toolbar"><strong>Print preview</strong><label>Page size <select class="print-page-size"><option value="A3" selected>A3 landscape (420 × 297 mm)</option><option value="A2">A2 landscape (594 × 420 mm)</option><option value="A3_PORTRAIT">A3 portrait (297 × 420 mm)</option></select></label><button type="button" class="print-preview-action">Print using browser</button><button type="button" class="print-preview-close">Close</button></div><div class="print-preview-mount" tabindex="-1"></div>`
  const previewMount = overlay.querySelector('.print-preview-mount')
  const select = overlay.querySelector('.print-page-size')
  const render = () => {
    previewMount.dataset.pageSize = select.value
    previewMount.innerHTML = renderPrintProfileHTML(buildPrintSnapshot(profileState, select.value))
    requestAnimationFrame(() => fitPrintPreview(previewMount))
  }
  select.addEventListener('change', render)
  overlay.querySelector('.print-preview-action').addEventListener('click', print)
  overlay.querySelector('.print-preview-close').addEventListener('click', () => { resizeObserver.disconnect(); overlay.remove() })
  mount.append(overlay)
  const resizeObserver = new ResizeObserver(() => fitPrintPreview(previewMount))
  resizeObserver.observe(previewMount)
  render()
  fetch(`${import.meta.env.BASE_URL}data/local-profile/ahmedabad-boundary.geojson`).then((response) => response.ok ? response.json() : null).then((geojson) => {
    const geometry = geojson?.features?.[0]?.geometry
    if (geometry) { profileState = { ...profileState, boundaryGeometry: geometry }; render() }
  }).catch(() => {})
  return { available: true, overlay }
}
