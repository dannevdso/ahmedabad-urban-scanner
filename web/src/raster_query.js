import { fromUrl } from 'geotiff'
import proj4 from 'proj4'

const WGS84 = 'EPSG:4326'
const DEFAULT_BINS = {
  lst: [30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48],
  ndvi: [-1, 0, 0.3, 0.6, 1],
  height2023: [0, 3, 6, 10, 15, 25, 50],
  vegetationFraction: [0, 1, 2],
}

const METRIC_ALIASES = {
  LST: 'lst',
  surfaceTemperature: 'lst',
  height: 'height2023',
  buildingHeight2023: 'height2023',
  'vegetation-fraction': 'vegetationFraction',
}

function canonicalMetric(metric) {
  return METRIC_ALIASES[metric] ?? metric
}

function abortIfNeeded(signal) {
  if (signal?.aborted) throw new DOMException('The raster query was aborted', 'AbortError')
}

function normaliseRasterMetadata(raster, image) {
  const transform = raster.transform
  const origin = raster.origin ?? image.getOrigin?.() ?? (transform ? [transform[0], transform[3]] : null)
  const pixelSize = raster.pixelSize ?? image.getResolution?.() ?? (transform ? [transform[1], transform[5]] : null)
  const width = raster.width ?? image.getWidth()
  const height = raster.height ?? image.getHeight()
  if (!origin || !pixelSize || !width || !height) throw new Error('Raster manifest/image lacks origin, pixel size, or dimensions')
  return { ...raster, origin, pixelSize, width, height }
}

export function buildRasterWindow({ center, radiusM, raster }) {
  const [x, y] = center
  const [originX, originY] = raster.origin
  const [pixelWidth, pixelHeight] = raster.pixelSize
  if (!(pixelWidth > 0) || pixelHeight === 0) throw new RangeError('Raster pixel size must be non-zero')
  const minX = x - radiusM
  const maxX = x + radiusM
  const minY = y - radiusM
  const maxY = y + radiusM
  const left = Math.max(0, Math.floor((minX - originX) / pixelWidth))
  const right = Math.min(raster.width, Math.ceil((maxX - originX) / pixelWidth))
  const top = pixelHeight < 0
    ? Math.max(0, Math.floor((originY - maxY) / Math.abs(pixelHeight)))
    : Math.max(0, Math.floor((minY - originY) / pixelHeight))
  const bottom = pixelHeight < 0
    ? Math.min(raster.height, Math.ceil((originY - minY) / Math.abs(pixelHeight)))
    : Math.min(raster.height, Math.ceil((maxY - originY) / pixelHeight))
  return [left, top, Math.max(left, right), Math.max(top, bottom)]
}

function geometryBbox(geometry) {
  const points = []
  const visit = (value) => Array.isArray(value) && value.length >= 2 && value.every(Number.isFinite) ? points.push(value) : value?.forEach(visit)
  visit(geometry?.coordinates)
  if (!points.length) throw new TypeError('selection geometry must contain coordinates')
  return [Math.min(...points.map(([x]) => x)), Math.min(...points.map(([, y]) => y)), Math.max(...points.map(([x]) => x)), Math.max(...points.map(([, y]) => y))]
}
function buildRasterWindowForBbox({ bbox, raster }) {
  const [minX, minY, maxX, maxY] = bbox; const [originX, originY] = raster.origin; const [pixelWidth, pixelHeight] = raster.pixelSize
  const left = Math.max(0, Math.floor((minX - originX) / pixelWidth)); const right = Math.min(raster.width, Math.ceil((maxX - originX) / pixelWidth))
  const top = pixelHeight < 0 ? Math.max(0, Math.floor((originY - maxY) / Math.abs(pixelHeight))) : Math.max(0, Math.floor((minY - originY) / pixelHeight))
  const bottom = pixelHeight < 0 ? Math.min(raster.height, Math.ceil((originY - minY) / Math.abs(pixelHeight))) : Math.min(raster.height, Math.ceil((maxY - originY) / pixelHeight))
  return [left, top, Math.max(left, right), Math.max(top, bottom)]
}
function ringCovers(point, ring) { let inside = false; for (let i=0,j=ring.length-1;i<ring.length;j=i,i+=1) { const [xi,yi]=ring[i]; const [xj,yj]=ring[j]; if (yi > point[1] !== yj > point[1] && point[0] < ((xj-xi)*(point[1]-yi))/(yj-yi)+xi) inside=!inside }; return inside }
function geometryCovers(geometry, point) { const polygons=geometry.type==='Polygon'?[geometry.coordinates]:geometry.type==='MultiPolygon'?geometry.coordinates:[]; return polygons.some((polygon)=>ringCovers(point,polygon[0])&&!polygon.slice(1).some((ring)=>ringCovers(point,ring))) }
function transformGeometry(geometry, sourceCrs, targetCrs) { if (sourceCrs === targetCrs) return geometry; const visit=(value)=>Array.isArray(value)&&value.length>=2&&value.every(Number.isFinite)?proj4(sourceCrs,targetCrs,value):value.map(visit); return {...geometry,coordinates:visit(geometry.coordinates)} }

