import { deserialize as deserializeFlatGeobuf } from 'flatgeobuf/geojson'
import polygonClipping from 'polygon-clipping'
import proj4 from 'proj4'

const DEFAULT_MANIFEST_URL = './data/local-profile/manifest.json'
const PROFILE_RADII = [400, 800, 1200]
const FIXED_BINS = {
  buildingCount: [0, 25, 100, 250, 500, 1000, 2500],
  footprintAreaM2: [0, 25, 100, 250, 500, 1000, 5000],
  streetLengthKm: [0, 1, 3, 5, 10, 20, 50],
  intersectionDensityPerKm2: [0, 5, 10, 20, 40, 80],
  publicTransportStops: [0, 1, 3, 5, 10, 25],
}
const BUILDING_LOCATION_BINS = {
  provisionalHeightM: [0, 3, 6, 10, 20, 50, 100],
  provisionalAreaM2: [0, 25, 100, 250, 500, 1000, 5000],
  derivedVolumeM3: [0, 100, 500, 2000, 10000, 50000, 250000],
}
const SUHI_CATEGORIES = [
  ['low', 'Low'],
  ['moderate', 'Moderate'],
  ['high', 'High'],
  ['veryHigh', 'Very High'],
  ['extremeHigh', 'Extreme High'],
]
const ASSET_KEYS = ['buildings', 'buildingCentroids', 'buildingFootprints', 'footprints', 'streets', 'centrality', 'spaceSyntax', 'heatRisk', 'parks', 'schools', 'gtfsStops', 'transitStops', 'routeReach', 'routeReachCells']

