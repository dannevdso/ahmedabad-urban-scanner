import { describe, expect, it } from 'vitest'

import { BUILDING_HEIGHT_FINE_MAX_ZOOM, BUILDING_HEIGHT_FINE_MIN_ZOOM, BUILDING_HEIGHT_TILE_ZOOMS, buildingHeightLayers, buildingHeightSources } from './building_height.js'

describe('hybrid building-height publication', () => {
  it('publishes overview only below the fine-raster switch and fine tiles above it', () => {
    expect(BUILDING_HEIGHT_FINE_MIN_ZOOM).toBe(8)
    expect(BUILDING_HEIGHT_FINE_MAX_ZOOM).toBe(22)
    expect(BUILDING_HEIGHT_TILE_ZOOMS).toEqual([8, 11, 14, 16])
    expect(buildingHeightSources.overview.type).toBe('image')
    expect(buildingHeightSources.fine).toHaveLength(4)
    expect(buildingHeightSources.fine.map((source) => source.maxzoom)).toEqual([8, 11, 14, 16])
    expect(buildingHeightSources.fine.every((source) => source.tiles[0].includes('/building-height-fine/{z}/{x}/{y}.webp'))).toBe(true)
    expect(buildingHeightLayers.overview.maxzoom).toBe(BUILDING_HEIGHT_FINE_MIN_ZOOM)
    expect(buildingHeightLayers.fine.map((layer) => [layer.minzoom, layer.maxzoom])).toEqual([[8, 11], [11, 14], [14, 16], [16, 22]])
  })

  it('keeps the overview and fine layers mutually exclusive at the threshold', () => {
    expect(buildingHeightLayers.overview.paint['raster-opacity']).toBe(0.7)
    expect(buildingHeightLayers.fine.every((layer) => layer.paint['raster-opacity'] === 0.7)).toBe(true)
  })
})
