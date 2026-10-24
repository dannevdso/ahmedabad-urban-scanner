import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'

import { PLANX_OVERLAYS, PLANX_SOURCES } from './planx_layers.js'

describe('canonical centrality publication', () => {
  it('publishes one bounded centrality overlay and no duplicate network overlay', () => {
    expect(PLANX_SOURCES.network).toBeUndefined()
    expect(PLANX_OVERLAYS.some(({ key }) => key === 'network')).toBe(false)
    expect(PLANX_SOURCES.centrality).toEqual({ type: 'geojson', data: './data/planx-centrality.geojson' })
    expect(PLANX_OVERLAYS.filter(({ key }) => key === 'centrality')).toHaveLength(1)
  })

  it('does not advertise height-dependent stages as pending after raster publication', () => {
    const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8')
    const layers = readFileSync(new URL('./planx_layers.js', import.meta.url), 'utf8')
    expect(layers).toContain("label: '2023 modelled building height'")
    expect(layers).toContain("contextKey: 'modelled-building-height'")
    expect(html).not.toContain('height-dependent stages remain pending')
  })

  it('does not expose controls for stale products absent from the current export', () => {
    for (const key of ['deadends', 'serviceAreas', 'proposedSites', 'greenConnectivity', 'routes']) {
      expect(PLANX_SOURCES[key]).toBeUndefined()
      expect(PLANX_OVERLAYS.some((overlay) => overlay.key === key)).toBe(false)
    }
  })
})