function abortError() {
  return Object.assign(new Error('The local area profile request was aborted'), { name: 'AbortError' })
}
function throwIfAborted(signal) {
  if (signal?.aborted) throw abortError()
}
function finite(value) { return Number.isFinite(Number(value)) }
function assertCenter(center) {
  if (!Array.isArray(center) || center.length !== 2 || !center.every(finite)) throw new TypeError('center must be [longitude, latitude]')
}
function assertRadius(radiusM, allowed = PROFILE_RADII) {
  if (!allowed.includes(Number(radiusM))) throw new RangeError(`radius must be one of ${allowed.join(', ')}`)
}
function number(value) { const n = Number(value); return Number.isFinite(n) ? n : null }
function featureGeometry(feature) { return feature?.geometry ?? feature }
function geometryCoordinates(feature) { return featureGeometry(feature)?.coordinates }
function properties(feature) { return feature?.properties ?? {} }
function routeIds(value) {
  if (Array.isArray(value)) return value.map(String)
  if (value == null || value === '') return []
  if (typeof value === 'string' && value.trim().startsWith('[') && value.trim().endsWith(']')) {
    return value.trim().slice(1, -1).split(',').map((item) => item.trim().replace(/^['"]|['"]$/g, '')).filter(Boolean)
  }
  return [String(value)]
}
function ringCentroid(ring) {
  let areaTwice = 0; let x = 0; let y = 0
  for (let i = 0; i < ring.length - 1; i += 1) {
    const cross = ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1]
    areaTwice += cross; x += (ring[i][0] + ring[i + 1][0]) * cross; y += (ring[i][1] + ring[i + 1][1]) * cross
  }
  return areaTwice ? [x / (3 * areaTwice), y / (3 * areaTwice)] : ring[0]
}
function explicitCentroid(feature) {
  const p = properties(feature)
  if (finite(p.centroid_x) && finite(p.centroid_y)) return [Number(p.centroid_x), Number(p.centroid_y)]
  return null
}
function pointOf(feature, { allowGeometryFallback = true } = {}) {
  const geometry = featureGeometry(feature)
  if (geometry?.type === 'Point' && allowGeometryFallback) return geometry.coordinates
  const centroid = explicitCentroid(feature)
  if (centroid) return centroid
  const p = properties(feature)
  if (finite(p.x) && finite(p.y)) return [Number(p.x), Number(p.y)]
  if (allowGeometryFallback && geometry?.type === 'Polygon' && geometry.coordinates?.[0]?.length) return ringCentroid(geometry.coordinates[0])
  if (allowGeometryFallback && geometry?.type === 'MultiPolygon' && geometry.coordinates?.length) {
    const centroids = geometry.coordinates.map((polygon) => ringCentroid(polygon[0]))
    return centroids[0]
  }
  return null
}
function bboxIntersects(a, b) { return a[0] <= b[2] && a[2] >= b[0] && a[1] <= b[3] && a[3] >= b[1] }

export function transformWgs84ToMetric(center, metricCrs) {
  assertCenter(center)
  if (!metricCrs) throw new TypeError('metric CRS is required')
  const transformed = proj4('EPSG:4326', metricCrs, [Number(center[0]), Number(center[1])])
  return [Number(transformed[0]), Number(transformed[1])]
}

export function metricBboxForCircle(centerMetric, radiusM) {
  if (!Array.isArray(centerMetric) || centerMetric.length !== 2 || !centerMetric.every(finite)) throw new TypeError('metric center must be [x, y]')
  if (!finite(radiusM) || Number(radiusM) <= 0) throw new RangeError('radius must be positive')
  const [x, y] = centerMetric.map(Number)
  const radius = Number(radiusM)
  return [x - radius, y - radius, x + radius, y + radius]
}

function geometryBbox(geometry) {
  const coordinates = []
  const visit = (value) => {
    if (!Array.isArray(value)) return
    if (value.length >= 2 && value.every((item) => Number.isFinite(Number(item)))) coordinates.push(value)
    else value.forEach(visit)
  }
  visit(geometry?.coordinates)
  if (!coordinates.length) throw new TypeError('selection geometry must contain coordinates')
  return [Math.min(...coordinates.map(([x]) => Number(x))), Math.min(...coordinates.map(([, y]) => Number(y))), Math.max(...coordinates.map(([x]) => Number(x))), Math.max(...coordinates.map(([, y]) => Number(y)))]
}

function circlePolygon([x, y], radius, segments = 64) {
  const coordinates = []
  for (let i = 0; i <= segments; i += 1) {
    const theta = (i / segments) * Math.PI * 2
    coordinates.push([x + Math.cos(theta) * radius, y + Math.sin(theta) * radius])
  }
  return [coordinates]
}
function asPolygonCoordinates(geometry) {
  if (!geometry) return []
  if (geometry.type === 'Polygon') return [geometry.coordinates]
  if (geometry.type === 'MultiPolygon') return geometry.coordinates
  return []
}
function pointOnSegment(point, a, b, epsilon = 1e-8) {
  const cross = (point[1] - a[1]) * (b[0] - a[0]) - (point[0] - a[0]) * (b[1] - a[1])
  const length = Math.hypot(b[0] - a[0], b[1] - a[1])
  if (Math.abs(cross) > epsilon * Math.max(length, 1)) return false
  return point[0] >= Math.min(a[0], b[0]) - epsilon && point[0] <= Math.max(a[0], b[0]) + epsilon && point[1] >= Math.min(a[1], b[1]) - epsilon && point[1] <= Math.max(a[1], b[1]) + epsilon
}
function ringCovers(point, ring) {
  for (let index = 0; index < ring.length - 1; index += 1) if (pointOnSegment(point, ring[index], ring[index + 1])) return true
  return pointInRing(point, ring)
}
function polygonCoversPoint(point, polygons) {
  return polygons.some((polygon) => ringCovers(point, polygon[0]) && !polygon.slice(1).some((hole) => ringCovers(point, hole)))
}
function polygonContainsPoint(point, polygons) {
  return polygons.some((polygon) => {
    if (polygon.some((ring) => ring.slice(0, -1).some((start, index) => pointOnSegment(point, start, ring[index + 1])))) return false
    return pointInRing(point, polygon[0]) && !polygon.slice(1).some((hole) => pointInRing(point, hole))
  })
}
function transformGeometry(geometry, transform) {
  const visit = (value) => Array.isArray(value) && value.length >= 2 && value.every((item) => Number.isFinite(Number(item))) ? transform(value) : value.map(visit)
  return { ...geometry, coordinates: visit(geometry.coordinates) }
}
function areaOfRing(ring) {
  let area = 0
  for (let i = 0; i < ring.length - 1; i += 1) area += ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1]
  return Math.abs(area) / 2
}
function areaOfMultiPolygon(multipolygon) {
  return multipolygon.reduce((sum, polygon) => sum + areaOfRing(polygon[0]) - polygon.slice(1).reduce((holes, ring) => holes + areaOfRing(ring), 0), 0)
}
function selectionFromRequest({ center, radiusM, selection, metricCrs, transform, geometryTransform }) {
  if (selection?.type === 'tps') {
    if (!selection.geometry || !['Polygon', 'MultiPolygon'].includes(selection.geometry.type)) throw new TypeError('TPS selection geometry must be a Polygon or MultiPolygon')
    const metricGeometry = geometryTransform ? geometryTransform(selection.geometry, metricCrs) : transformGeometry(selection.geometry, (point) => transform(point, metricCrs))
    const polygons = asPolygonCoordinates(metricGeometry)
    const areaM2 = areaOfMultiPolygon(polygons)
    return { kind: 'tps', bbox: geometryBbox(metricGeometry), polygons, metricGeometry, areaM2, output: { type: 'tps', source_id: selection.source_id, tps_name: selection.tps_name ?? null, tps_no: selection.tps_no ?? null, tps_status: selection.tps_status ?? null, areaM2 } }
  }
  assertCenter(center); assertRadius(radiusM)
  const metricCenter = transform(center, metricCrs)
  const radius = Number(radiusM)
  return { kind: 'circle', center: metricCenter, radiusM: radius, bbox: metricBboxForCircle(metricCenter, radius), polygons: circlePolygon(metricCenter, radius), areaM2: Math.PI * radius * radius, output: { type: 'circle', center: [...center], radiusM: radius, areaM2: Math.PI * radius * radius } }
}
function unionInChunks(polygons, chunkSize = 128) {
  let current = []
  for (let i = 0; i < polygons.length; i += chunkSize) current.push(polygonClipping.union(...polygons.slice(i, i + chunkSize)))
  while (current.length > 1) {
    const next = []
    for (let i = 0; i < current.length; i += 2) next.push(i + 1 < current.length ? polygonClipping.union(current[i], current[i + 1]) : current[i])
    current = next
  }
  return current[0] ?? []
}
function polygonUnion(features) {
  const polygons = features.flatMap((feature) => asPolygonCoordinates(featureGeometry(feature)))
  if (!polygons.length) return []
  return unionInChunks(polygons)
}
function clippedUnionArea(features, circle) {
  const union = polygonUnion(features)
  if (!union.length) return 0
  const clipped = polygonClipping.intersection(union, circle)
  return areaOfMultiPolygon(clipped)
}
const FLOOD_RISK_CLASSES = [
  ['veryHigh', 'Very high', 'Very High Risk Areas'],
  ['high', 'High', 'High Risk Areas'],
  ['moderate', 'Moderate', 'Moderate Risk Areas'],
  ['low', 'Low', null],
]
function buildFloodRiskArea(features, circle) {
  if (!features.length) return { status: 'unavailable', unit: 'm²', categories: [], totalClassifiedAreaM2: null, reason: 'flood-risk source returned no candidates' }
  const categories = FLOOD_RISK_CLASSES.map(([key, label, sourceClass]) => {
    const matching = sourceClass ? features.filter((feature) => properties(feature).uf_risk === sourceClass) : []
    const areaM2 = matching.length ? clippedUnionArea(matching, circle) : (sourceClass === null ? null : 0)
    return { key, label, sourceClass, areaM2, status: areaM2 === null ? 'unavailable' : 'available' }
  })
  return { status: 'available', unit: 'm²', categories, totalClassifiedAreaM2: categories.reduce((sum, category) => sum + (category.areaM2 ?? 0), 0), caveat: 'The supplied VEDAS/ISRO source has no Low risk class; Low is shown as Unavailable rather than zero.' }
}
function pointInsideCircle(point, center, radius) {
  if (!point) return false
  const dx = point[0] - center[0]
  const dy = point[1] - center[1]
  return dx * dx + dy * dy <= radius * radius
}
function segmentInsideCircle(a, b, center, radius) {
  const dx = b[0] - a[0]
  const dy = b[1] - a[1]
  const fx = a[0] - center[0]
  const fy = a[1] - center[1]
  const aa = dx * dx + dy * dy
  if (aa === 0) return pointInsideCircle(a, center, radius) ? 0 : 0
  const bb = 2 * (fx * dx + fy * dy)
  const cc = fx * fx + fy * fy - radius * radius
  const discriminant = bb * bb - 4 * aa * cc
  const cuts = [0, 1]
  if (discriminant >= 0) {
    const root = Math.sqrt(discriminant)
    for (const t of [(-bb - root) / (2 * aa), (-bb + root) / (2 * aa)]) if (t > 0 && t < 1) cuts.push(t)
  }
  cuts.sort((x, y) => x - y)
  let length = 0
  for (let i = 0; i < cuts.length - 1; i += 1) {
    const t0 = cuts[i]; const t1 = cuts[i + 1]; const tm = (t0 + t1) / 2
    if (pointInsideCircle([a[0] + dx * tm, a[1] + dy * tm], center, radius)) length += Math.hypot(dx, dy) * (t1 - t0)
  }
  return length
}
function clippedLineLength(feature, center, radius) {
  const geometry = featureGeometry(feature)
  if (geometry?.type === 'LineString') return geometry.coordinates.slice(0, -1).reduce((sum, point, index) => sum + segmentInsideCircle(point, geometry.coordinates[index + 1], center, radius), 0)
  if (geometry?.type === 'MultiLineString') return geometry.coordinates.reduce((sum, line) => sum + line.slice(0, -1).reduce((part, point, index) => part + segmentInsideCircle(point, line[index + 1], center, radius), 0), 0)
  return 0
}
function segmentIntersectionParameter(a, b, c, d) {
  const rx = b[0] - a[0]; const ry = b[1] - a[1]
  const sx = d[0] - c[0]; const sy = d[1] - c[1]
  const denominator = rx * sy - ry * sx
  if (Math.abs(denominator) < 1e-12) return null
  const qx = c[0] - a[0]; const qy = c[1] - a[1]
  const t = (qx * sy - qy * sx) / denominator
  const u = (qx * ry - qy * rx) / denominator
  return t > 0 && t < 1 && u >= 0 && u <= 1 ? t : null
}
function segmentInsidePolygons(a, b, polygons) {
  const cuts = [0, 1]
  for (const polygon of polygons) {
    for (const ring of polygon) {
      for (let index = 0; index < ring.length - 1; index += 1) {
        const t = segmentIntersectionParameter(a, b, ring[index], ring[index + 1])
        if (t !== null) cuts.push(t)
      }
    }
  }
  cuts.sort((left, right) => left - right)
  const unique = cuts.filter((value, index) => index === 0 || Math.abs(value - cuts[index - 1]) > 1e-10)
  const dx = b[0] - a[0]; const dy = b[1] - a[1]; const segmentLength = Math.hypot(dx, dy)
  let length = 0
  for (let index = 0; index < unique.length - 1; index += 1) {
    const start = unique[index]; const end = unique[index + 1]; const middle = (start + end) / 2
    if (polygonCoversPoint([a[0] + dx * middle, a[1] + dy * middle], polygons)) length += segmentLength * (end - start)
  }
  return length
}
function clippedLineLengthForSelection(feature, selection) {
  if (selection.kind === 'circle') return clippedLineLength(feature, selection.center, selection.radiusM)
  const geometry = featureGeometry(feature)
  const lines = geometry?.type === 'LineString' ? [geometry.coordinates] : geometry?.type === 'MultiLineString' ? geometry.coordinates : []
  return lines.reduce((total, line) => total + line.slice(0, -1).reduce((sum, point, index) => sum + segmentInsidePolygons(point, line[index + 1], selection.polygons), 0), 0)
}
function pointCoveredBySelection(point, selection) {
  return Boolean(point) && (selection.kind === 'circle' ? pointInsideCircle(point, selection.center, selection.radiusM) : polygonCoversPoint(point, selection.polygons))
}
function pointInsideSelection(point, selection) {
  return Boolean(point) && (selection.kind === 'circle' ? pointInsideCircle(point, selection.center, selection.radiusM) : polygonContainsPoint(point, selection.polygons))
}
function valuesFrom(features, field) { return features.map((feature) => number(properties(feature)[field])).filter((value) => value !== null) }
function summary(values, bins) {
  const histogram = (sourceValues) => {
    if (!bins) return { bins: [], counts: [], method: 'fixed', interval: 'left_closed_right_open_except_last', underflowCount: 0, overflowCount: 0, totalCount: sourceValues.length }
    const counts = bins.slice(0, -1).map((lower, index) => sourceValues.filter((value) => value >= lower && (index === bins.length - 2 ? value <= bins[index + 1] : value < bins[index + 1])).length)
    return { bins, counts, method: 'fixed', interval: 'left_closed_right_open_except_last', underflowCount: sourceValues.filter((value) => value < bins[0]).length, overflowCount: sourceValues.filter((value) => value > bins.at(-1)).length, totalCount: sourceValues.length }
  }
  if (!values.length) return { status: 'unavailable', mean: null, median: null, min: null, max: null, std: null, histogram: histogram([]) }
  const sorted = [...values].sort((a, b) => a - b)
  const mean = values.reduce((sum, value) => sum + value, 0) / values.length
  const variance = values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / values.length
  return { status: 'available', mean, median: sorted.length % 2 ? sorted[(sorted.length - 1) / 2] : (sorted[sorted.length / 2 - 1] + sorted[sorted.length / 2]) / 2, min: sorted[0], max: sorted.at(-1), std: Math.sqrt(variance), histogram: histogram(values) }
}
function availability(available, denominator) { return { available, denominator } }
function normalizeSuhiClass(value) {
  if (typeof value !== 'string') return null
  let normalized = value.trim().replace(/\s+/g, ' ').toLowerCase()
  if (!normalized) return null
  if (normalized.endsWith(' suhi')) normalized = normalized.slice(0, -5).trim()
  return ({ low: 'Low', moderate: 'Moderate', high: 'High', 'very high': 'Very High', 'extreme high': 'Extreme High' })[normalized] ?? 'Other/unknown'
}
function summarizeSuhiCategories(values) {
  const counts = Object.fromEntries(SUHI_CATEGORIES.map(([, label]) => [label, 0]))
  for (const value of values) {
    const normalized = normalizeSuhiClass(value)
    if (normalized !== null) counts[normalized] = (counts[normalized] ?? 0) + 1
  }
  const categories = SUHI_CATEGORIES.map(([key, label]) => ({ key, label, count: counts[label] }))
  if (counts['Other/unknown']) categories.push({ key: 'otherUnknown', label: 'Other/unknown', count: counts['Other/unknown'] })
  const totalCount = Object.values(counts).reduce((sum, count) => sum + count, 0)
  const maximum = Math.max(...Object.values(counts))
  const dominantClass = [...SUHI_CATEGORIES.map(([, label]) => label), 'Other/unknown'].find((label) => counts[label] && counts[label] === maximum) ?? null
  return { categories, totalCount, dominantClass }
}
function buildingLocationSummary(features, selectionAreaM2) {
  const central = features.filter((feature) => properties(feature).zone_group === 'central')
  const enriched = features.filter((feature) => properties(feature).zone_group === 'enriched')
  const data = { totalLocationCount: features.length, centralLocationCount: central.length, enrichedLocationCount: enriched.length, buildingInclusionRule: 'boundary_inclusive_point_coverage', centralCountOnly: true }
  for (const [field, key, unit] of [['height_m', 'provisionalHeightM', 'm'], ['area_m2', 'provisionalAreaM2', 'm²'], ['volume_m3', 'derivedVolumeM3', 'm³']]) {
    const values = valuesFrom(enriched, field)
    const metricSummary = summary(values, BUILDING_LOCATION_BINS[key])
    data[key] = { status: values.length ? 'available' : 'unavailable', unit, summary: metricSummary, distribution: metricSummary.histogram, availability: availability(values.length, enriched.length), reason: values.length ? null : 'no valid enriched values; Central is count-only' }
  }
  const suhi = summarizeSuhiCategories(enriched.map((feature) => properties(feature).suhi))
  data.suhi = { status: suhi.totalCount ? 'available' : 'unavailable', kind: 'categorical', unit: 'unverified categorical class', summary: { dominantClass: suhi.dominantClass }, distribution: { categories: suhi.categories, totalCount: suhi.totalCount }, availability: availability(suhi.totalCount, enriched.length), reason: suhi.totalCount ? null : 'no valid enriched SUHI classes; Central is count-only' }
  const storedAreaValues = valuesFrom(enriched, 'area_m2')
  data.summedStoredAreaM2 = storedAreaValues.length ? storedAreaValues.reduce((sum, value) => sum + value, 0) : null
  data.storedAreaSharePct = storedAreaValues.length && selectionAreaM2 ? data.summedStoredAreaM2 / selectionAreaM2 * 100 : null
  data.storedAreaSelectionBasis = 'point-selected stored area / exact selection area; not exact footprint-union coverage'
  return data
}
function sourceMeta(asset, fallback = null) {
  const claim = asset?.claim_type ?? asset?.claimType
  const accuracy = asset?.accuracy ?? (claim === 'exact source geometry/fields' || claim === 'exact source numeric values' ? 'exact' : claim ? 'source-approximate' : 'unavailable')
  return { source: asset?.source ?? asset?.url ?? fallback, provenance: asset?.provenance ?? asset?.provenance_status ?? null, accuracy }
}
function availableSection(data, asset, denominator = 1) { return { status: 'available', data, availability: availability(denominator, denominator), ...sourceMeta(asset) } }
function unavailableSection(reason, asset, denominator = 0) { return { status: 'unavailable', data: null, availability: availability(0, denominator), reason, ...sourceMeta(asset), accuracy: 'unavailable' } }
function pickAsset(manifest, names) { return names.map((name) => manifest.assets?.[name]).find(Boolean) }
function featureValue(feature, names) { const p = properties(feature); for (const name of names) if (number(p[name]) !== null) return number(p[name]); return null }
function normalizeManifest(manifest, manifestUrl) {
  const base = (() => { try { return new URL(manifestUrl, globalThis.location?.href ?? 'http://localhost/') } catch { return null } })()
  const assets = Object.fromEntries(Object.entries(manifest.assets ?? {}).map(([key, asset]) => {
    const rawUrl = asset.url ?? asset.path
    const url = asset.url ?? (base && rawUrl ? new URL(rawUrl, base).href : rawUrl)
    return [key, { ...asset, url, accuracy: asset.accuracy ?? (asset.claim_type === 'exact source geometry/fields' ? 'exact' : asset.claim_type ? 'source-approximate' : undefined) }]
  }))
  return { ...manifest, metricCrs: manifest.metricCrs ?? manifest.target_crs ?? manifest.crs, radiiM: manifest.radiiM ?? manifest.allowed_radii_m ?? manifest.profileRadiiM, assets }
}
function pointInRing(point, ring) {
  let inside = false
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i, i += 1) {
    const [xi, yi] = ring[i]; const [xj, yj] = ring[j]
    const crosses = yi > point[1] !== yj > point[1] && point[0] < ((xj - xi) * (point[1] - yi)) / (yj - yi) + xi
    if (crosses) inside = !inside
  }
  return inside
}
function intersectsCircle(feature, circle) {
  const geometry = featureGeometry(feature)
  if (geometry?.type === 'Point') return pointInRing(geometry.coordinates, circle[0])
  const polygons = asPolygonCoordinates(geometry)
  return polygons.length > 0 && polygonClipping.intersection(polygons, circle).length > 0
}

