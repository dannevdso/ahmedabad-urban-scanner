import { describe, expect, it } from 'vitest'
import proj4 from 'proj4'

import {
  buildRasterWindow,
  collectRasterPixels,
  queryRasterMetric,
  summarizeRasterValues,
  getRasterMetricProvenance,
} from './raster_query.js'

const fixtureRaster = {
  crs: 'EPSG:32643',
  origin: [500000, 2600000],
  pixelSize: [10, -10],
  width: 6,
  height: 6,
  nodata: -9999,
}

const manifest = {
  contractVersion: 'local-area-profile.static.v1',
  metrics: {
    ndvi: { url: '/ndvi.tif', crs: 'EPSG:32643', unit: 'unitless', oneScene: true, nodata: -9999, bins: [-1, 0, 0.3, 0.6, 1] },
    lst: { url: '/lst.tif', crs: 'EPSG:32643', unit: '°C', oneScene: true },
    height2023: { url: '/height.tif', crs: 'EPSG:32643', unit: 'metres', modelled: true },
    vegetationFraction: { derivedFrom: 'ndvi', threshold: 0.3, unit: '0–1' },
  },
}

const WGS84_CENTER = proj4('EPSG:32643', 'EPSG:4326', [500005, 2599995])

function fakeOpenTiff(values) {
  return async () => ({
    getImage: async () => ({
      getWidth: () => fixtureRaster.width,
      getHeight: () => fixtureRaster.height,
      getOrigin: () => fixtureRaster.origin,
      getResolution: () => fixtureRaster.pixelSize,
      readRasters: async ({ window, signal }) => {
        if (signal?.aborted) throw new DOMException('Aborted', 'AbortError')
        const [left, top, right, bottom] = window
        const output = []
        for (let row = top; row < bottom; row += 1) {
          for (let col = left; col < right; col += 1) output.push(values[row * fixtureRaster.width + col])
        }
        return [Float32Array.from(output)]
      },
    }),
  })
}

describe('browser raster query', () => {
  it('computes a clamped intersecting window in raster coordinates', () => {
    expect(buildRasterWindow({
      center: [500005, 2599995],
      radiusM: 12,
      raster: fixtureRaster,
    })).toEqual([0, 0, 2, 2])
  })

  it('includes pixels by pixel center, not pixel corners', () => {
    const values = Float32Array.from([1, 2, 3, 4])
    const pixels = collectRasterPixels({
      values,
      window: [0, 0, 2, 2],
      raster: { ...fixtureRaster, width: 2, height: 2 },
      center: [500005, 2599995],
      radiusM: 15,
    })
    expect(pixels.map(({ value }) => value)).toEqual([1, 2, 3, 4])
    expect(pixels.every(({ distanceM }) => distanceM <= 15)).toBe(true)
  })

  it('drops nodata, NaN and masked pixels before calculating statistics', () => {
    const summary = summarizeRasterValues({
      values: [1, 2, -9999, Number.NaN, 5],
      validMask: [true, true, true, true, false],
      expectedPixelCount: 5,
      cellAreaM2: 100,
      bins: [0, 2, 4, 6],
      nodata: -9999,
    })
    expect(summary).toMatchObject({ mean: 1.5, median: 1.5, maximum: 2, standardDeviation: 0.5, validPixelCount: 2, validAreaM2: 200, coveragePercentage: 40 })
    expect(summary.distribution.counts).toEqual([1, 1, 0])
  })

  it('reads only the window and returns provenance for one-scene and modelled metrics', async () => {
    const calls = []
    const openTiff = async (url) => {
      const tiff = await fakeOpenTiff(Float32Array.from([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36]))()
      const image = await tiff.getImage()
      const original = image.readRasters
      image.readRasters = async (options) => { calls.push({ url, window: options.window }); return original(options) }
      return { getImage: async () => image }
    }
    const result = await queryRasterMetric({ metric: 'ndvi', center: WGS84_CENTER, radiusM: 12, manifest, openTiff })
    expect(calls[0].window).toEqual([0, 0, 2, 2])
    expect(result.provenance).toMatchObject({ label: 'one-scene', metric: 'ndvi' })
    expect(getRasterMetricProvenance('height2023', manifest)).toMatchObject({ label: 'modelled', metric: 'height2023' })
  })

  it('uses one-degree surface-temperature bins from 30 to 48 °C', async () => {
    const values = Float32Array.from(Array.from({ length: 36 }, (_, index) => 35 + index * 0.25))
    const result = await queryRasterMetric({ metric: 'lst', center: WGS84_CENTER, radiusM: 12, manifest, openTiff: fakeOpenTiff(values) })
    expect(result.distribution.bins).toEqual([30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48])
  })

  it('supports vegetation fraction as a derived NDVI threshold metric', async () => {
    const ndviValues = Float32Array.from([
      0.1, 0.4, 0.5, 0.2, 0.7, 0.8, 0.1, 0.2, 0.9, 0.4, 0.1, 0.2,
      0.6, 0.7, 0.8, 0.9, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8,
      0.9, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.1, 0.2,
    ])
    const result = await queryRasterMetric({ metric: 'vegetationFraction', center: WGS84_CENTER, radiusM: 12, manifest, openTiff: fakeOpenTiff(ndviValues) })
    expect(result.provenance).toMatchObject({ label: 'derived', metric: 'vegetationFraction', threshold: 0.3 })
    expect(result.mean).toBeGreaterThan(0)
  })

  it('honours an already-aborted signal without opening the raster', async () => {
    const controller = new AbortController()
    controller.abort()
    let opened = false
    await expect(queryRasterMetric({ metric: 'ndvi', center: WGS84_CENTER, radiusM: 12, manifest, signal: controller.signal, openTiff: async () => { opened = true; return fakeOpenTiff([])() } })).rejects.toMatchObject({ name: 'AbortError' })
    expect(opened).toBe(false)
  })

  it('does not invent heat-green priority without canonical normalization', async () => {
    const result = await queryRasterMetric({ metric: 'heatGreenPriority', center: [500005, 2599995], radiusM: 12, manifest, openTiff: fakeOpenTiff([]) })
    expect(result).toMatchObject({ status: 'unavailable', reason: 'canonical-normalization-unavailable' })
  })

  it('masks TPS raster pixels by exact polygon centers and preserves nodata coverage', async () => {
    const selection = { type: 'tps', crs: 'EPSG:32643', geometry: { type: 'Polygon', coordinates: [[[500000, 2599980], [500020, 2599980], [500020, 2600000], [500000, 2600000], [500000, 2599980]]] } }
    const result = await queryRasterMetric({ metric: 'ndvi', selection, manifest, openTiff: fakeOpenTiff(Float32Array.from([-9999, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36])) })
    expect(result.window).toEqual([0, 0, 2, 2])
    expect(result.expectedPixelCount).toBe(4)
    expect(result.validPixelCount).toBe(3)
    expect(result.status).toBe('available')
  })
})
