const AHMEDABAD_BOUNDS = [72.437031, 22.914348, 72.728602, 23.140865]

export function renderA3AtlasHTML(snapshot, disclaimer) {
  const result = snapshot.result ?? {}
  const overview = sectionData(result, 'overview')
  const buildings = sectionData(result, 'buildings')
  const streets = sectionData(result, 'streetsConnectivity')
  const syntax = sectionData(result, 'spaceSyntaxCentrality')
  const environment = sectionData(result, 'environment')
  const transport = sectionData(result, 'publicTransport')
  const amenities = sectionData(result, 'parksEducation')
  const footprint = buildings.provisionalAreaM2 ?? buildings.footprintAreaM2 ?? {}
  const height = buildings.provisionalHeightM ?? {}
  const footprintSummary = metricSummary(footprint)
  const heightSummary = metricSummary(height)
  const lstSummary = metricSummary(environment.lst)
  const ndviSummary = metricSummary(environment.ndvi)
  const footprintBins = distributionBins(footprint)
  const heightBins = distributionBins(height)
  const vegetationPercent = toPercent(environment.vegetationFraction?.mean ?? overview.vegetationFractionMean)
  const connectedPercent = toPercent(streets.connectedNodeRatio)
  const routes = Array.isArray(transport.routesServingStopsInsideCircle)
    ? transport.routesServingStopsInsideCircle.length
    : transport.routesServingStopsInsideCircle
  const areaShare = buildings.storedAreaSharePct ?? buildings.footprintCoveragePct
  const selectionLabel = snapshot.selectionType === 'tps'
    ? String(snapshot.selectionPresentation?.metricValue ?? 'TPS selected area').split('\n')[0]
    : `${formatValue(snapshot.radiusM)} M SELECTED AREA`
  const isTps = snapshot.selectionType === 'tps'
  const meta = isTps
    ? `<div class="atlas-meta-row"><dt>TPS number</dt><dd>${escapeHtml(formatValue(result.selection?.tps_no))}</dd></div><div class="atlas-meta-row"><dt>Area</dt><dd>${escapeHtml(formatValue(result.selection?.areaM2, ' m²'))}</dd></div><div class="atlas-meta-row"><dt>PROFILE</dt><dd>${escapeHtml(formatValue(snapshot.profileId))}</dd></div><div class="atlas-meta-row"><dt>DATE</dt><dd>${escapeHtml(formatValue(snapshot.date))}</dd></div>`
    : `<div class="atlas-meta-row"><dt>COORD.</dt><dd>${escapeHtml(formatCenter(snapshot.center))}</dd></div><div class="atlas-meta-row"><dt>PROFILE</dt><dd>${escapeHtml(formatValue(snapshot.profileId))}</dd></div><div class="atlas-meta-row"><dt>DATE</dt><dd>${escapeHtml(formatValue(snapshot.date))}</dd></div>`

  return `<article class="print-sheet print-page-a3 atlas-sheet" data-page-size="A3" data-template="A3">
    <header class="atlas-header" data-slot="header">
      <div class="atlas-brand"><h1><span class="city">AHMEDABAD</span><span class="system">URBAN SCANNER</span></h1><p class="atlas-prototype">PROTOTYPE</p></div>
      <div class="atlas-title"><h2>LOCAL AREA PROFILE</h2><p>${escapeHtml(selectionLabel)}</p><small>A3 LANDSCAPE</small></div>
      <dl class="atlas-meta${isTps ? ' atlas-meta-tps' : ''}">${meta}</dl>
    </header>
    <div class="atlas-header-rule"></div>
    <div class="atlas-row atlas-row-one">
      ${moduleBlock('00', 'Key map', renderKeyMap(snapshot), { className: 'atlas-map', slot: 'key-map' })}
      ${moduleBlock('01', 'Overview', `<div class="atlas-overview"><div class="atlas-overview-lead"><span>Building locations</span><strong>${escapeHtml(formatValue(buildings.totalLocationCount ?? overview.totalLocationCount))}</strong><small>SELECTION AREA<b>${escapeHtml(formatNumber(selectionAreaKm2(snapshot), 3))} km²</b></small></div>${metric('Footprint-area share', areaShare == null ? null : `${formatNumber(Number(areaShare))}%`)}${metric('Vegetation-positive fraction', vegetationPercent == null ? null : `${formatNumber(vegetationPercent)}%`)}</div>`, { slot: 'overview', section: 'overview' })}
      ${moduleBlock('02', 'Buildings', `<div class="atlas-building-lead"><div><span>SUMMED FOOTPRINT-AREA FIELD</span><strong>${escapeHtml(withUnit(buildings.summedStoredAreaM2 ?? buildings.footprintCoverageM2, 'm²') ?? 'No data')}</strong></div><div><span>DOMINANT SUHI CLASS</span><strong>${escapeHtml(formatValue(buildings.suhi?.summary?.dominantClass))}</strong></div></div><div class="atlas-building-summaries">${summaryPanel('FOOTPRINT AREA · M²', footprintSummary)}${summaryPanel('BUILDING HEIGHT · M', heightSummary)}</div>`, { slot: 'buildings', section: 'buildings' })}
      ${moduleBlock('03', 'Streets & connectivity', `<dl class="atlas-streets">${definitionMetric('Street length', streets.clippedLengthKm, streets.clippedLengthKm == null ? null : `${formatNumber(Number(streets.clippedLengthKm))} km`)}${definitionMetric('Intersections / km²', streets.intersectionDensityPerKm2)}${definitionMetric('Link / node ratio', streets.linkNodeRatio)}${definitionMetric('Connected-node share', streets.connectedNodeRatio, connectedPercent == null ? null : `${formatNumber(connectedPercent)}%`)}</dl>`, { slot: 'streets-connectivity', section: 'streetsConnectivity' })}
    </div>
    <div class="atlas-row atlas-row-two">
      ${moduleBlock('04', 'Space syntax / centrality', `<div class="atlas-syntax">${metric('Centrality betweenness', syntax.centrality?.betweenness?.weightedMean)}${metric('Syntax betweenness', syntax.spaceSyntax?.betweenness?.weightedMean)}${metric('Centrality closeness', syntax.centrality?.closeness?.weightedMean)}${metric('Syntax closeness', syntax.spaceSyntax?.closeness?.weightedMean)}${metric('Centrality straightness', syntax.centrality?.straightness?.weightedMean)}${metric('Syntax straightness', syntax.spaceSyntax?.straightness?.weightedMean)}</div><small class="atlas-method">WEIGHTED BY CLIPPED NETWORK LENGTH</small>`, { slot: 'space-syntax-centrality', section: 'spaceSyntaxCentrality' })}
      ${moduleBlock('05', 'Public transport', `<div class="atlas-transport">${metric('Stops inside selected area', transport.stopsInsideCircle)}${metric('Routes serving stops', routes)}${metric('Route-associated reach', transport.routeReachAreaM2 == null ? null : `${formatNumber(Number(transport.routeReachAreaM2) / 1e6)} km²`)}</div>`, { slot: 'public-transport', section: 'publicTransport' })}
      ${moduleBlock('06', 'Parks and schools', `<div class="atlas-amenities">${metric('Parks / count', amenities.parks?.count ?? amenities.parks?.value)}${metric('Schools / count', amenities.schools?.count ?? amenities.schools?.value)}<p><strong>NORMALIZED POINT SOURCES</strong><br>Inside the selected area. Missing values remain visible as No data.</p></div>`, { slot: 'parks-education', section: 'parksEducation' })}
    </div>
    <div class="atlas-chart-row">
      ${chartBlock('07', 'Footprint area', 'Footprint-area distribution', footprint, [{ label: 'MEAN', value: withUnit(footprintSummary.mean, 'm²') }, { label: 'MEDIAN', value: withUnit(footprintSummary.median, 'm²') }, { label: 'RANGE', value: rangeValue(footprintSummary, 'm²') }, { label: 'MODE', value: withUnit(modeLabel(footprintBins), 'm²') }])}
      ${chartBlock('08', 'Building height', 'Building-height field distribution', height, [{ label: 'MEAN', value: withUnit(heightSummary.mean, 'm') }, { label: 'MEDIAN', value: withUnit(heightSummary.median, 'm') }, { label: 'RANGE', value: rangeValue(heightSummary, 'm') }, { label: 'MODE', value: withUnit(modeLabel(heightBins), 'm') }])}
      ${chartBlock('09', 'Land surface temperature', 'LST distribution · occupied 1°C bins', environment.lst, [{ label: 'MEAN', value: withUnit(lstSummary.mean, '°C') }, { label: 'MEDIAN', value: withUnit(lstSummary.median, '°C') }, { label: 'MAXIMUM', value: withUnit(lstSummary.maximum ?? lstSummary.max, '°C') }, { label: 'VALID AREA', value: environment.lst?.validAreaM2 == null ? null : `${formatNumber(Number(environment.lst.validAreaM2) / 1e6, 3)} km²` }], true, ' data-slot="environment" data-section="environment"')}
      ${chartBlock('10', 'Vegetation / NDVI', 'NDVI distribution', environment.ndvi, [{ label: 'MEAN', value: ndviSummary.mean }, { label: 'MEDIAN', value: ndviSummary.median }, { label: 'VEGETATION+', value: vegetationPercent == null ? null : `${formatNumber(vegetationPercent)}%` }, { label: 'THRESHOLD', value: environment.vegetationFraction?.provenance?.threshold == null ? null : `≥ ${formatValue(environment.vegetationFraction.provenance.threshold)}` }])}
    </div>
    <footer class="atlas-footer print-footer" data-slot="footer">
      <div class="atlas-source"><strong>SOURCE / PROVENANCE</strong><span>${escapeHtml(formatProvenance(snapshot.provenance))}</span><small>MISSING OR UNAVAILABLE CLASSES ARE NOT ZERO · MEAN AND MEDIAN ARE LABELLED SEPARATELY</small></div>
      <div class="atlas-footer-center"><strong>AHMEDABAD URBAN SCANNER</strong></div>
      <div class="atlas-footer-right"><span>FORMAT</span><b>A3 / 420 × 297 MM</b><span>TEMPLATE</span><b>MONO ATLAS</b></div>
      <div class="atlas-disclaimer print-disclaimer"><strong>Experimental data limitation</strong><span>${escapeHtml(disclaimer)}</span></div>
    </footer>
  </article>`
}

