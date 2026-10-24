import { addProtocol, AttributionControl, Map, NavigationControl, setWorkerUrl } from 'maplibre-gl'
import mapLibreWorkerUrl from '../node_modules/maplibre-gl/dist/maplibre-gl-worker.mjs?url'
import { Protocol } from 'pmtiles'
import './styles.css'
import { resolveItemContextKey } from './context.js'

import { baseLayerVisibilityUpdates, captureBaseLayerVisibility, isRoadLayer } from './map_controls.js'
import { PLANX_OVERLAYS, PLANX_SOURCES, SPACE_SYNTAX_FIELDS, SPACE_SYNTAX_LAYER, SPACE_SYNTAX_POINT_LAYER, activateExclusiveOverlay, applyPlanxClassifications, orderedPlanxOverlays, overlayControlCategory, overlayControlSubheading, overlayRegistration, planxSummaryLabel, planxVisibilityUpdates, reorderPlanxLayers, spaceSyntaxPaint, spaceSyntaxVisibilityUpdates } from './planx_layers.js'
import { buildLegendState, renderLegend, renderLegendHelp } from './legends.js'

import { buildFloodRiskDetails } from './flood_risk_details.js'
import { indicatorSidebarDescription, overlaySidebarDescription, spaceSyntaxSidebarDescription } from './sidebar_descriptions.js'
import { buildRouteReachCatchment } from './transit_isochrones.js'
import { buildStopDetails, formatAreaM2, graphAxisTicks, graphHourTicks, graphSeries, routeColor, selectedRouteFilter } from './transit_details.js'
import { buildChartModel, buildCircleFeature, buildTpsFeatureIndex, createPreviewScheduler, createProfileState, normalizeProfileResult, profileSelectionPresentation, resolveTpsSelection, updateProfileState } from './local_area_profile.js'
import { createLocalAreaProfileService } from './local_area_profile_service.js'
import { buildBuildingsPresentation, buildEnvironmentPresentation, buildParksSchoolsPresentation, buildPublicTransportPresentation, buildSpaceSyntaxPresentation, buildStreetsPresentation } from './profile_presentations.js'
import { getPrintAvailability, openPrintProfilePreview } from './print_profile.js'
import './print_profile.css'

const BASE_STYLE = 'https://tiles.openfreemap.org/styles/liberty'
const BUILDING_SOURCE = 'buildings'
const BUILDING_FILL = 'building-fill'
const BUILDING_OUTLINE = 'building-outline'
const BUILDING_FILL_COLOR = '#b8c7d1'

let metadata
let map
let basemapLayerVisibility = []
const activePlanxOverlays = new Set()
const registeredPlanxOverlays = new Set()
let transitIsochroneInteractionsBound = false
let floodRiskInteractionsBound = false
let tpsInteractionsBound = false
let exactTpsFeatureIndexPromise = null
let transitIsochroneModelPromise = null
let transitStopIndex = null
let transitSelection = null
let transitSelectionRequest = 0
let profileState = createProfileState()
let profileDrag = null
let profilePreviewScheduler
let profileRequestId = 0
let inspectorMode = null
let profileChartSequence = 0
const localAreaProfileService = createLocalAreaProfileService()


setWorkerUrl(mapLibreWorkerUrl)
const pmtilesProtocol = new Protocol()
addProtocol('pmtiles', pmtilesProtocol.tile)

const elements = {
  basemapToggle: document.querySelector('#basemap-toggle'),
  buildingToggle: document.querySelector('#building-toggle'),
  buildingCount: document.querySelector('#building-count'),
  buildingDetails: document.querySelector('#building-details'),
  evidenceNote: document.querySelector('#evidence-note'),
  catchmentOpacityControl: document.querySelector('#catchment-opacity-control'),
  catchmentOpacityValue: document.querySelector('#catchment-opacity-value'),
  routeStopOpacityControl: document.querySelector('#route-stop-opacity-control'),
  routeStopOpacityValue: document.querySelector('#route-stop-opacity-value'),
  transitDetails: document.querySelector('#transit-details'),
  inspectorEyebrow: document.querySelector('#inspector-eyebrow'),
  buildingId: document.querySelector('#building-id'),
  closeInspector: document.querySelector('#close-inspector'),
  closeMethod: document.querySelector('#close-method'),

  indicatorContext: document.querySelector('#indicator-context'),
  indicatorGroup: document.querySelector('#indicator-group'),
  indicatorGroups: document.querySelector('#indicator-groups'),
  indicatorTitle: document.querySelector('#indicator-title'),
  featuredTransitControl: document.querySelector('#featured-transit-control'),
  inspector: document.querySelector('#inspector'),
  legend: document.querySelector('#legend'),
  legendHelp: document.querySelector('#legend-help'),
  legendWrap: document.querySelector('.legend-wrap'),
  legendInfoButton: document.querySelector('#legend-info-button'),
  limitations: document.querySelector('#limitations'),
  loadingPanel: document.querySelector('#loading-panel'),
  menuToggle: document.querySelector('#menu-toggle'),
  methodButton: document.querySelector('#method-button'),
  methodDialog: document.querySelector('#method-dialog'),
  methodDone: document.querySelector('#method-done'),
  opacityControl: document.querySelector('#opacity-control'),
  opacityValue: document.querySelector('#opacity-value'),
  planxActiveSummary: document.querySelector('#planx-active-summary'),
  planxOverlayControls: document.querySelector('#planx-overlay-controls'),
  spaceSyntaxSelect: document.querySelector('#space-syntax-select'),
  resetView: document.querySelector('#reset-view'),
  roadsToggle: document.querySelector('#roads-toggle'),
  selectedMethod: document.querySelector('#selected-method'),
  selectedMetric: document.querySelector('.selected-metric'),
  selectedMetricLabel: document.querySelector('#selected-metric-label'),
  selectedMetricValue: document.querySelector('#selected-metric-value'),
  selectedSource: document.querySelector('#selected-source'),
  sidebar: document.querySelector('#sidebar'),
  sidebarCollapse: document.querySelector('#sidebar-collapse'),
  sidebarScrim: document.querySelector('#sidebar-scrim'),
  summaryPeriod: document.querySelector('#summary-period'),
  summaryValue: document.querySelector('#summary-value'),
  profileRadius: document.querySelector('#profile-radius'),
  profilePlace: document.querySelector('#profile-place'),
  profileClear: document.querySelector('#profile-clear'),
  profileStatus: document.querySelector('#profile-status'),
  profileDashboard: document.querySelector('#local-profile-dashboard'),
  profileDashboardTitle: document.querySelector('#profile-dashboard-title'),
  profileInspectorStatus: document.querySelector('#profile-inspector-status'),
  profileDashboardSections: document.querySelector('#profile-dashboard-sections'),
  profilePrint: document.querySelector('#profile-print'),
  tpsProvisionalControl: document.querySelector('#tps-provisional-control'),
}

async function bootstrap() {
  try {
    metadata = await fetchJson('./data/metadata.json')
    renderStaticMetadata()
    renderIndicatorControls()
    renderSpaceSyntaxControl()
    renderPlanxControls()
    initialiseMap()
    bindInterface()
    addSidebarReopenControl()
  } catch (error) {
    showLoadingError(error)
  }
}

async function fetchJson(url) {
  const response = await fetch(url)
  if (!response.ok) throw new Error(`Could not load ${url}: ${response.status}`)
  return response.json()
}