export function collectRasterPixels({ values, validMask, window, raster, center, radiusM, geometry = null }) {
  const [left, top, right, bottom] = window
  const [originX, originY] = raster.origin
  const [pixelWidth, pixelHeight] = raster.pixelSize
  const pixels = []
  let offset = 0
  for (let row = top; row < bottom; row += 1) {
    for (let col = left; col < right; col += 1) {
      const x = originX + (col + 0.5) * pixelWidth
      const y = originY + (row + 0.5) * pixelHeight
      const distanceM = center ? Math.hypot(x - center[0], y - center[1]) : null
      if (geometry ? geometryCovers(geometry, [x, y]) : distanceM <= radiusM) pixels.push({ value: values[offset], valid: validMask?.[offset] !== false, distanceM, row, col })
      offset += 1
    }
  }
  return pixels
}

function binCounts(values, bins) {
  const counts = Array.from({ length: Math.max(0, bins.length - 1) }, () => 0)
  for (const value of values) {
    for (let i = 0; i < bins.length - 1; i += 1) {
      const last = i === bins.length - 2
      if (value >= bins[i] && (value < bins[i + 1] || (last && value <= bins[i + 1]))) {
        counts[i] += 1
        break
      }
    }
  }
  return counts
}

export function summarizeRasterValues({ values, validMask, expectedPixelCount, cellAreaM2, bins = [], nodata }) {
  const valid = values.filter((value, index) => validMask?.[index] !== false && Number.isFinite(value) && value !== nodata)
  const sorted = [...valid].sort((a, b) => a - b)
  const mean = valid.length ? valid.reduce((sum, value) => sum + value, 0) / valid.length : null
  const median = sorted.length ? (sorted[Math.floor((sorted.length - 1) / 2)] + sorted[Math.ceil((sorted.length - 1) / 2)]) / 2 : null
  const variance = valid.length ? valid.reduce((sum, value) => sum + ((value - mean) ** 2), 0) / valid.length : null
  const maximum = valid.length ? sorted[sorted.length - 1] : null
  return {
    status: valid.length ? 'available' : 'unavailable',
    mean,
    median,
    maximum,
    max: maximum,
    standardDeviation: variance == null ? null : Math.sqrt(variance),
    std: variance == null ? null : Math.sqrt(variance),
    validPixelCount: valid.length,
    validAreaM2: valid.length * cellAreaM2,
    expectedPixelCount,
    coveragePercentage: expectedPixelCount ? (valid.length / expectedPixelCount) * 100 : 0,
    validCoveragePct: expectedPixelCount ? (valid.length / expectedPixelCount) * 100 : 0,
    distribution: { bins, counts: binCounts(valid, bins) },
  }
}