async function collectFeatures(deserialize, asset, bbox, signal, guardrails = {}) {
  throwIfAborted(signal)
  if (!asset) return []
  const output = []; let estimatedBytes = 0
  const rect = { minX: bbox[0], minY: bbox[1], maxX: bbox[2], maxY: bbox[3] }
  const stream = deserialize(asset.url, { rect })
  for await (const feature of stream) {
    throwIfAborted(signal)
    estimatedBytes += JSON.stringify(feature).length
    if (output.length >= (guardrails.maxFeatures ?? 100000)) throw new RangeError(`FlatGeobuf candidate limit exceeded for ${asset.url}`)
    if (estimatedBytes > (guardrails.maxDecodedBytes ?? 128 * 1024 * 1024)) throw new RangeError(`FlatGeobuf decoded memory limit exceeded for ${asset.url}`)
    output.push(feature)
  }
  return output
}

function buildStreetSection(features, selection, asset) {
  if (!features.length) return unavailableSection('street network returned no candidates', asset)
  const orderedFeatures = [...features].sort((a, b) => Number(properties(b).seg_id ?? 0) - Number(properties(a).seg_id ?? 0))
  const selectedEdges = orderedFeatures.map((feature) => ({ feature, length: clippedLineLengthForSelection(feature, selection) })).filter(({ length }) => length > 0)
  const lengths = selectedEdges.map(({ length }) => length)
  const nodeCoordinates = new Map(); const graph = new Map(); const degree = new Map()
  for (const feature of orderedFeatures) {
    const geometry = featureGeometry(feature); const p = properties(feature)
    if (!['LineString', 'MultiLineString'].includes(geometry?.type)) continue
    const line = geometry.type === 'LineString' ? geometry.coordinates : geometry.coordinates[0]
    const u = p.u ?? p.source; const v = p.v ?? p.target
    if (u == null || v == null || !line?.length) continue
    nodeCoordinates.set(String(u), line[0]); nodeCoordinates.set(String(v), line.at(-1))
  }
  const nodes = [...nodeCoordinates.entries()].filter(([, point]) => pointInsideSelection(point, selection)).map(([id]) => id)
  for (const { feature } of selectedEdges) {
    const p = properties(feature); const geometry = featureGeometry(feature); const line = geometry?.type === 'LineString' ? geometry.coordinates : geometry?.coordinates?.[0]
    const u = p.u ?? p.source; const v = p.v ?? p.target
    if (u == null || v == null || !line) continue
    if (!graph.has(String(u))) graph.set(String(u), new Set()); if (!graph.has(String(v))) graph.set(String(v), new Set())
    graph.get(String(u)).add(String(v)); graph.get(String(v)).add(String(u))
    if (pointInsideSelection(nodeCoordinates.get(String(u)), selection)) degree.set(String(u), (degree.get(String(u)) ?? 0) + 1)
    if (pointInsideSelection(nodeCoordinates.get(String(v)), selection)) degree.set(String(v), (degree.get(String(v)) ?? 0) + 1)
  }
  const seen = new Set(); let largest = 0
  for (const start of nodes) {
    if (seen.has(start)) continue
    const stack = [start]; seen.add(start); let size = 0
    while (stack.length) { const node = stack.pop(); size += 1; for (const next of graph.get(node) ?? []) if (nodes.includes(next) && !seen.has(next)) { seen.add(next); stack.push(next) } }
    largest = Math.max(largest, size)
  }
  const clippedLengthM = lengths.reduce((sum, value) => sum + value, 0)
  const areaKm2 = selection.areaM2 / 1e6
  const data = { clippedLengthM, clippedLengthKm: clippedLengthM / 1000, intersectionDensityPerKm2: areaKm2 ? nodes.filter((id) => (degree.get(id) ?? 0) >= 3).length / areaKm2 : null, linkNodeRatio: nodes.length ? lengths.length / nodes.length : null, connectedNodeRatio: nodes.length ? largest / nodes.length : null, topologyRule: 'authoritative u/v or source/target IDs; clip-created boundary points excluded', fixedBins: { streetLengthKm: summary([clippedLengthM / 1000], FIXED_BINS.streetLengthKm).histogram, intersectionDensityPerKm2: summary([nodes.filter((id) => (degree.get(id) ?? 0) >= 3).length / areaKm2], FIXED_BINS.intersectionDensityPerKm2).histogram } }
  return availableSection(data, asset, features.length)
}