function initialiseMap() {
  map = new Map({
    container: 'map',
    style: BASE_STYLE,
    center: metadata.centre_wgs84,
    zoom: 13.7,
    minZoom: 11,
    maxZoom: 19,
    attributionControl: false,
  })
  if (import.meta.env.DEV) window.__urbanScannerMap = map

  map.addControl(new NavigationControl({ showCompass: false }), 'bottom-right')
  map.addControl(
    new AttributionControl({
      compact: true,
      customAttribution: 'Buildings: Google Open Buildings · GTFS transit feed · Ahmedabad Urban Scanner',
    }),
    'bottom-right',
  )

  map.on('load', () => {
    basemapLayerVisibility = captureBaseLayerVisibility(map.getStyle().layers)
    setBaseLayerVisibility()
    const firstSymbolLayer = map.getStyle().layers?.find((layer) => layer.type === 'symbol')?.id
    map.addSource(BUILDING_SOURCE, {
      type: 'vector',
      url: 'pmtiles://./data/buildings.pmtiles',
      generateId: true,
    })


    map.addLayer({
      id: BUILDING_FILL,
      type: 'fill',
      source: BUILDING_SOURCE,
      'source-layer': 'buildings',
      paint: {
        'fill-color': BUILDING_FILL_COLOR,
        'fill-opacity': Number(elements.opacityControl.value) / 100,
      },
    }, firstSymbolLayer)
    map.addLayer({
      id: BUILDING_OUTLINE,
      type: 'line',
      source: BUILDING_SOURCE,
      'source-layer': 'buildings',
      minzoom: 15,
      paint: {
        'line-color': 'rgba(22,22,22,0.45)',
        'line-width': ['interpolate', ['linear'], ['zoom'], 15, 0.15, 18, 0.7],
      },
    }, firstSymbolLayer)

    map.addSource('local-profile-circle', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
    map.addLayer({
      id: 'local-profile-circle-fill', type: 'fill', source: 'local-profile-circle',
      paint: { 'fill-color': '#94412f', 'fill-opacity': 0.08 },
    })
    map.addLayer({
      id: 'local-profile-circle-line', type: 'line', source: 'local-profile-circle',
      paint: { 'line-color': '#6f2f24', 'line-width': 2, 'line-dasharray': [2, 1] },
    })

    fitStudyBounds(false)
    updateLegend()
    bindMapInteractions()
    bindProfileMapInteractions()
  })

  map.on('error', (event) => {
    if (!map.loaded()) console.error('Map error', event.error)
  })
}

function bindMapInteractions() {
  map.on('sourcedata', (event) => {
    if (event.sourceId === BUILDING_SOURCE && event.isSourceLoaded) {
      elements.loadingPanel.classList.add('loaded')
    }
  })
}

function bindProfileMapInteractions() {
  map.on('click', 'local-profile-circle-fill', () => {
    if (profileState.result) renderProfileDashboard(profileState.result)
    else renderProfileInspectorState()
  })
  map.on('click', (event) => {
    if (!map.getCanvas().classList.contains('profile-placement-mode')) return
    map.getCanvas().classList.remove('profile-placement-mode')
    updateProfileCircle(event.lngLat.toArray(), Number(elements.profileRadius.value), true)
  })
  map.on('mousedown', 'local-profile-circle-fill', (event) => {
    if (event.originalEvent?.button !== 0) return
    profileDrag = { center: event.lngLat.toArray() }
    renderProfileInspectorState()
    map.getCanvas().style.cursor = 'grabbing'
    map.dragPan.disable()
  })
  map.on('mousemove', (event) => {
    if (!profileDrag) return
    profileDrag.center = event.lngLat.toArray()
    profileState = updateProfileState(profileState, { type: 'preview', center: profileDrag.center, radiusM: profileState.radiusM })
    renderProfileStatus()
    updateProfileCircleSource(profileDrag.center, profileState.radiusM)
    profilePreviewScheduler.schedule({ center: profileDrag.center, radiusM: profileState.radiusM })
  })
  map.on('mouseup', () => {
    if (!profileDrag) return
    const center = profileDrag.center
    profileDrag = null
    map.dragPan.enable()
    map.getCanvas().style.cursor = ''
    updateProfileCircle(center, profileState.radiusM, true)
  })
}

function updateProfileCircle(center, radiusM, finalize = false) {
  profileState = updateProfileState(profileState, { type: 'preview', center, radiusM })
  updateProfileCircleSource(center, radiusM)
  renderProfileInspectorState()
  renderProfileStatus()
  if (finalize) requestProfile({ center, radiusM }, true)
  else profilePreviewScheduler.schedule({ center, radiusM })
}

function updateProfileCircleSource(center, radiusM) {
  map?.getSource('local-profile-circle')?.setData(buildCircleFeature(center, radiusM))
}

async function requestProfile(payload, finalize) {
  const requestId = ++profileRequestId
  profileState = updateProfileState(profileState, { type: 'request', requestId })
  renderProfileStatus()
  try {
    const result = await localAreaProfileService.query({ ...payload, phase: finalize ? 'release' : 'preview' })
    if (requestId !== profileRequestId) return
    profileState = updateProfileState(profileState, { type: 'resolved', requestId, result: normalizeProfileResult(result) })
    renderProfileDashboard(profileState.result)
    renderProfileStatus()
  } catch (error) {
    if (requestId !== profileRequestId) return
    if (error.name === 'AbortError') return
    elements.profileStatus.textContent = `Profile unavailable: ${error.message}`
    if (inspectorMode === 'profile') {
      elements.profileInspectorStatus.textContent = `Profile unavailable: ${error.message}`
    }
  }
}

function renderProfileStatus() {
  const status = profileStatusLabel()
  elements.profileStatus.textContent = status
  if (inspectorMode === 'profile') {
    renderProfileCoordinates()
    elements.profileInspectorStatus.textContent = status
  }
  const printAvailability = getPrintAvailability(profileState)
  elements.profilePrint.disabled = !printAvailability.available
  elements.profilePrint.setAttribute('aria-disabled', printAvailability.available ? 'false' : 'true')
}

function profileStatusLabel() {
  const labels = { empty: 'No profile selected', preview: 'Preview', updating: 'Updating…', ready: 'Profile ready' }
  return labels[profileState.status] ?? profileState.status
}

function renderProfileCoordinates() {
  const presentation = profileSelectionPresentation(profileState.result ?? { selection: profileState.selection, center: profileState.center, radiusM: profileState.radiusM })
  elements.selectedMetricLabel.textContent = presentation.metricLabel
  elements.selectedMetricValue.textContent = presentation.metricValue
}

function showInspectorMode(mode) {
  inspectorMode = mode
  elements.selectedMetric.classList.toggle('profile-coordinate-metric', mode === 'profile')
  elements.profileDashboard.hidden = mode !== 'profile'
  elements.buildingDetails.hidden = mode !== 'floodRisk'
  elements.transitDetails.hidden = mode !== 'transit'
  elements.evidenceNote.hidden = mode === 'profile'
  elements.inspector.classList.add('open')
  elements.inspector.setAttribute('aria-hidden', 'false')
  elements.inspector.inert = false
}

function renderProfileInspectorState() {
  showInspectorMode('profile')
  const presentation = profileSelectionPresentation(profileState.result ?? { selection: profileState.selection, center: profileState.center, radiusM: profileState.radiusM })
  elements.inspectorEyebrow.textContent = presentation.eyebrow
  elements.buildingId.textContent = presentation.title
  renderProfileCoordinates()
  elements.profileDashboardTitle.textContent = profileState.selection?.type === 'tps' || profileState.result?.selection?.type === 'tps' ? `${presentation.title} · exact boundary` : `${profileState.radiusM} m circular study area`
  elements.profileInspectorStatus.textContent = profileStatusLabel()
}

function renderProfileDashboard(result) {
  renderProfileInspectorState()
  elements.profileDashboardSections.replaceChildren()
  const labels = {
    overview: 'Overview', buildings: 'Buildings', streetsConnectivity: 'Streets / connectivity',
    spaceSyntaxCentrality: 'Space syntax / centrality', environment: 'Environment', publicTransport: 'Public transport',
    parksEducation: 'Parks and schools',
  }
  for (const [key, label] of Object.entries(labels)) {
    const details = document.createElement('details')
    details.className = 'profile-section'
    details.open = key === 'overview'
    const summary = document.createElement('summary')
    summary.textContent = label
    const body = document.createElement('div')
    const section = result.sections[key]
    if (section.status !== 'available') {
      body.append(renderUnavailableProfileState())
    } else if (key === 'buildings') {
      body.append(renderProfilePresentation(buildBuildingsPresentation(section), key))
    } else if (key === 'streetsConnectivity') {
      body.append(renderProfilePresentation(buildStreetsPresentation(section), key))
    } else if (key === 'environment') {
      body.append(renderProfilePresentation(buildEnvironmentPresentation(section), key))
    } else if (key === 'spaceSyntaxCentrality') {
      body.append(renderSpaceSyntaxPresentation(buildSpaceSyntaxPresentation(section), key))
    } else if (key === 'publicTransport') {
      body.append(renderPublicTransportPresentation(buildPublicTransportPresentation(section), key))
    } else if (key === 'parksEducation') {
      body.append(renderParksSchoolsPresentation(buildParksSchoolsPresentation(section), key))
    } else if (Array.isArray(section.data?.charts)) {
      body.append(...section.data.charts.map((chart) => renderProfileChart(buildChartModel(chart))))
    } else {
      body.append(renderProfileData(section.data, key === 'overview' ? 'Unavailable' : 'No data'))
    }
    details.append(summary, body)
    elements.profileDashboardSections.append(details)
  }
  elements.inspector.scrollTop = 0
}

const PROFILE_SECTION_INTROS = {
  buildings: 'Building statistics use the published analytical asset within the selected profile boundary; the method and validity are stated below.',
  streetsConnectivity: 'Street-network structure inside the selected profile boundary, using authoritative endpoint identifiers and exactly clipped street length.',
  environment: 'Valid-cell summaries from one-scene, derived, and modelled environmental sources; validity differs by metric.',
}

function renderProfilePresentation(model, key) {
  const fragment = document.createDocumentFragment()
  if (model.status === 'unavailable') {
    const message = document.createElement('p')
    message.className = 'profile-unavailable-state'
    message.textContent = 'Unavailable in this result.'
    fragment.append(message)
    return fragment
  }
  const intro = document.createElement('p')
  intro.className = 'profile-section-intro'
  intro.textContent = PROFILE_SECTION_INTROS[key]
  fragment.append(intro)
  if (model.kpis.length) fragment.append(renderProfileKpis(model.kpis))
  for (const chart of model.charts) fragment.append(renderProfileColumnChart(chart))
  if (model.vegetationThreshold) fragment.append(renderVegetationThresholdChart(model.vegetationThreshold))
  const detailRows = model.details?.rows ?? []
  const numericDetailRows = detailRows.filter((row) => row.kind !== 'categorical')
  const categoricalDetailRows = detailRows.filter((row) => row.kind === 'categorical')
  if (numericDetailRows.length) fragment.append(renderProfileDetailTable(numericDetailRows))
  if (categoricalDetailRows.length) fragment.append(renderProfileCategoricalDetailTable(categoricalDetailRows))
  if (model.metrics?.length) fragment.append(renderProfileValidity(model.metrics))
  if (model.caveats.length) {
    const notes = document.createElement('div')
    notes.className = 'profile-method-note'
    for (const caveat of model.caveats) {
      const line = document.createElement('p')
      line.textContent = caveat
      notes.append(line)
    }
    fragment.append(notes)
  }
  return fragment
}

function renderUnavailableProfileState() {
  const message = document.createElement('p')
  message.className = 'profile-unavailable-state'
  message.textContent = 'Unavailable in this result.'
  return message
}

function renderProfileGroupedTable(captionText, group) {
  const table = document.createElement('table')
  table.className = 'profile-grouped-table'
  const caption = document.createElement('caption')
  caption.textContent = captionText
  table.append(caption)
  const head = document.createElement('thead')
  const headerRow = document.createElement('tr')
  for (const label of ['Metric', 'Value', 'Unit']) {
    const heading = document.createElement('th')
    heading.scope = 'col'
    heading.textContent = label
    headerRow.append(heading)
  }
  head.append(headerRow)
  const body = document.createElement('tbody')
  const rows = group?.rows ?? group?.metrics ?? []
  for (const row of rows) {
    const tr = document.createElement('tr')
    const label = row.label ?? row.name ?? row.key ?? 'Metric'
    const value = row.displayValue ?? row.value ?? row.mean ?? null
    const values = [label, value == null ? 'Unavailable' : formatProfileValue(value), row.unit ?? '']
    values.forEach((valueText, index) => {
      const cell = document.createElement(index === 0 ? 'th' : 'td')
      if (index === 0) cell.scope = 'row'
      cell.textContent = valueText
      tr.append(cell)
    })
    body.append(tr)
  }
  table.append(head, body)
  return table
}

function renderProfilePresentationTables(model, captionText) {
  const fragment = document.createDocumentFragment()
  const groups = model.groups ?? model.metricGroups ?? []
  for (const group of groups) fragment.append(renderProfileGroupedTable(group.caption ?? captionText, group))
  if (!groups.length && (model.rows ?? model.details?.rows)?.length) {
    fragment.append(renderProfileGroupedTable(captionText, { rows: model.rows ?? model.details.rows }))
  }
  return fragment
}

function renderSpaceSyntaxPresentation(model) {
  if (model.status === 'unavailable') return renderUnavailableProfileState()
  const fragment = document.createDocumentFragment()
  if (model.intro) {
    const intro = document.createElement('p')
    intro.className = 'profile-section-intro'
    intro.textContent = model.intro
    fragment.append(intro)
  }
  if (model.kpis?.length) fragment.append(renderProfileKpis(model.kpis))
  fragment.append(renderProfilePresentationTables(model, 'Space syntax / centrality metrics'))
  return appendProfileCaveats(fragment, model.caveats ?? model.caveat)
}

function renderPublicTransportPresentation(model) {
  if (model.status === 'unavailable') return renderUnavailableProfileState()
  const fragment = document.createDocumentFragment()
  if (model.kpis?.length) fragment.append(renderProfileKpis(model.kpis))
  const groups = model.reachGroups ?? model.groups ?? [
    model.localReach ? { label: 'Local reach', rows: model.localReach } : null,
    model.routeReach ? { label: 'Route reach', rows: model.routeReach } : null,
  ].filter(Boolean)
  for (const group of groups) fragment.append(renderProfileGroupedTable(group.caption ?? group.label ?? 'Public transport reach', group))
  return appendProfileCaveats(fragment, model.caveats ?? model.caveat)
}

function renderParksSchoolsPresentation(model) {
  if (model.status === 'unavailable') return renderUnavailableProfileState()
  const fragment = document.createDocumentFragment()
  if (model.kpis?.length) fragment.append(renderProfileKpis(model.kpis))
  fragment.append(renderProfilePresentationTables(model, 'Parks and schools'))
  return appendProfileCaveats(fragment, model.caveats ?? model.caveat)
}

function appendProfileCaveats(fragment, caveats) {
  const values = (Array.isArray(caveats) ? caveats : [caveats]).filter(Boolean)
  if (!values.length) return fragment
  const note = document.createElement('div')
  note.className = 'profile-caveat'
  for (const caveat of values) {
    const line = document.createElement('p')
    line.textContent = caveat
    note.append(line)
  }
  fragment.append(note)
  return fragment
}

function renderProfileKpis(metrics) {
  const grid = document.createElement('dl')
  grid.className = 'profile-kpi-grid'
  for (const metric of metrics) {
    const card = document.createElement('div')
    card.className = 'profile-kpi-card'
    const label = document.createElement('dt')
    label.textContent = metric.label
    const valueWrap = document.createElement('dd')
    const value = document.createElement('strong')
    value.textContent = metric.value == null ? 'Unavailable' : metric.displayValue
    const unit = document.createElement('small')
    unit.textContent = metric.unit ?? ''
    valueWrap.append(value, unit)
    card.append(label, valueWrap)
    grid.append(card)
  }
  return grid
}

function renderCategoricalAreaChart(chart) {
  const figure = document.createElement('figure')
  figure.className = 'profile-column-chart profile-categorical-area-chart'
  const chartId = `profile-chart-${++profileChartSequence}`
  const caption = document.createElement('figcaption')
  const title = document.createElement('strong')
  title.id = `${chartId}-title`
  title.textContent = chart.title
  const subtitle = document.createElement('span')
  subtitle.textContent = `${chart.xAxisLabel} · ${chart.yAxisLabel}`
  caption.append(title, subtitle)
  const categories = chart.categories ?? []
  const maximum = Math.max(1, ...categories.map(({ value }) => Number(value) || 0))
  const columns = document.createElement('div')
  columns.className = 'profile-chart-columns'
  columns.style.gridTemplateColumns = `repeat(${categories.length}, minmax(0, 1fr))`
  for (const category of categories) {
    const column = document.createElement('div')
    column.className = 'profile-chart-column'
    const value = document.createElement('b')
    value.textContent = category.displayValue
    const mark = document.createElement('i')
    mark.setAttribute('aria-hidden', 'true')
    mark.style.setProperty('--column-height', `${category.value == null ? 0 : Math.max(1, Number(category.value) / maximum * 100)}%`)
    const label = document.createElement('span')
    label.textContent = category.label
    column.append(value, mark, label)
    columns.append(column)
  }
  const data = document.createElement('ul')
  data.id = `${chartId}-data`
  data.className = 'profile-chart-data'
  for (const category of categories) {
    const item = document.createElement('li')
    item.textContent = `${category.label}: ${category.displayValue} ${chart.unit}`
    data.append(item)
  }
  figure.setAttribute('aria-labelledby', title.id)
  figure.setAttribute('aria-describedby', data.id)
  figure.append(caption, columns, data)
  return figure
}

function renderCategoricalCountChart(chart) {
  const { type: _ignoredType, categories = [], ...columnChart } = chart
  return renderProfileColumnChart({
    ...columnChart,
    categorical: true,
    bins: categories.map((category) => ({ label: category.label, count: category.count, percentage: category.percentage })),
  })
}

function renderProfileColumnChart(chart) {
  if (chart.type === 'categorical-area') return renderCategoricalAreaChart(chart)
  if (chart.type === 'categorical-counts') return renderCategoricalCountChart(chart)
  const figure = document.createElement('figure')
  figure.className = 'profile-column-chart'
  const chartId = `profile-chart-${++profileChartSequence}`
  const caption = document.createElement('figcaption')
  const title = document.createElement('strong')
  title.id = `${chartId}-title`
  title.textContent = chart.title
  const subtitle = document.createElement('span')
  const totalCount = Number(chart.totalCount ?? chart.bins.reduce((sum, bin) => sum + Number(bin.count || 0), 0))
  subtitle.textContent = `${chart.categorical ? 'Categorical class counts' : chart.key === 'footprintAreaM2' ? `Buildings by ${chart.unit}` : chart.key === 'vegetationThreshold' ? 'Valid-pixel composition' : `Valid pixels by ${chart.unit || 'class'}`} · n=${totalCount.toLocaleString()}`
  caption.append(title, subtitle)
  const columns = document.createElement('div')
  columns.className = 'profile-chart-columns'
  columns.classList.toggle('profile-chart-columns-dense', chart.bins.length > 8)
  if (chart.bins.length <= 8) columns.style.gridTemplateColumns = `repeat(${chart.bins.length}, minmax(0, 1fr))`
  const maximum = Math.max(1, ...chart.bins.map(({ count }) => Number(count) || 0))
  for (const bin of chart.bins) {
    const column = document.createElement('div')
    column.className = 'profile-chart-column'
    const count = document.createElement('b')
    count.textContent = `${Number(bin.count).toLocaleString()}\n${Number(bin.percentage ?? 0).toLocaleString(undefined, { maximumFractionDigits: 1 })}%`
    const mark = document.createElement('i')
    mark.setAttribute('aria-hidden', 'true')
    mark.style.setProperty('--column-height', `${Math.max(1, Number(bin.count) / maximum * 100)}%`)
    const label = document.createElement('span')
    label.textContent = bin.label
    column.append(count, mark, label)
    columns.append(column)
  }
  const data = document.createElement('ul')
  data.id = `${chartId}-data`
  data.className = 'profile-chart-data'
  for (const bin of chart.bins) {
    const item = document.createElement('li')
    item.textContent = `${bin.label}: ${Number(bin.count).toLocaleString()} (${Number(bin.percentage ?? 0).toLocaleString(undefined, { maximumFractionDigits: 1 })}%)`
    data.append(item)
  }
  figure.setAttribute('aria-labelledby', title.id)
  figure.setAttribute('aria-describedby', data.id)
  figure.append(caption, columns, data)
  return figure
}

function renderVegetationThresholdChart(chart) {
  const total = chart.columns.reduce((sum, column) => sum + Number(column.count || 0), 0)
  return renderProfileColumnChart({
    key: 'vegetationThreshold',
    title: `Vegetation threshold (${chart.thresholdLabel} NDVI)`,
    unit: 'valid pixels',
    totalCount: total,
    bins: chart.columns.map((column) => ({
      ...column,
      percentage: total ? column.count / total * 100 : 0,
      label: column.label,
    })),
  })
}

function renderProfileDetailTable(rows) {
  const table = document.createElement('table')
  table.className = 'profile-detail-table'
  const caption = document.createElement('caption')
  caption.textContent = 'Building-form summary statistics'
  const head = document.createElement('thead')
  const headerRow = document.createElement('tr')
  for (const label of ['Building form', 'Mean', 'Median', 'Min–max']) {
    const heading = document.createElement('th')
    heading.scope = 'col'
    heading.textContent = label
    headerRow.append(heading)
  }
  head.append(headerRow)
  const body = document.createElement('tbody')
  for (const row of rows) {
    const tr = document.createElement('tr')
    const values = [`${row.label} (${row.unit})`, formatProfileValue(row.mean), formatProfileValue(row.median), `${formatProfileValue(row.min)}–${formatProfileValue(row.max)}`]
    values.forEach((value, index) => {
      const cell = document.createElement(index === 0 ? 'th' : 'td')
      if (index === 0) cell.scope = 'row'
      cell.textContent = value
      tr.append(cell)
    })
    body.append(tr)
  }
  table.append(caption, head, body)
  return table
}

function renderProfileCategoricalDetailTable(rows) {
  const table = document.createElement('table')
  table.className = 'profile-detail-table'
  const caption = document.createElement('caption')
  caption.textContent = 'Categorical building-form distribution'
  const head = document.createElement('thead')
  const headerRow = document.createElement('tr')
  for (const label of ['Attribute', 'Dominant class', 'Valid coverage']) {
    const heading = document.createElement('th')
    heading.scope = 'col'
    heading.textContent = label
    headerRow.append(heading)
  }
  head.append(headerRow)
  const body = document.createElement('tbody')
  for (const row of rows) {
    const tr = document.createElement('tr')
    const values = [row.label, row.displayValue ?? 'Unavailable', row.coverageLabel ?? 'coverage unavailable']
    values.forEach((value, index) => {
      const cell = document.createElement(index === 0 ? 'th' : 'td')
      if (index === 0) cell.scope = 'row'
      cell.textContent = value
      tr.append(cell)
    })
    body.append(tr)
  }
  table.append(caption, head, body)
  return table
}

function renderProfileValidity(metrics) {
  const list = document.createElement('div')
  list.className = 'profile-validity-list'
  for (const metric of metrics) {
    const row = document.createElement('p')
    row.textContent = `${metric.label}: ${metric.coverageLabel} · ${metric.evidenceLabel}`
    list.append(row)
  }
  return list
}

function renderProfileData(data, missingLabel = 'No data') {
  const fragment = document.createDocumentFragment()
  if (data == null) return fragment
  const grid = document.createElement('div')
  grid.className = 'profile-metric-grid'
  const addMetric = (key, value, prefix = '') => {
    if (key === 'charts' || key === 'histogram' || key === 'distribution') return
    const labelKey = prefix ? `${prefix} / ${key}` : key
    if (value && typeof value === 'object' && value.status == null && value.availability == null && value.mean == null && value.value == null && value.count == null && value.weightedMean == null && !Array.isArray(value)) {
      for (const [childKey, childValue] of Object.entries(value)) addMetric(childKey, childValue, labelKey)
      return
    }
    const card = document.createElement('div')
    card.className = 'profile-metric-card'
    const label = document.createElement('span')
    label.textContent = humanizeProfileKey(labelKey)
    const valueNode = document.createElement('strong')
    if (value && typeof value === 'object') valueNode.textContent = value.status === 'unavailable' ? 'Unavailable' : formatProfileValue(value.mean ?? value.value ?? value.count ?? value.weightedMean ?? (Array.isArray(value) ? value.length : null), missingLabel)
    else valueNode.textContent = formatProfileValue(value, missingLabel)
    card.append(label, valueNode)
    if (value?.availability) {
      const availability = document.createElement('small')
      availability.textContent = `${availabilityValue(value.availability)} available`
      card.append(availability)
    }
    grid.append(card)
    if (value?.histogram || value?.distribution) fragment.append(renderProfileChart(buildChartModel({ title: humanizeProfileKey(labelKey), method: value.histogram?.method ?? 'Fixed bins', bins: histogramBins(value.histogram ?? value.distribution) })))
  }
  for (const [key, value] of Object.entries(data)) addMetric(key, value)
  if (grid.childElementCount) fragment.prepend(grid)
  return fragment
}
function availabilityValue(value) { return `${value.available ?? 0}/${value.denominator ?? 0}` }
function histogramBins(histogram) {
  const bins = histogram?.bins ?? []
  const counts = histogram?.counts ?? []
  return counts.map((value, index) => ({ label: `${bins[index]}–${bins[index + 1]}`, value }))
}
const PROFILE_METRIC_LABELS = {
  buildingCount: 'Buildings',
  totalLocationCount: 'Building locations',
  buildingFootprintCoveragePct: 'Building-footprint coverage (%)',
  intersectionDensityPerKm2: 'Intersection density (per km²)',
  vegetationFractionMean: 'Vegetation fraction (mean)',
  publicTransportStops: 'Public-transport stops',
  directlyServingRoutes: 'Directly serving routes',
}
function humanizeProfileKey(value) { return PROFILE_METRIC_LABELS[value] ?? String(value).replace(/([a-z])([A-Z])/g, '$1 $2').replace(/[_-]+/g, ' ').replace(/^./, (char) => char.toUpperCase()) }
function formatProfileValue(value, missingLabel = 'No data') { return value == null || value === '' ? missingLabel : typeof value === 'number' ? Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 }) : String(value) }

