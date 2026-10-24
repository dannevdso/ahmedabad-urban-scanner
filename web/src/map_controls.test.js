import { describe, expect, it } from 'vitest'

import { baseLayerVisibilityUpdates, captureLayerVisibility, isRoadLayer, layerVisibilityUpdates } from './map_controls.js'

describe('basemap visibility controls', () => {
  it('captures each basemap layer original visibility', () => {
    const layers = [
      { id: 'background', type: 'background' },
      { id: '3d-buildings', type: 'fill-extrusion', layout: { visibility: 'none' } },
    ]

    expect(captureLayerVisibility(layers)).toEqual([
      ['background', 'visible'],
      ['3d-buildings', 'none'],
    ])
  })

  it('hides all basemap layers and restores their original visibility', () => {
    const original = [
      ['background', 'visible'],
      ['3d-buildings', 'none'],
    ]

    expect(layerVisibilityUpdates(original, false)).toEqual([
      ['background', 'none'],
      ['3d-buildings', 'none'],
    ])
    expect(layerVisibilityUpdates(original, true)).toEqual(original)
  })

  it('recognises road geometry and road labels as a separate base layer', () => {
    expect(isRoadLayer({ id: 'road_minor', 'source-layer': 'transportation' })).toBe(true)
    expect(isRoadLayer({ id: 'highway-name-major', 'source-layer': 'transportation_name' })).toBe(true)
    expect(isRoadLayer({ id: 'water', 'source-layer': 'water' })).toBe(false)
  })

  it('keeps roads on while the rest of the background map is off by default', () => {
    const original = [
      { id: 'background', sourceLayer: '', visibility: 'visible' },
      { id: 'road_minor', sourceLayer: 'transportation', visibility: 'visible' },
      { id: 'highway-name-major', sourceLayer: 'transportation_name', visibility: 'visible' },
      { id: 'building-3d', sourceLayer: 'building', visibility: 'none' },
    ]
    expect(baseLayerVisibilityUpdates(original, { backgroundVisible: false, roadsVisible: true })).toEqual([
      ['background', 'none'],
      ['road_minor', 'visible'],
      ['highway-name-major', 'visible'],
      ['building-3d', 'none'],
    ])
  })
})