function moduleBlock(index, title, body, { className = '', slot = '', section = '' } = {}) {
  const classes = section ? `print-section section-available atlas-module ${className}` : `atlas-module ${className}`
  return `<section class="${classes.trim()}" data-atlas-index="${index}"${slot ? ` data-slot="${slot}"` : ''}${section ? ` data-section="${section}"` : ''}><div class="atlas-module-head"><span>${index}</span><h2>${escapeHtml(title)}</h2></div>${body}</section>`
}

function chartBlock(index, title, chartTitle, metricData, footer, trimEmptyEdges = false, attributes = '') {
  const bins = distributionBins(metricData, trimEmptyEdges)
  const maximum = Math.max(1, ...bins.map(({ value }) => value))
  const availability = metricAvailability(metricData, bins)
  const bars = bins.length
    ? bins.map(({ label, value }) => `<div class="atlas-bar-group"><span>${escapeHtml(formatValue(value))}</span><i class="atlas-bar pattern-hatch" style="--atlas-bar-height:${Math.max(1, value / maximum * 100)}%" aria-label="${escapeAttribute(`${label}: ${formatValue(value)}`)}"></i></div>`).join('')
    : '<div class="atlas-chart-empty">No distribution available</div>'
  const labels = bins.map(({ label }) => `<span>${escapeHtml(cleanBinLabel(label))}</span>`).join('')
  const footerItems = footer.filter(({ value }) => value != null).map(({ label, value }) => `<span>${escapeHtml(label)} ${escapeHtml(formatValue(value))}</span>`).join('')
  const classes = attributes.includes('data-section=') ? 'print-section section-available atlas-module atlas-chart-module' : 'atlas-module atlas-chart-module'
  return `<section class="${classes}" data-atlas-index="${index}"${attributes}><div class="atlas-module-head"><span>${index}</span><h2>${escapeHtml(title)}</h2></div><div class="atlas-chart-wrap"><div class="atlas-chart-title"><span>${escapeHtml(chartTitle)}</span><small>${availability.count == null ? 'VALID N = N/A' : `VALID N = ${escapeHtml(formatValue(availability.count))}`}<br>${availability.coverage == null ? 'COVERAGE N/A' : `COVERAGE ${escapeHtml(formatNumber(availability.coverage))}%`}</small></div><div class="atlas-chart-bars">${bars}</div><div class="atlas-chart-labels">${labels}</div><div class="atlas-chart-foot">${footerItems}</div></div></section>`
}