function renderProfileChart(chart) {
  const wrapper = document.createElement('div')
  wrapper.className = 'profile-chart'
  const title = document.createElement('strong')
  title.textContent = chart.title
  const subtitle = document.createElement('small')
  subtitle.textContent = chart.subtitle
  wrapper.append(title, subtitle)
  const max = Math.max(1, ...chart.bins.map((bin) => bin.value))
  for (const bin of chart.bins) {
    const row = document.createElement('div')
    row.className = 'profile-chart-row'
    const label = document.createElement('span')
    label.textContent = bin.label
    const bar = document.createElement('i')
    bar.style.width = `${(bin.value / max) * 100}%`
    bar.setAttribute('aria-label', `${bin.label}: ${bin.value}`)
    row.append(label, bar)
    wrapper.append(row)
  }
  return wrapper
}

function clearProfile() {
  profileRequestId += 1
  profilePreviewScheduler?.cancel()
  profileState = updateProfileState(profileState, { type: 'clear' })
  map?.getSource('local-profile-circle')?.setData({ type: 'FeatureCollection', features: [] })
  elements.profileDashboardSections.replaceChildren()
  if (inspectorMode === 'profile') closeInspector()
  renderProfileStatus()
}

function bindInterface() {
  elements.buildingToggle.addEventListener('click', () => {
    const visible = elements.buildingToggle.getAttribute('aria-checked') !== 'true'
    elements.buildingToggle.setAttribute('aria-checked', visible ? 'true' : 'false')
    for (const layerId of [BUILDING_FILL, BUILDING_OUTLINE]) {
      if (map?.getLayer(layerId)) map.setLayoutProperty(layerId, 'visibility', visible ? 'visible' : 'none')
    }
  })
  elements.basemapToggle.addEventListener('click', () => {
    const visible = elements.basemapToggle.getAttribute('aria-checked') !== 'true'
    elements.basemapToggle.setAttribute('aria-checked', visible ? 'true' : 'false')
    setBaseLayerVisibility()
  })
  elements.roadsToggle.addEventListener('click', () => {
    const visible = elements.roadsToggle.getAttribute('aria-checked') !== 'true'
    elements.roadsToggle.setAttribute('aria-checked', visible ? 'true' : 'false')
    setBaseLayerVisibility()
  })

  elements.opacityControl.addEventListener('input', () => {
    const opacity = Number(elements.opacityControl.value) / 100
    elements.opacityValue.value = `${Math.round(opacity * 100)}%`
    if (map?.getLayer(BUILDING_FILL)) map.setPaintProperty(BUILDING_FILL, 'fill-opacity', opacity)
  })
  elements.catchmentOpacityControl.addEventListener('input', updateCatchmentOpacity)
  elements.routeStopOpacityControl.addEventListener('input', updateRouteStopOpacity)

  elements.resetView.addEventListener('click', () => fitStudyBounds(true))
  elements.legendInfoButton.addEventListener('click', () => {
    const open = elements.legendHelp.hidden
    elements.legendHelp.hidden = !open
    elements.legendInfoButton.setAttribute('aria-expanded', open ? 'true' : 'false')
  })
  elements.closeInspector.addEventListener('click', closeInspector)
  elements.menuToggle.addEventListener('click', toggleSidebar)
  elements.sidebarScrim.addEventListener('click', () => toggleSidebar(false))
  elements.sidebarCollapse.addEventListener('click', () => toggleSidebar(false))
  elements.methodButton.addEventListener('click', () => elements.methodDialog.showModal())
  elements.closeMethod.addEventListener('click', () => elements.methodDialog.close())
  elements.methodDone.addEventListener('click', () => elements.methodDialog.close())
  elements.methodDialog.addEventListener('click', (event) => {
    if (event.target === elements.methodDialog) elements.methodDialog.close()
  })
  elements.spaceSyntaxSelect.addEventListener('change', () => updateSpaceSyntax(elements.spaceSyntaxSelect.value))
  elements.profileRadius.addEventListener('change', () => {
    if (profileState.center) updateProfileCircle(profileState.center, Number(elements.profileRadius.value), true)
  })
  elements.profilePlace.addEventListener('click', () => {
    profileState = updateProfileState(profileState, { type: 'preview', center: map?.getCenter().toArray() ?? metadata.centre_wgs84, radiusM: Number(elements.profileRadius.value) })
    elements.profileStatus.textContent = 'Click the map to place profile'
    map?.getCanvas().classList.add('profile-placement-mode')
  })
  elements.profileClear.addEventListener('click', clearProfile)
  elements.profilePrint.addEventListener('click', () => {
    const availability = openPrintProfilePreview({ profileState, mount: document.body, print: () => window.print() })
    if (!availability.available) elements.profileStatus.textContent = availability.reason
  })
  profilePreviewScheduler = createPreviewScheduler((payload) => requestProfile(payload, false))
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && window.innerWidth <= 720 && elements.sidebar.classList.contains('open')) toggleSidebar(false)
  })
  window.addEventListener('resize', () => {
    updateLegend()
    if (window.innerWidth > 720) {
      elements.sidebar.classList.remove('open')
      elements.sidebar.removeAttribute('aria-hidden')
      elements.sidebarScrim.classList.remove('open')
      elements.menuToggle.setAttribute('aria-expanded', 'false')
    }
  })
}