export function getRasterMetricProvenance(metric, manifest) {
  const entry = manifest?.metrics?.[metric] ?? {}
  if (entry.derivedFrom) return { metric, label: 'derived', source: entry.derivedFrom, threshold: entry.threshold }
  if (entry.modelled || metric === 'height2023') return { metric, label: 'modelled' }
  if (entry.oneScene || metric === 'lst' || metric === 'ndvi') return { metric, label: 'one-scene' }
  return { metric, label: 'published-raster' }
}

function extractRasterData(readResult) {
  if (Array.isArray(readResult)) return { values: readResult[0], validMask: readResult.mask }
  if (ArrayBuffer.isView(readResult)) return { values: readResult, validMask: undefined }
  return { values: readResult.data ?? readResult.values, validMask: readResult.mask }
}

export async function queryRasterMetric({ metric, center, radiusM, selection = null, manifest, signal, openTiff = fromUrl }) {
  const metricKey = canonicalMetric(metric)
  abortIfNeeded(signal)
  if (metricKey === 'heatGreenPriority' && !manifest?.metrics?.[metricKey]?.normalization) {
    return { status: 'unavailable', reason: 'canonical-normalization-unavailable', provenance: { metric: metricKey, label: 'unavailable' } }
  }
  const requested = manifest?.metrics?.[metricKey]
  const derived = metricKey === 'vegetationFraction'
  const sourceMetric = derived ? 'ndvi' : metricKey
  const entry = manifest?.metrics?.[sourceMetric]
  if (!entry?.url) return { status: 'unavailable', reason: `manifest-metadata-unavailable:${sourceMetric}` }
  abortIfNeeded(signal)
  const tiff = await openTiff(entry.url, { signal })
  abortIfNeeded(signal)
  const image = await tiff.getImage()
  const raster = normaliseRasterMetadata({ ...entry, crs: entry.crs ?? 'EPSG:32643', nodata: entry.nodata }, image)
  const geometry = selection?.type === 'tps' ? transformGeometry(selection.geometry, selection.crs ?? WGS84, raster.crs) : null
  const projectedCenter = geometry ? null : (raster.crs === WGS84 ? center : proj4(WGS84, raster.crs, center))
  const window = geometry ? buildRasterWindowForBbox({ bbox: geometryBbox(geometry), raster }) : buildRasterWindow({ center: projectedCenter, radiusM, raster })
  const [left, top, right, bottom] = window
  const width = right - left
  const height = bottom - top
  if (width <= 0 || height <= 0) return { status: 'unavailable', reason: 'raster-window-outside-bounds', provenance: getRasterMetricProvenance(metricKey, manifest) }
  const readResult = await image.readRasters({ window, samples: [0], interleave: true, signal })
  const { values, validMask } = extractRasterData(readResult)
  const pixels = collectRasterPixels({ values, validMask, window, raster, center: projectedCenter, radiusM, geometry })
  const includedValues = pixels.map(({ value }) => value)
  const includedMask = pixels.map(({ value, valid }) => valid && Number.isFinite(value) && value !== raster.nodata)
  const transformedValues = derived ? includedValues.map((value) => value === raster.nodata ? value : (value >= (requested?.threshold ?? 0.3) ? 1 : 0)) : includedValues
  const cellAreaM2 = Math.abs(raster.pixelSize[0] * raster.pixelSize[1])
  const result = summarizeRasterValues({ values: transformedValues, validMask: includedMask, expectedPixelCount: pixels.length, cellAreaM2, bins: requested?.bins ?? DEFAULT_BINS[metricKey] ?? [], nodata: raster.nodata })
  return {
    ...result,
    metric: metricKey,
    unit: requested?.unit ?? entry.unit,
    window,
    provenance: derived ? { ...getRasterMetricProvenance(metricKey, manifest), threshold: requested?.threshold ?? 0.3 } : getRasterMetricProvenance(metricKey, manifest),
  }
}
