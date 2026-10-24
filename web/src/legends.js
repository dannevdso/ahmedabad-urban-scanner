import { legendEntries, getIndicator, NO_DATA_COLOR } from './indicators.js'
import { resolveContext } from './context.js'
import { spaceSyntaxSidebarDescription } from './sidebar_descriptions.js'

const FALLBACK_COLORS = {
  gtfsShapes: '#0f766e', gtfsStops: '#b45309', network: '#440154', centrality: '#2563eb',
  floodRiskZones: '#d7301f',
  deadends: '#be123c', serviceAreas: '#94412f', proposedSites: '#f97316',
  greenConnectivity: '#16a34a', heatRisk: '#ea580c', routes: '#94412f',
}

const BRAND_LEGEND_COLORS = {
  transitIsochrones: ['#94412f', 'rgba(148, 65, 47, 0)', '#f59e0b'],
  tpsProvisional: ['#94412f'],
}

function contextText(metadata, contextKey) {
  const context = resolveContext(metadata, contextKey)
  return [context.scopeLabel, context.statusLabel, context.temporalLabel].filter(Boolean).join(' · ')
}

function fallbackRecord(key, overlay, metadata) {
  const geometry = overlay?.layers?.[0]?.type ?? 'circle'
  const color = FALLBACK_COLORS[key] ?? '#525252'
  const kind = key === 'proposedSites' ? 'scenario' : 'single-symbol'
  return {
    key,
    title: overlay?.label ?? key,
    kind,
    geometry,
    context_key: overlay?.contextKey ?? 'scope-unverified',
    entries: [{ label: overlay?.label ?? key, color, shape: geometry }],
    caveat: overlay?.description ?? 'Legend metadata is unavailable; the current renderer is represented conservatively without inventing a numeric scale.',
    numeric_applicable: false,
    unit: '',
    unit_status: 'not_documented',
    ...metadata,
  }
}

function buildingSection(key) {
  if (!key) {
    return {
      key: 'building-footprints',
      title: 'Building footprints',
      subtitle: 'Fixed display style',
      source: 'building',
      kind: 'single-symbol',
      geometry: 'fill',
      entries: [{ label: 'Mapped footprint', color: '#b8c7d1', shape: 'fill' }],
      contextKey: 'full-study-current',
      caveat: 'Geometry-only display tiles. Individual footprints are not selectable and carry no display attributes.',
      unitStatus: 'verified',
    }
  }
  const indicator = getIndicator(key)
  return {
    key,
    title: indicator.shortLabel,
    subtitle: indicator.unit.trim() || 'index',
    source: 'building',
    kind: 'classification',
    geometry: 'fill',
    entries: legendEntries(key).map((entry) => ({ ...entry, shape: 'fill' })),
    noData: true,
    contextKey: indicator.contextKey,
    caveat: indicator.description ?? indicator.method,
    unitStatus: 'verified',
  }
}

function metadataRecord(metadata, key, overlay, spaceSyntaxKey) {
  if (spaceSyntaxKey !== 'off') {
    const record = metadata?.overlay_legends?.spaceSyntax?.[spaceSyntaxKey]
    return record ?? fallbackRecord(spaceSyntaxKey, { key: spaceSyntaxKey, label: spaceSyntaxKey, contextKey: 'supplied-external', layers: [{ type: spaceSyntaxKey === 'betweenness' ? 'circle' : 'line' }] }, metadata)
  }
  return metadata?.overlay_legends?.[key] ?? fallbackRecord(key, overlay, metadata)
}

function normaliseRecord(record) {
  const entries = Array.isArray(record.entries) ? record.entries : []
  const brandColors = BRAND_LEGEND_COLORS[record.key]
  return {
    ...record,
    kind: record.kind === 'categorical' ? 'classification' : record.kind,
    unitStatus: record.unit_status ?? 'not_documented',
    contextKey: record.context_key ?? 'scope-unverified',
    rendererProperty: record.renderer_property ?? null,
    entries: entries.map((entry, index) => ({ ...entry, color: brandColors?.[index] ?? entry.color, shape: entry.shape ?? record.geometry })),
  }
}