function renderSpaceSyntaxControl() {
  elements.spaceSyntaxSelect.replaceChildren()
  for (const [value, label] of SPACE_SYNTAX_FIELDS) {
    const option = document.createElement('option')
    option.value = value
    option.textContent = label
    elements.spaceSyntaxSelect.append(option)
  }
  const note = elements.spaceSyntaxSelect.closest('.overlay-select-row')?.querySelector('small')
  if (note) {
    note.textContent = spaceSyntaxSidebarDescription('off')
  }
}

function updateSpaceSyntax(property) {
  if (property !== 'off') registerSpaceSyntaxLayers()
  for (const [layerId, visibility] of spaceSyntaxVisibilityUpdates(property)) {
    if (map?.getLayer(layerId)) map.setLayoutProperty(layerId, 'visibility', visibility)
  }
  if (property !== 'off' && map?.getLayer('space-syntax-line')) map.setPaintProperty('space-syntax-line', 'line-color', spaceSyntaxPaint(property, metadata).color)
  if (property === 'betweenness' && map?.getLayer('space-syntax-point')) map.setPaintProperty('space-syntax-point', 'circle-color', spaceSyntaxPaint(property, metadata).color)
  const note = elements.spaceSyntaxSelect.closest('.overlay-select-row')?.querySelector('small')
  if (note) note.textContent = spaceSyntaxSidebarDescription('off')
  updateLegend()
}