function metric(label, value) {
  return `<div class="atlas-metric"><span>${escapeHtml(label)}</span><strong>${escapeHtml(formatValue(value))}</strong></div>`
}

function definitionMetric(label, rawValue, presentedValue = null) {
  const value = presentedValue ?? rawValue
  return `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(formatValue(value))}</dd></div>`
}

function summaryPanel(title, summary) {
  return `<section><h3>${escapeHtml(title)}</h3><div>${summaryItem('MEAN', summary.mean)}${summaryItem('MEDIAN', summary.median)}${summaryItem('MIN–MAX', summary.min == null || summary.max == null ? null : `${formatValue(summary.min)}–${formatValue(summary.max)}`)}</div></section>`
}

function summaryItem(label, value) {
  return `<div><span>${escapeHtml(label)}</span><b>${escapeHtml(formatValue(value))}</b></div>`
}

function renderKeyMap(snapshot) {
  const isTps = snapshot.selectionType === 'tps'
  const boundary = snapshot.boundaryGeometry ?? bboxGeometry(AHMEDABAD_BOUNDS)
  const selected = isTps ? snapshot.result?.selection?.geometry : circleGeometry(snapshot.center, snapshot.radiusM)
  const allCoordinates = [...coordinatesFromGeometry(boundary), ...coordinatesFromGeometry(selected)]
  const bounds = extent(allCoordinates.length ? allCoordinates : coordinatesFromGeometry(boundary))
  const project = ([longitude, latitude]) => `${(((longitude - bounds[0]) / (bounds[2] - bounds[0] || 1)) * 100).toFixed(2)},${(100 - ((latitude - bounds[1]) / (bounds[3] - bounds[1] || 1)) * 100).toFixed(2)}`
  const path = (geometry) => geometryPaths(geometry).map((ring) => `M ${ring.map(project).join(' L ')} Z`).join(' ')
  const selectedClass = isTps ? 'selected-tps' : 'selected-circle'
  const markerPoint = !isTps && Array.isArray(snapshot.center) ? project(snapshot.center).split(',') : null
  const marker = !isTps && Number(snapshot.radiusM) < 600 && markerPoint ? `<circle class="locator-halo" cx="${markerPoint[0]}" cy="${markerPoint[1]}" r="2.8" />` : ''
  return `<div class="print-key-map" data-map-kind="print-map-placeholder" aria-label="Ahmedabad boundary-only locator map"><span class="print-map-title">${isTps ? 'TPS boundary key map' : 'Selected-area key map'}</span><svg viewBox="0 0 100 100" role="img" aria-label="Ahmedabad municipal boundary and selected geometry"><path id="ahmedabad-boundary" class="ahmedabad-boundary" d="${path(boundary)}"/><path class="${selectedClass}" d="${path(selected)}"/>${marker}<g class="north-arrow"><path d="M 92 16 L 92 7 M 92 7 L 89 12 M 92 7 L 95 12"/></g><g class="scale-bar"><path d="M 8 92 H 28 M 8 90 V 94 M 28 90 V 94"/><text x="8" y="88">approx. 5 km</text></g></svg><span class="print-map-note">Ahmedabad boundary only; selected geometry is highlighted. Approximate scale, not survey accuracy.</span><span class="print-map-center">Center: ${escapeHtml(formatCenter(snapshot.center))}</span></div>`
}