export function buildLegendState({ activeIndicatorKey, activePlanxOverlays, spaceSyntaxKey, metadata = {}, planxOverlays = [] }) {
  const active = activePlanxOverlays instanceof Set ? activePlanxOverlays : new Set(activePlanxOverlays ?? [])
  const sections = []
  if (spaceSyntaxKey && spaceSyntaxKey !== 'off') {
    const record = normaliseRecord(metadataRecord(metadata, null, null, spaceSyntaxKey))
    if (record.kind !== 'off') sections.push({ ...record, description: spaceSyntaxSidebarDescription(spaceSyntaxKey) })
  }
  for (const overlay of planxOverlays) {
    if (!active.has(overlay.key)) continue
    const record = normaliseRecord(metadataRecord(metadata, overlay.key, overlay, 'off'))
    if (record.kind !== 'off') sections.push(record)
  }
  return {
    sections: sections.length ? sections : [buildingSection(activeIndicatorKey)],
    activeOverlay: sections.length > 0,
    metadata,
  }
}

export function legendHelpText(state) {
  return state.sections.map((section) => {
    const context = section.contextLabel ?? section.contextKey
    const detail = [context, section.caveat, section.validation_status === 'unverified' ? 'Validation status: unverified.' : ''].filter(Boolean).join(' · ')
    return `${section.title}: ${detail}`
  }).join('\n')
}

function appendText(parent, tag, text, className) {
  const node = document.createElement(tag)
  if (className) node.className = className
  node.textContent = text
  parent.append(node)
  return node
}

export function legendSwatchBackground(entry) {
  const stops = Array.isArray(entry?.palette_stops) ? entry.palette_stops : []
  const validStops = stops.filter((stop) => Number.isFinite(stop?.value) && typeof stop?.color === 'string')
  if (validStops.length >= 2) {
    const gradientStops = validStops
      .map((stop) => `${stop.color} ${Math.max(0, Math.min(1, stop.value)) * 100}%`)
      .join(', ')
    return `linear-gradient(to right, ${gradientStops})`
  }
  return entry?.color ?? NO_DATA_COLOR
}

export function resetButtonBottom(viewportWidth, legendHeight) {
  return viewportWidth <= 720 ? `${Math.max(104, legendHeight + 42)}px` : ''
}

export function renderLegend(container, state) {
  container.replaceChildren()
  container.setAttribute('aria-live', 'polite')
  for (const section of state.sections) {
    const sectionNode = document.createElement('section')
    sectionNode.className = `legend-section legend-kind-${section.kind}`
    const heading = appendText(sectionNode, 'h3', section.title, 'legend-section-title')
    heading.setAttribute('aria-label', `${section.title} legend`)
    if (section.subtitle || section.unit) appendText(sectionNode, 'p', section.subtitle ?? section.unit, 'legend-section-unit')
    if (section.description) appendText(sectionNode, 'p', section.description, 'legend-section-description')
    const list = document.createElement('div')
    list.className = 'legend-scale'
    for (const entry of section.entries ?? []) {
      const item = document.createElement('div')
      item.className = 'legend-item'
      const swatch = document.createElement('i')
      swatch.className = `legend-swatch legend-shape-${entry.shape ?? section.geometry}`
      swatch.style.background = legendSwatchBackground(entry)
      swatch.setAttribute('aria-hidden', 'true')
      item.append(swatch)
      appendText(item, 'span', entry.label ?? 'Unlabelled', 'legend-label')
      list.append(item)
    }
    sectionNode.append(list)
    if (section.noData) {
      const item = document.createElement('div')
      item.className = 'legend-no-data'
      const swatch = document.createElement('i')
      swatch.style.background = NO_DATA_COLOR
      swatch.setAttribute('aria-hidden', 'true')
      item.append(swatch)
      appendText(item, 'span', 'No data')
      sectionNode.append(item)
    }
    container.append(sectionNode)
  }
}

export function renderLegendHelp(container, state) {
  container.replaceChildren()
  container.setAttribute('aria-live', 'polite')
  for (const section of state.sections) {
    const item = document.createElement('p')
    appendText(item, 'strong', section.title)
    const context = contextText(state.metadata ?? {}, section.contextKey)
    item.append(document.createTextNode(`: ${[context, section.caveat].filter(Boolean).join(' · ')}`))
    container.append(item)
  }
}