function registerSpaceSyntaxLayers() {
  if (!map || map.getSource('planx-spaceSyntax')) return
  map.addSource('planx-spaceSyntax', PLANX_SOURCES.spaceSyntax)
  map.addSource('planx-spaceSyntaxPoints', PLANX_SOURCES.spaceSyntaxPoints)
  map.addLayer(SPACE_SYNTAX_LAYER)
  map.addLayer(SPACE_SYNTAX_POINT_LAYER)
}

function registerPlanxOverlays(keys) {
  const missing = new Set([...keys].filter((key) => !registeredPlanxOverlays.has(key)))
  if (!missing.size) return
  const { sources, layers } = overlayRegistration(PLANX_OVERLAYS, PLANX_SOURCES, missing)
  const firstSymbolLayer = map.getStyle().layers?.find((layer) => layer.type === 'symbol')?.id
  for (const [key, source] of sources) {
    if (!map.getSource(`planx-${key}`)) map.addSource(`planx-${key}`, source)
  }
  for (const layer of layers) {
    if (!map.getLayer(layer.id)) map.addLayer(layer, firstSymbolLayer)
  }
  for (const key of missing) registeredPlanxOverlays.add(key)
  const firstRoadLayer = map.getStyle().layers?.find(isRoadLayer)?.id
  reorderPlanxLayers(map, PLANX_OVERLAYS, registeredPlanxOverlays, firstRoadLayer)
  if (missing.has('transitIsochrones')) bindTransitIsochroneInteractions()
  if (missing.has('floodRiskZones')) bindFloodRiskInteractions()
  if (missing.has('tpsProvisional')) bindTpsInteractions()
  applyPlanxClassifications(map, metadata)
}