function sectionData(result, key) {
  const section = result.sections?.[key]
  if (section?.status === 'available') return section.data ?? {}
  return result[key] ?? {}
}

function metricSummary(metricData) {
  return metricData?.summary ?? metricData ?? {}
}

function distributionBins(metricData, trimEmptyEdges = false) {
  const distribution = metricData?.distribution ?? metricData?.histogram ?? metricData?.summary?.histogram
  if (!Array.isArray(distribution?.bins) || !Array.isArray(distribution?.counts) || distribution.bins.length !== distribution.counts.length + 1) return []
  let first = 0
  let last = distribution.counts.length - 1
  if (trimEmptyEdges) {
    while (first < last && Number(distribution.counts[first]) === 0) first += 1
    while (last > first && Number(distribution.counts[last]) === 0) last -= 1
  }
  return distribution.counts.slice(first, last + 1).map((count, offset) => ({
    label: `${formatValue(distribution.bins[first + offset])}–${formatValue(distribution.bins[first + offset + 1])}`,
    value: Number(count || 0),
  }))
}

function metricAvailability(metricData, bins) {
  const derivedCount = bins.length ? bins.reduce((sum, bin) => sum + bin.value, 0) : null
  const count = finiteNumber(metricData?.availability?.available ?? metricData?.validPixelCount ?? derivedCount)
  const denominator = finiteNumber(metricData?.availability?.denominator ?? metricData?.expectedPixelCount ?? count)
  const explicitCoverage = finiteNumber(metricData?.coveragePercentage ?? metricData?.validCoveragePct)
  return {
    count,
    coverage: explicitCoverage ?? (count != null && denominator != null && denominator > 0 ? count / denominator * 100 : null),
  }
}

