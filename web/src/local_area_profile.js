export const PROFILE_RADII = [400, 800, 1200]

export const PROFILE_SECTION_KEYS = [
  'overview',
  'buildings',
  'streetsConnectivity',
  'spaceSyntaxCentrality',
  'environment',
  'publicTransport',
  'parksEducation',
  'availability',
  'methods',
]

const EARTH_RADIUS_M = 6371008.8

function assertCenter(center) {
  if (!Array.isArray(center) || center.length !== 2 || center.some((value) => !Number.isFinite(Number(value)))) {
    throw new TypeError('center must be [longitude, latitude]')
  }
}

function assertRadius(radiusM) {
  if (!PROFILE_RADII.includes(Number(radiusM))) throw new RangeError(`radius must be one of ${PROFILE_RADII.join(', ')}`)
}

export function buildCircleFeature(center, radiusM, segments = 64) {
  assertCenter(center)
  assertRadius(radiusM)
  if (!Number.isInteger(segments) || segments < 4) throw new RangeError('segments must be an integer of at least 4')
  const [longitude, latitude] = center.map(Number)
  const angularDistance = Number(radiusM) / EARTH_RADIUS_M
  const lat1 = latitude * Math.PI / 180
  const lon1 = longitude * Math.PI / 180
  const coordinates = []
  for (let index = 0; index <= segments; index += 1) {
    const bearing = (index / segments) * 2 * Math.PI
    const lat2 = Math.asin(Math.sin(lat1) * Math.cos(angularDistance) + Math.cos(lat1) * Math.sin(angularDistance) * Math.cos(bearing))
    const lon2 = lon1 + Math.atan2(Math.sin(bearing) * Math.sin(angularDistance) * Math.cos(lat1), Math.cos(angularDistance) - Math.sin(lat1) * Math.sin(lat2))
    coordinates.push([lon2 * 180 / Math.PI, lat2 * 180 / Math.PI])
  }
  return {
    type: 'Feature',
    properties: { radiusM: Number(radiusM) },
    geometry: { type: 'Polygon', coordinates: [coordinates] },
  }
}

export function createProfileState() {
  return { center: null, radiusM: 400, selection: null, status: 'empty', result: null, requestId: 0 }
}

export function updateProfileState(state, event) {
  const current = { ...state }
  if (event.type === 'preview') {
    assertCenter(event.center)
    assertRadius(event.radiusM)
    return { ...current, center: [...event.center], radiusM: Number(event.radiusM), selection: null, result: null, status: 'preview' }
  }
  if (event.type === 'select') return { ...current, center: null, selection: event.selection, result: null, status: 'preview' }
  if (event.type === 'request') return { ...current, status: 'updating', requestId: Number(event.requestId) }
  if (event.type === 'resolved') {
    if (Number(event.requestId) !== current.requestId) return current
    return { ...current, status: 'ready', result: event.result }
  }
  if (event.type === 'clear') return { ...createProfileState(), requestId: current.requestId + 1 }
  throw new TypeError(`Unknown profile event: ${event.type}`)
}

export function buildTpsSelection(feature) {
  const geometry = feature?.geometry
  if (!geometry || !['Polygon', 'MultiPolygon'].includes(geometry.type)) throw new TypeError('TPS feature requires Polygon or MultiPolygon geometry')
  const properties = feature.properties ?? {}
  return { type: 'tps', geometry, source_id: properties.source_id, tps_name: properties.tps_name ?? null, tps_no: properties.tps_no ?? null, tps_status: properties.tps_status ?? null }
}

export function buildTpsFeatureIndex(collection) {
  return new Map((collection?.features ?? []).map((feature) => [String(feature?.properties?.source_id ?? ''), feature]).filter(([sourceId]) => sourceId))
}

export function resolveTpsSelection(renderedFeature, featureIndex) {
  const sourceId = String(renderedFeature?.properties?.source_id ?? '')
  const exactFeature = featureIndex?.get(sourceId)
  if (!exactFeature) throw new Error(`Exact TPS source geometry unavailable for ${sourceId || 'unknown feature'}`)
  return buildTpsSelection(exactFeature)
}

function selectionText(value, fallback) {
  return value === null || value === undefined || String(value).trim() === '' ? fallback : String(value)
}

export function profileSelectionPresentation(result = {}) {
  const selection = result.selection
  if (selection?.type === 'tps') {
    const name = selectionText(selection.tps_name, 'TPS name unavailable')
    const number = selectionText(selection.tps_no, 'unavailable')
    const area = Number.isFinite(Number(selection.areaM2)) ? `${Number(selection.areaM2).toLocaleString('en-US', { maximumFractionDigits: 2 })} m²` : 'Unavailable'
    return { eyebrow: 'TOWN-PLANNING SCHEME PROFILE', title: number === 'unavailable' ? 'TPS number unavailable' : `TPS number ${number}`, metricLabel: 'Selected TPS', metricValue: `${name}\nArea ${area}` }
  }
  const center = result.center
  const radiusM = result.radiusM
  let metricValue = 'No point selected'
  if (Array.isArray(center) && center.length === 2) {
    const [longitude, latitude] = center
    metricValue = `X / Longitude  ${Math.abs(longitude).toFixed(5)}° ${longitude >= 0 ? 'E' : 'W'}\nY / Latitude    ${Math.abs(latitude).toFixed(5)}° ${latitude >= 0 ? 'N' : 'S'}`
  }
  return { eyebrow: 'LOCAL AREA PROFILE', title: radiusM == null ? 'Local Area Profile' : `${radiusM} m profile`, metricLabel: 'Selected centre · WGS84', metricValue }
}

export function normalizeProfileResult(result = {}) {
  const normalized = {}
  for (const key of PROFILE_SECTION_KEYS) {
    const supplied = result.sections?.[key] ?? result[key]
    if (supplied == null) normalized[key] = { status: 'unavailable', data: null }
    else if (supplied.status === 'available' || supplied.status === 'unavailable') normalized[key] = supplied
    else normalized[key] = { status: 'available', data: supplied }
  }
  return {
    ...result,
    contractVersion: result.contractVersion ?? 'local-area-profile.v1',
    center: result.center ?? null,
    radiusM: PROFILE_RADII.includes(Number(result.radiusM)) ? Number(result.radiusM) : null,
    sections: normalized,
  }
}

export function buildChartModel({ title, method, bins = [] }) {
  return {
    title: String(title ?? ''),
    subtitle: String(method ?? ''),
    bins: bins.map(({ label, value }) => ({ label: String(label), value: Number(value) })),
  }
}

export function createPreviewScheduler(onPreview, delay = 180) {
  let timer = null
  let requestId = 0
  return {
    schedule(payload) {
      if (timer !== null) clearTimeout(timer)
      timer = setTimeout(() => {
        timer = null
        onPreview(payload)
      }, delay)
    },
    nextRequestId() {
      requestId += 1
      return requestId
    },
    isCurrent(candidate) {
      return Number(candidate) === requestId
    },
    cancel() {
      if (timer !== null) clearTimeout(timer)
      timer = null
      requestId += 1
    },
  }
}