function bindTpsInteractions() {
  if (tpsInteractionsBound) return
  tpsInteractionsBound = true
  map.on('mouseenter', 'tps-provisional-fill', () => {
    if (activePlanxOverlays.has('tpsProvisional')) map.getCanvas().style.cursor = 'pointer'
  })
  map.on('mouseleave', 'tps-provisional-fill', () => {
    map.getCanvas().style.cursor = ''
  })
  map.on('click', 'tps-provisional-fill', async (event) => {
    if (!activePlanxOverlays.has('tpsProvisional')) return
    const feature = event.features?.[0]
    if (!feature) return
    map.getCanvas().style.cursor = 'progress'
    try {
      const selection = resolveTpsSelection(feature, await loadExactTpsFeatureIndex())
      if (!activePlanxOverlays.has('tpsProvisional')) return
      map.getCanvas().classList.remove('profile-placement-mode')
      localAreaProfileService.abort()
      profileRequestId += 1
      profileState = updateProfileState(profileState, { type: 'select', selection })
      map.getSource('local-profile-circle')?.setData({ type: 'FeatureCollection', features: [] })
      renderProfileInspectorState()
      renderProfileStatus()
      requestProfile({ selection }, true)
    } catch (error) {
      console.error('TPS profile selection failed', error)
      elements.profileStatus.textContent = `TPS profile unavailable: ${error.message}`
    } finally {
      map.getCanvas().style.cursor = activePlanxOverlays.has('tpsProvisional') ? 'pointer' : ''
    }
  })
}

function loadExactTpsFeatureIndex() {
  if (!exactTpsFeatureIndexPromise) exactTpsFeatureIndexPromise = fetchJson('./data/tps-provisional.geojson').then(buildTpsFeatureIndex)
  return exactTpsFeatureIndexPromise
}

function bindFloodRiskInteractions() {
  if (floodRiskInteractionsBound) return
  floodRiskInteractionsBound = true
  map.on('mouseenter', 'flood-risk-zones-fill', () => {
    if (activePlanxOverlays.has('floodRiskZones')) map.getCanvas().style.cursor = 'pointer'
  })
  map.on('mouseleave', 'flood-risk-zones-fill', () => {
    map.getCanvas().style.cursor = ''
  })
  map.on('click', 'flood-risk-zones-fill', (event) => {
    if (!activePlanxOverlays.has('floodRiskZones')) return
    const feature = event.features?.[0]
    if (!feature) return
    const details = buildFloodRiskDetails(feature.properties)
    showInspectorMode('floodRisk')
    elements.inspectorEyebrow.textContent = 'URBAN FLOOD-RISK ZONE'
    elements.buildingId.textContent = details.title
    elements.selectedMetricLabel.textContent = 'Risk class'
    elements.selectedMetricValue.textContent = feature.properties?.uf_risk || 'Unavailable'
    elements.buildingDetails.replaceChildren(detailSection('Source attributes', details.rows))
    elements.selectedMethod.textContent = 'Source polygons and risk classes are shown unchanged.'
    elements.selectedSource.textContent = 'Source: VEDAS / ISRO · provisional urban flood-risk zones'
  })
}

function loadTransitIsochroneModel() {
  if (!transitIsochroneModelPromise) {
    transitIsochroneModelPromise = fetchJson('./data/transit-isochrone-model.json').then((model) => {
      transitStopIndex = new globalThis.Map(model.stops.map((stop, index) => [String(stop.id), index]))
      return model
    })
  }
  return transitIsochroneModelPromise
}

function bindTransitIsochroneInteractions() {
  if (transitIsochroneInteractionsBound) return
  transitIsochroneInteractionsBound = true
  map.on('mouseenter', 'transit-isochrone-origin-circle', () => {
    if (activePlanxOverlays.has('transitIsochrones')) map.getCanvas().style.cursor = 'pointer'
  })
  map.on('mouseleave', 'transit-isochrone-origin-circle', () => {
    map.getCanvas().style.cursor = ''
  })
  map.on('click', 'transit-isochrone-origin-circle', async (event) => {
    if (!activePlanxOverlays.has('transitIsochrones')) return
    const feature = event.features?.[0]
    const stopId = String(feature?.properties?.stop_id ?? '')
    if (!stopId) return
    const request = ++transitSelectionRequest
    map.getCanvas().style.cursor = 'progress'
    try {
      const model = await loadTransitIsochroneModel()
      if (request !== transitSelectionRequest || !activePlanxOverlays.has('transitIsochrones')) return
      const originIndex = transitStopIndex.get(stopId)
      if (originIndex === undefined) throw new Error(`Stop ${stopId} is absent from the transit isochrone model`)
      const catchment = buildRouteReachCatchment(model, originIndex)
      map.getSource('planx-transitIsochrone15')?.setData(catchment.minutes15)
      map.getSource('planx-transitIsochroneDirect15')?.setData(catchment.directMinutes15)
      map.getSource('planx-transitIsochroneRouteStops')?.setData(catchment.routeStops)
      map.setFilter('transit-isochrone-selected-circle', ['==', ['get', 'stop_id'], stopId])
      const stopName = feature.properties?.stop_name || model.stops[originIndex].name || stopId
      const details = buildStopDetails(model, originIndex, catchment)
      transitSelection = { model, catchment, details, selectedRouteIds: new Set(details.routes.map((route) => route.id)) }
      renderTransitInspector()
      updateTransitRouteHighlight()
      elements.planxActiveSummary.textContent = `${planxSummaryLabel(PLANX_OVERLAYS, activePlanxOverlays, metadata)} · Origin: ${stopName} · ${catchment.seedStopIndexes.length} stop(s) within 5 minutes · ${catchment.routeIndexes.length} route(s) · ${catchment.routeStopIndexes.length} route stop(s)`
    } catch (error) {
      console.error('Transit isochrone calculation failed', error)
      elements.planxActiveSummary.textContent = `Transit isochrone calculation failed: ${error.message}`
    } finally {
      if (request === transitSelectionRequest) map.getCanvas().style.cursor = 'pointer'
    }
  })
}

function renderPlanxControls() {
  elements.planxOverlayControls.replaceChildren()
  elements.featuredTransitControl.replaceChildren()
  elements.tpsProvisionalControl.replaceChildren()
  const groupDefinitions = [
    ['current', 'Analytical layers'],
    ['context', 'Context layers'],
    ['experimental', 'Experimental / not validated'],
  ]
  const groupBodies = new globalThis.Map()
  for (const [groupKey, label] of groupDefinitions) {
    const details = document.createElement('details')
    details.className = 'overlay-disclosure'
    details.open = groupKey === 'current'
    const summary = document.createElement('summary')
    summary.textContent = label
    const body = document.createElement('div')
    body.className = 'overlay-disclosure-body'
    details.append(summary, body)
    elements.planxOverlayControls.append(details)
    groupBodies.set(groupKey, body)
  }
  const overlays = orderedPlanxOverlays(PLANX_OVERLAYS)
  const currentCategory = new globalThis.Map()
  const currentSubheading = new globalThis.Map()
  for (const overlay of overlays) {
    const overlayContextKey = resolveItemContextKey(metadata, overlay, 'overlay')
    const groupKey = overlayDisclosureGroup(overlayContextKey)
    const isTpsControl = overlay.key === 'tpsProvisional'
    const body = overlay.featured ? elements.featuredTransitControl : isTpsControl ? elements.tpsProvisionalControl : groupBodies.get(groupKey)
    if (!overlay.featured && !isTpsControl) {
      const category = overlayControlCategory(overlay)
      if (currentCategory.get(groupKey) !== category) {
        const heading = document.createElement('h3')
        heading.className = 'overlay-subheading'
        heading.textContent = category
        body.append(heading)
        currentCategory.set(groupKey, category)
        currentSubheading.delete(groupKey)
      }
      const subheading = overlayControlSubheading(overlay)
      if (subheading && currentSubheading.get(groupKey) !== subheading) {
        const heading = document.createElement('h4')
        heading.className = 'overlay-nested-subheading'
        heading.textContent = subheading
        body.append(heading)
        currentSubheading.set(groupKey, subheading)
      }
    }
    const badge = document.createElement('span')
    badge.className = 'overlay-status-badge'
    badge.textContent = overlayStatusLabel(overlayContextKey)
    const badgeHtml = badge.outerHTML
    if (overlay.key.startsWith('poi-')) {
      const label = document.createElement('label')
      label.className = 'poi-checkbox-row'
      const input = document.createElement('input')
      input.type = 'checkbox'
      input.dataset.overlay = overlay.key
      input.checked = false
      input.addEventListener('change', () => {
        if (input.checked) activePlanxOverlays.add(overlay.key)
        else activePlanxOverlays.delete(overlay.key)
        updatePlanxVisibility()
      })
      const copy = document.createElement('span')
      copy.innerHTML = `<strong>${escapeHtml(overlay.label)} ${badgeHtml}</strong><small>${escapeHtml(overlaySidebarDescription(overlay))}</small>`
      label.append(input, copy)
      body.append(label)
      continue
    }
    const button = document.createElement('button')
    button.className = 'planx-overlay-button'
    button.type = 'button'
    button.dataset.overlay = overlay.key
    button.setAttribute('aria-pressed', 'false')
    button.innerHTML = `<span><strong>${escapeHtml(overlay.label)} ${badgeHtml}</strong><small>${escapeHtml(overlaySidebarDescription(overlay))}</small></span><i aria-hidden="true"></i>`
    button.addEventListener('click', () => {
      const next = activateExclusiveOverlay(activePlanxOverlays, PLANX_OVERLAYS, overlay.key)
      activePlanxOverlays.clear()
      for (const key of next) activePlanxOverlays.add(key)
      for (const control of elements.sidebar.querySelectorAll('.planx-overlay-button')) {
        const active = activePlanxOverlays.has(control.dataset.overlay)
        control.classList.toggle('active', active)
        control.setAttribute('aria-pressed', active ? 'true' : 'false')
      }
      updatePlanxVisibility()
    })
    body.append(button)
  }
}