function buildWeightedSection(features, fields, selection, asset) {
  if (!features.length) return unavailableSection('weighted vector source returned no candidates', asset)
  const aliases = { betweenness: ['betweenness', 'betw_edge'], closeness: ['closeness', 'clo_mean'], straightness: ['straightness', 'str_mean'] }
  const result = {}
  for (const field of fields) {
    let total = 0; let weighted = 0; let count = 0
    for (const feature of features) { const value = featureValue(feature, aliases[field] ?? [field]); const length = clippedLineLengthForSelection(feature, selection); if (value !== null && length > 0) { weighted += value * length; total += length; count += 1 } }
    result[field] = total ? { status: 'available', weightedMean: weighted / total, weightField: 'clippedLengthM', weightTotal: total, availability: availability(count, features.length) } : { status: 'unavailable', weightedMean: null, weightField: 'clippedLengthM', weightTotal: 0, availability: availability(0, features.length) }
  }
  return availableSection(result, asset, features.length)
}

export function createLocalAreaProfileAdapter(options = {}) {
  const manifestUrl = options.manifestUrl ?? DEFAULT_MANIFEST_URL
  const fetchImpl = options.fetchImpl ?? globalThis.fetch
  const deserialize = options.deserialize ?? ((url, query) => deserializeFlatGeobuf(url, query))
  const manifestProvided = options.manifest ?? null
  const transform = options.centerTransform ?? ((center, crs) => transformWgs84ToMetric(center, crs))
  let manifestPromise = manifestProvided ? Promise.resolve(manifestProvided) : null
  const assetCache = new Map()
  let activeController = null

  async function loadManifest(signal) {
    if (!manifestPromise) manifestPromise = fetchImpl(manifestUrl, { signal }).then((response) => { if (!response.ok && response.ok !== undefined) throw new Error(`Unable to load local profile manifest: ${response.status}`); return response.json() })
    return normalizeManifest(await manifestPromise, manifestUrl)
  }
  async function query({ center, radiusM = 400, selection: requestedSelection = null, signal: externalSignal, phase = 'release' } = {}) {
    const manifest = await loadManifest(externalSignal)
    throwIfAborted(externalSignal)
    const radii = manifest.radiiM ?? manifest.profileRadiiM ?? PROFILE_RADII
    if (requestedSelection?.type !== 'tps') { assertCenter(center); assertRadius(radiusM, radii) }
    if (phase === 'preview') return { contractVersion: 'local-area-profile.v1', center: center ? [...center] : null, radiusM: requestedSelection?.type === 'tps' ? null : Number(radiusM), selection: requestedSelection ? { ...requestedSelection, geometry: undefined } : undefined, sections: { overview: availableSection({ radiusM: requestedSelection?.type === 'tps' ? null : Number(radiusM), preview: true }, null), availability: availableSection({ preview: true }, null) }, provenance: { manifest: manifestUrl } }
    if (activeController) activeController.abort()
    const requestController = new AbortController()
    activeController = requestController
    const signal = requestController.signal
    if (externalSignal) externalSignal.addEventListener('abort', () => requestController.abort(), { once: true })
    const metricCrs = manifest.metricCrs ?? manifest.crs ?? 'EPSG:32643'
    const activeSelection = selectionFromRequest({ center, radiusM, selection: requestedSelection, metricCrs, transform, geometryTransform: options.geometryTransform })
    const metricCenter = activeSelection.center ?? null
    const bbox = activeSelection.bbox
    const circle = activeSelection.polygons
    const diagnostics = { startedAt: performance.now(), assets: {} }
    const get = async (names) => {
      const asset = pickAsset(manifest, names)
      if (!asset) return { asset: null, features: [] }
      if (options.guardrails?.maxSourceBytes != null && Number(asset.bytes) > options.guardrails.maxSourceBytes) throw new RangeError(`FlatGeobuf source byte limit exceeded for ${asset.url}`)
      const key = `${asset.url}|${bbox.join(',')}`
      if (assetCache.has(key)) return { asset, features: assetCache.get(key) }
      const startedAt = performance.now()
      const features = await collectFeatures(deserialize, asset, bbox, signal, options.guardrails)
      assetCache.set(key, features)
      diagnostics.assets[asset.url] = { candidateCount: features.length, estimatedDecodedBytes: features.reduce((sum, feature) => sum + JSON.stringify(feature).length, 0), durationMs: performance.now() - startedAt }
      return { asset, features }
    }
    const [buildingLocations, streets, centrality, syntax, heat, parks, schools, stops, reach, floodRisk] = await Promise.all([get(['buildingLocations']), get(['streets']), get(['centrality']), get(['spaceSyntax', 'space_syntax']), get(['heatRisk', 'heat_risk']), get(['parks', 'parks_schools']), get(['schools', 'parks_schools']), get(['gtfsStops', 'gtfs_stops', 'transitStops']), get(['routeReach', 'routeReachCells']), get(['floodRisk', 'flood_risk'])])
    throwIfAborted(signal)
    const selectedLocations = buildingLocations.features.filter((feature) => pointCoveredBySelection(pointOf(feature), activeSelection))
    const locationData = buildingLocations.asset ? buildingLocationSummary(selectedLocations, activeSelection.areaM2) : null
    const buildingsSection = buildingLocations.asset
      ? availableSection(locationData, buildingLocations.asset, buildingLocations.features.length)
      : unavailableSection('building-location point asset unavailable; polygon fallback is retired', null)
    const centralitySection = buildWeightedSection(centrality.features, ['betweenness', 'closeness', 'straightness'], activeSelection, centrality.asset)
    const syntaxSection = buildWeightedSection(syntax.features, ['betweenness', 'closeness', 'straightness'], activeSelection, syntax.asset)
    const weightedSection = centrality.asset || syntax.asset
      ? availableSection({ centrality: centralitySection.data, spaceSyntax: syntaxSection.data }, centrality.asset ?? syntax.asset, centrality.features.length + syntax.features.length)
      : unavailableSection('centrality and space-syntax sources unavailable')
    const heatValues = heat.features.filter((feature) => intersectsCircle(feature, circle)).map((feature) => featureValue(feature, ['risk', 'heat_risk', 'heatRisk', 'uhi_risk', 'value'])).filter((value) => value !== null)
    const environmentData = {}
    if (heat.asset) environmentData.heatRisk = summary(heatValues)
    if (floodRisk.asset) environmentData.floodRiskArea = buildFloodRiskArea(floodRisk.features, circle)
    const environment = Object.keys(environmentData).length ? availableSection({ ...environmentData, selectionRule: 'vector candidates in metric bbox; source geometry retained' }, heat.asset ?? floodRisk.asset, (heat.features.length + floodRisk.features.length)) : unavailableSection('heat-risk and flood-risk vector sources unavailable')
    const pointCounts = {}
    const poiMatches = (feature, kind) => { const p = properties(feature); const value = String(p.kind ?? p.poi_type ?? '').toLowerCase(); return !value || value === kind || value === `${kind}s` || value.includes(kind) }
    if (parks.asset) pointCounts.parks = { count: parks.features.filter((feature) => poiMatches(feature, 'park') && pointCoveredBySelection(pointOf(feature), activeSelection)).length, availability: availability(parks.features.length, parks.features.length) }
    if (schools.asset) pointCounts.schools = { count: schools.features.filter((feature) => poiMatches(feature, 'school') && pointCoveredBySelection(pointOf(feature), activeSelection)).length, availability: availability(schools.features.length, schools.features.length) }
    const parksEducation = Object.keys(pointCounts).length ? availableSection(pointCounts, parks.asset ?? schools.asset, (parks.features.length + schools.features.length)) : unavailableSection('park and school point sources unavailable')
    const stopFeatures = stops.features.filter((feature) => pointCoveredBySelection(pointOf(feature), activeSelection))
    const routes = [...new Set(stopFeatures.flatMap((feature) => routeIds(properties(feature).route_ids ?? properties(feature).routeIds)))].sort()
    const matchingReach = reach.features.filter((feature) => routeIds(properties(feature).route_ids ?? properties(feature).routeIds).some((id) => routes.includes(id)))
    const transitData = stops.asset && routes.length ? { stopsInsideCircle: stopFeatures.length, routesServingStopsInsideCircle: routes, routeReachCells: matchingReach.length, routeReachCoveragePct: reach.features.length ? clippedUnionArea(matchingReach, circle) / activeSelection.areaM2 * 100 : null, routeSelectionRule: activeSelection.kind === 'tps' ? 'routes serving GTFS stops covered by exact TPS polygon; route-reach cells clipped to TPS polygon' : 'routes serving GTFS stops inside circle; existing route-reach cells intersected with circle' } : null
    const publicTransport = transitData ? availableSection(transitData, stops.asset, stops.features.length) : unavailableSection(stops.asset ? 'route-serving-stop relationship unavailable' : 'GTFS stops source unavailable', stops.asset, stops.features.length)
    const sections = { overview: availableSection({ areaM2: activeSelection.areaM2, radiusM: activeSelection.kind === 'circle' ? Number(radiusM) : null, metricCrs }, null), buildings: buildingsSection, streetsConnectivity: buildStreetSection(streets.features, activeSelection, streets.asset), spaceSyntaxCentrality: weightedSection, environment, publicTransport, parksEducation, availability: availableSection({ buildings: buildingsSection.status, streetsConnectivity: streets.asset ? 'available' : 'unavailable', spaceSyntaxCentrality: weightedSection.status, environment: environment.status, publicTransport: publicTransport.status, parksEducation: parksEducation.status }, null), methods: availableSection({ selection: activeSelection.kind === 'tps' ? 'exact polygon' : 'metric CRS circle', clipping: 'polygon-clipping', buildingSelection: 'boundary-inclusive point coverage from building-location asset only', weightedMetrics: 'clipped line length', fixedBins: FIXED_BINS }, null) }
    return { contractVersion: 'local-area-profile.v1', center: center ? [...center] : null, radiusM: activeSelection.kind === 'circle' ? Number(radiusM) : null, selection: activeSelection.output, metricCenter, metricBbox: bbox, sections, diagnostics: { ...diagnostics, durationMs: performance.now() - diagnostics.startedAt, requestBytes: null, requestBytesStatus: 'unavailable from FlatGeobuf deserialize API' }, provenance: { manifest: manifest.provenance?.manifest ?? manifestUrl, assets: Object.fromEntries(Object.entries(manifest.assets ?? {}).map(([key, asset]) => [key, asset.source ?? asset.url])) }, accuracy: { buildings: buildingsSection.accuracy, footprintCoverage: 'unavailable', streets: sections.streetsConnectivity.accuracy, weightedMetrics: weightedSection.accuracy, environment: environment.accuracy, transit: publicTransport.accuracy } }
  }
  return { query, loadManifest, clearCache: () => { assetCache.clear(); if (!manifestProvided) manifestPromise = null }, abort: () => activeController?.abort() }
}

export async function queryLocalAreaProfile(options, request) { return createLocalAreaProfileAdapter(options).query(request) }