function modeLabel(bins) {
  if (!bins.length) return null
  return cleanBinLabel(bins.reduce((best, bin) => bin.value > best.value ? bin : best, bins[0]).label)
}

function rangeValue(summary, unit) {
  return summary.min == null || summary.max == null ? null : `${formatValue(summary.min)}–${formatValue(summary.max)} ${unit}`
}

function withUnit(value, unit) {
  return value == null ? null : `${formatValue(value)} ${unit}`
}

function cleanBinLabel(label) {
  return String(label).replace('–<', '–')
}

function selectionAreaKm2(snapshot) {
  const explicitArea = finiteNumber(snapshot.result?.selection?.areaM2)
  if (explicitArea != null) return explicitArea / 1e6
  const radius = finiteNumber(snapshot.radiusM)
  return radius == null ? null : Math.PI * radius * radius / 1e6
}

function toPercent(value) {
  const number = finiteNumber(value)
  if (number == null) return null
  return number <= 1 ? number * 100 : number
}

function finiteNumber(value) {
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

function formatCenter(center) {
  return Array.isArray(center) && center.length === 2 ? `${formatNumber(Number(center[0]), 6)}, ${formatNumber(Number(center[1]), 6)}` : 'No data'
}

function formatNumber(value, maximumFractionDigits = 2) {
  if (!Number.isFinite(value)) return 'No data'
  if (Number.isInteger(value)) return value.toLocaleString('en-US')
  if (value !== 0 && Math.abs(value) < 0.01) return Number(value.toPrecision(2)).toString()
  return value.toLocaleString('en-US', { maximumFractionDigits })
}

function formatValue(value, suffix = '') {
  if (value == null || value === '') return 'No data'
  if (typeof value === 'number') return `${formatNumber(value)}${suffix}`
  if (Array.isArray(value)) return `${value.map((item) => formatValue(item)).join(', ')}${suffix}`
  if (typeof value === 'object') return 'No data'
  return `${String(value)}${suffix}`
}

function formatProvenance(provenance) {
  if (provenance == null) return 'No provenance supplied in this result.'
  if (typeof provenance === 'string') return provenance
  return Object.entries(provenance).slice(0, 4).map(([key, value]) => `${key.replace(/^./, (character) => character.toUpperCase())}: ${formatValue(value)}`).join(' · ').slice(0, 180)
}

function bboxGeometry([west, south, east, north]) {
  return { type: 'Polygon', coordinates: [[[west, south], [east, south], [east, north], [west, north], [west, south]]] }
}

function circleGeometry(center, radiusM) {
  if (!Array.isArray(center) || center.length !== 2 || !Number.isFinite(Number(radiusM))) return null
  const [longitude, latitude] = center.map(Number)
  const latitudeDelta = Number(radiusM) / 111320
  const longitudeDelta = Number(radiusM) / (111320 * Math.cos(latitude * Math.PI / 180))
  return { type: 'Polygon', coordinates: [Array.from({ length: 48 }, (_, index) => {
    const angle = index / 48 * Math.PI * 2
    return [longitude + Math.cos(angle) * longitudeDelta, latitude + Math.sin(angle) * latitudeDelta]
  }).concat([[longitude + longitudeDelta, latitude]])] }
}

function geometryPaths(geometry) {
  if (!geometry) return []
  if (geometry.type === 'Polygon') return geometry.coordinates
  if (geometry.type === 'MultiPolygon') return geometry.coordinates.flat()
  return []
}

function coordinatesFromGeometry(geometry) {
  return geometryPaths(geometry).flat().filter((point) => Array.isArray(point) && point.length === 2)
}

function extent(points) {
  return [Math.min(...points.map(([x]) => x)), Math.min(...points.map(([, y]) => y)), Math.max(...points.map(([x]) => x)), Math.max(...points.map(([, y]) => y))]
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[character])
}

function escapeAttribute(value) {
  return escapeHtml(value)
}