function overlayDisclosureGroup(contextKey) {
  if (['unverified-height', 'supplied-external', 'supplied-unverified-experimental', 'scope-unverified'].includes(contextKey)) return 'experimental'
  if (['contextual-gtfs', 'contextual-osm', 'contextual-vedas'].includes(contextKey)) return 'context'
  return 'current'
}

function overlayStatusLabel(contextKey) {
  return ({
    'full-study-current': 'Current',
    'current-study-bounded': 'Bounded',
    'current-study-sampled': 'Sampled model',
    'current-study-proxy': 'Screening proxy',
    'modelled-building-height': 'Modelled raster',
    'contextual-gtfs': 'GTFS context',
    'contextual-osm': 'OSM context',
    'contextual-vedas': 'VEDAS context',
    'supplied-external': 'Not rerun',
    'supplied-unverified-experimental': 'Unverified / experimental',
    'unverified-height': 'Not validated',
  })[contextKey] ?? 'Scope unverified'
}

function updatePlanxVisibility() {
  if (map) registerPlanxOverlays(activePlanxOverlays)
  for (const [layerId, visibility] of planxVisibilityUpdates(PLANX_OVERLAYS, activePlanxOverlays)) {
    if (map?.getLayer(layerId)) {
      map.setLayoutProperty(layerId, 'visibility', visibility)
    }
  }
  elements.planxActiveSummary.hidden = activePlanxOverlays.size === 0
  elements.planxActiveSummary.textContent = activePlanxOverlays.size
    ? planxSummaryLabel(PLANX_OVERLAYS, activePlanxOverlays, metadata)
    : ''
  if (!activePlanxOverlays.has('transitIsochrones')) clearTransitSelection({ closePanel: true })
  if (!activePlanxOverlays.has('floodRiskZones') && inspectorMode === 'floodRisk') closeInspector()
  if (!activePlanxOverlays.has('tpsProvisional') && profileState.selection?.type === 'tps') {
    localAreaProfileService.abort()
    profileRequestId += 1
    profileState = updateProfileState(profileState, { type: 'clear' })
    if (inspectorMode === 'profile') closeInspector()
    renderProfileStatus()
  }
  updateCatchmentOpacity()
  updateRouteStopOpacity()
  updateLegend()
}

function updateCatchmentOpacity() {
  const opacity = Number(elements.catchmentOpacityControl.value) / 100
  elements.catchmentOpacityValue.value = `${Math.round(opacity * 100)}%`
  for (const layerId of ['transit-isochrone-15-fill', 'transit-isochrone-direct-15-fill']) {
    if (map?.getLayer(layerId)) map.setPaintProperty(layerId, 'fill-opacity', opacity)
  }
}

function updateRouteStopOpacity() {
  const opacity = Number(elements.routeStopOpacityControl.value) / 100
  elements.routeStopOpacityValue.value = `${Math.round(opacity * 100)}%`
  if (map?.getLayer('transit-isochrone-route-stops-circle')) {
    map.setPaintProperty('transit-isochrone-route-stops-circle', 'circle-stroke-opacity', ['case', ['get', 'seed_stop'], 1, opacity])
  }
}

function setBaseLayerVisibility() {
  const backgroundVisible = elements.basemapToggle.getAttribute('aria-checked') === 'true'
  const roadsVisible = elements.roadsToggle.getAttribute('aria-checked') === 'true'
  for (const [layerId, visibility] of baseLayerVisibilityUpdates(basemapLayerVisibility, { backgroundVisible, roadsVisible })) {
    if (map?.getLayer(layerId)) map.setLayoutProperty(layerId, 'visibility', visibility)
  }
}

function renderIndicatorControls() {
  elements.indicatorGroups.replaceChildren()
  const control = document.createElement('div')
  control.className = 'planx-overlay-button building-display-control'
  const copy = document.createElement('span')
  const title = document.createElement('strong')
  title.textContent = 'Buildings'
  const description = document.createElement('small')
  description.textContent = 'Fixed neutral display · individual polygons are not selectable.'
  const marker = document.createElement('i')
  marker.setAttribute('aria-hidden', 'true')
  copy.append(title, description)
  control.append(copy, marker)
  elements.indicatorGroups.append(control)
}

function updateLegend() {
  const state = buildLegendState({ activeIndicatorKey: null, activePlanxOverlays, spaceSyntaxKey: elements.spaceSyntaxSelect.value, metadata, planxOverlays: PLANX_OVERLAYS })
  renderLegend(elements.legend, state)
  renderLegendHelp(elements.legendHelp, state)
}


function detailSection(title, rows) {
  const section = document.createElement('section')
  section.className = 'detail-section'
  const heading = document.createElement('h3')
  heading.textContent = title
  section.append(heading)
  for (const [label, value] of rows) {
    const row = document.createElement('div')
    row.className = 'detail-row'
    const labelNode = document.createElement('span')
    labelNode.textContent = label
    const valueNode = document.createElement('span')
    valueNode.textContent = value
    row.append(labelNode, valueNode)
    section.append(row)
  }
  return section
}

function renderTransitInspector() {
  const { details } = transitSelection
  showInspectorMode('transit')
  elements.inspectorEyebrow.textContent = 'SELECTED BUS STOP'
  elements.buildingId.textContent = details.stopName
  elements.selectedMetricLabel.textContent = 'Direct routes serving stop'
  elements.selectedMetricValue.textContent = String(details.directRouteCount)
  elements.buildingDetails.replaceChildren()
  elements.transitDetails.replaceChildren()
  elements.transitDetails.append(
    detailSection('Walking catchments', [
      ['Direct stop walk (15 min)', formatAreaM2(details.directWalkAreaM2)],
      ['Route-reach walk (15 min)', formatAreaM2(details.routeReachAreaM2)],
    ]),
    transitRouteControls(),
    transitGraph(),
  )
  elements.selectedMethod.textContent = 'Blue shows the route-reach catchment. Green shows the selected stop’s direct 15-minute walk, using the same 250 m cells.'
  elements.selectedSource.textContent = 'Source: prepared GTFS service and street-network model'
}

function transitRouteControls() {
  const section = document.createElement('section')
  section.className = 'detail-section transit-route-section'
  const heading = document.createElement('h3')
  heading.textContent = `Routes (${transitSelection.details.directRouteCount})`
  section.append(heading)
  const actions = document.createElement('div')
  actions.className = 'transit-route-actions'
  const reset = document.createElement('button')
  reset.type = 'button'
  reset.textContent = transitSelection.details.routes.length > 8 ? 'Total' : 'All routes'
  reset.addEventListener('click', () => {
    transitSelection.selectedRouteIds = new Set(transitSelection.details.routes.map(({ id }) => id))
    renderTransitInspector()
    updateTransitRouteHighlight()
  })
  actions.append(reset)
  section.append(actions)
  for (const route of transitSelection.details.routes) {
    const button = document.createElement('button')
    button.type = 'button'
    button.className = 'transit-route-button'
    button.dataset.routeId = route.id
    button.classList.toggle('active', transitSelection.selectedRouteIds.has(route.id))
    button.addEventListener('mouseenter', () => emphasizeTransitRoute(route.id, true))
    button.addEventListener('mouseleave', () => emphasizeTransitRoute(route.id, false))
    button.addEventListener('click', () => {
      transitSelection.selectedRouteIds = new Set([route.id])
      renderTransitInspector()
      updateTransitRouteHighlight()
    })
    const swatch = document.createElement('i')
    swatch.className = 'route-swatch'
    swatch.style.backgroundColor = routeColor(route.id)
    const copy = document.createElement('span')
    copy.textContent = `${route.shortName}${route.longName ? ` · ${route.longName}` : ''} · ${route.averageHeadwayMinutes == null ? 'headway unavailable' : `${route.averageHeadwayMinutes} min average headway`}${route.hasGeometry ? '' : ' · route geometry unavailable'}`
    button.append(swatch, copy)
    section.append(button)
  }
  return section
}

function transitGraph() {
  const section = document.createElement('section')
  section.className = 'detail-section transit-graph-section'
  const heading = document.createElement('h3')
  heading.textContent = 'Scheduled service by hour'
  section.append(heading)
  const routes = transitSelection.details.routes
  const hours = transitSelection.details.serviceHours
  const series = graphSeries(routes, transitSelection.selectedRouteIds, hours.length)
  const max = Math.max(1, ...series.flatMap(({ values }) => values))
  const yTicks = graphAxisTicks(max)
  const yMax = yTicks[yTicks.length - 1]
  const xTicks = graphHourTicks(hours)
  const width = 320
  const height = 190
  const plot = { left: 48, right: 10, top: 10, bottom: 38 }
  const plotWidth = width - plot.left - plot.right
  const plotHeight = height - plot.top - plot.bottom
  const xAt = (index, count) => plot.left + (index / Math.max(1, count - 1)) * plotWidth
  const yAt = (value) => plot.top + plotHeight - (Number(value) / yMax) * plotHeight
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg')
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`)
  svg.setAttribute('role', 'img')
  svg.setAttribute('aria-label', 'Scheduled service by hour')
  const axis = (x1, y1, x2, y2) => {
    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line')
    for (const [name, value] of Object.entries({ x1, y1, x2, y2 })) line.setAttribute(name, value)
    line.setAttribute('class', 'transit-graph-axis')
    svg.append(line)
  }
  const label = (text, x, y, className, transform = null) => {
    const node = document.createElementNS('http://www.w3.org/2000/svg', 'text')
    node.textContent = text
    node.setAttribute('x', x)
    node.setAttribute('y', y)
    node.setAttribute('class', className)
    if (transform) node.setAttribute('transform', transform)
    svg.append(node)
  }
  axis(plot.left, plot.top, plot.left, plot.top + plotHeight)
  axis(plot.left, plot.top + plotHeight, width - plot.right, plot.top + plotHeight)
  for (const tick of yTicks) {
    const y = yAt(tick)
    axis(plot.left - 4, y, plot.left, y)
    label(String(tick), plot.left - 8, y + 3, 'transit-graph-tick transit-graph-y-tick')
  }
  for (const tick of xTicks) {
    const x = xAt(tick.index, hours.length)
    axis(x, plot.top + plotHeight, x, plot.top + plotHeight + 4)
    label(tick.label, x, plot.top + plotHeight + 15, 'transit-graph-tick transit-graph-x-tick')
  }
  label('Service hour', plot.left + plotWidth / 2, height - 3, 'transit-graph-axis-label transit-graph-x-label')
  label('Scheduled departures per hour', 12, plot.top + plotHeight / 2, 'transit-graph-axis-label transit-graph-y-label', `rotate(-90 12 ${plot.top + plotHeight / 2})`)
  for (const item of series) {
    const points = item.values.map((value, index) => `${xAt(index, item.values.length)},${yAt(value)}`).join(' ')
    const line = document.createElementNS('http://www.w3.org/2000/svg', 'polyline')
    line.setAttribute('points', points)
    line.setAttribute('fill', 'none')
    line.setAttribute('stroke', item.color)
    line.setAttribute('stroke-width', series.length > 1 ? '2' : '3')
    svg.append(line)
  }
  section.append(svg)
  return section
}

function updateTransitRouteHighlight() {
  if (!map || !transitSelection) return
  const ids = [...transitSelection.selectedRouteIds]
  const selectedLayers = ['gtfs-shapes-selected-line', 'transit-isochrone-selected-route-line']
  for (const layerId of selectedLayers) if (map.getLayer(layerId)) map.setFilter(layerId, selectedRouteFilter(ids))
  for (const layerId of selectedLayers) if (map.getLayer(layerId)) {
    const color = ['match', ['get', 'route_id'], ...transitSelection.details.routes.flatMap((route) => [route.id, routeColor(route.id)]), '#6f2f24']
    map.setPaintProperty(layerId, 'line-color', color)
  }
}

function emphasizeTransitRoute(routeId, active) {
  if (!map || !transitSelection) return
  for (const layerId of ['gtfs-shapes-selected-line', 'transit-isochrone-selected-route-line']) {
    if (!map.getLayer(layerId)) continue
    map.setPaintProperty(layerId, 'line-width', active ? 5 : 3)
    map.setFilter(layerId, active ? selectedRouteFilter([routeId]) : selectedRouteFilter([...transitSelection.selectedRouteIds]))
  }
}

function clearTransitSelection({ closePanel = false } = {}) {
  transitSelectionRequest += 1
  transitSelection = null
  elements.transitDetails.hidden = true
  elements.transitDetails.replaceChildren()
  if (map?.getSource('planx-transitIsochrone15')) map.getSource('planx-transitIsochrone15').setData({ type: 'FeatureCollection', features: [] })
  if (map?.getSource('planx-transitIsochroneDirect15')) map.getSource('planx-transitIsochroneDirect15').setData({ type: 'FeatureCollection', features: [] })
  if (map?.getSource('planx-transitIsochroneRouteStops')) map.getSource('planx-transitIsochroneRouteStops').setData({ type: 'FeatureCollection', features: [] })
  for (const layerId of ['gtfs-shapes-selected-line', 'transit-isochrone-selected-route-line']) if (map?.getLayer(layerId)) map.setFilter(layerId, selectedRouteFilter([]))
  if (map?.getLayer('transit-isochrone-selected-circle')) map.setFilter('transit-isochrone-selected-circle', ['==', ['get', 'stop_id'], ''])
  if (closePanel && inspectorMode === 'transit') closeInspector()
}

function closeInspector() {
  inspectorMode = null
  elements.inspector.classList.remove('open')
  elements.inspector.setAttribute('aria-hidden', 'true')
  elements.inspector.inert = true
}

function toggleSidebar(force) {
  if (window.innerWidth <= 720) {
    const open = typeof force === 'boolean' ? force : !elements.sidebar.classList.contains('open')
    elements.sidebar.classList.toggle('open', open)
    elements.sidebarScrim.classList.toggle('open', open)
    elements.menuToggle.setAttribute('aria-expanded', open ? 'true' : 'false')
    elements.sidebar.setAttribute('aria-hidden', open ? 'false' : 'true')
    if (open) elements.sidebar.focus()
    else elements.menuToggle.focus()
    return
  }
  elements.sidebar.removeAttribute('aria-hidden')
  elements.sidebarScrim.classList.remove('open')
  const expanded = typeof force === 'boolean' ? force : elements.sidebar.classList.contains('collapsed')
  elements.sidebar.classList.toggle('collapsed', !expanded)
  elements.sidebarCollapse.setAttribute('aria-expanded', expanded ? 'true' : 'false')
  elements.sidebarCollapse.setAttribute('aria-label', expanded ? 'Collapse indicator panel' : 'Expand indicator panel')
  elements.sidebarCollapse.textContent = expanded ? '‹' : '›'
  document.querySelector('.sidebar-reopen')?.setAttribute('aria-expanded', expanded ? 'true' : 'false')
}

function addSidebarReopenControl() {
  const button = document.createElement('button')
  button.type = 'button'
  button.className = 'sidebar-reopen'
  button.setAttribute('aria-controls', 'sidebar')
  button.setAttribute('aria-expanded', 'true')
  button.setAttribute('aria-label', 'Expand indicator panel')
  button.textContent = 'Layers ›'
  button.addEventListener('click', () => toggleSidebar(true))
  document.querySelector('.map-shell').prepend(button)
}

function fitStudyBounds(animated) {
  map.fitBounds(
    [[metadata.bounds_wgs84[0], metadata.bounds_wgs84[1]], [metadata.bounds_wgs84[2], metadata.bounds_wgs84[3]]],
    { padding: { top: 120, right: 60, bottom: 110, left: 60 }, duration: animated ? 700 : 0 },
  )
}

function renderStaticMetadata() {
  elements.buildingCount.textContent = `${metadata.building_count.toLocaleString()} buildings`
  elements.limitations.innerHTML = `<h3>Interpretation limits</h3><ul>${(metadata.interpretation ?? []).map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ul>`
}

function formatMinutes(value) { return formatNumber(value, 1, ' min') }
function formatPercent(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return 'No data'
  return `${(Number(value) * 100).toFixed(1)}%`
}
function formatNumber(value, decimals, suffix = '') {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return 'No data'
  return `${Number(value).toFixed(decimals)}${suffix}`
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;',
  })[character])
}

function showLoadingError(error) {
  console.error(error)
  elements.loadingPanel.innerHTML = `<strong>Could not load the scanner</strong><small>${escapeHtml(error.message)}</small>`
}

bootstrap()
