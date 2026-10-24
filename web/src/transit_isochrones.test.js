import { describe, expect, it } from 'vitest'

import { buildRouteReachCatchment } from './transit_isochrones.js'

const model = {
  nearby_stop_seconds: 5 * 60,
  catchment_seconds: 15 * 60,
  stops: [
    { id: 'A', name: 'Alpha', lon: 72.5, lat: 23 },
    { id: 'B', name: 'Beta', lon: 72.51, lat: 23 },
    { id: 'C', name: 'Gamma', lon: 72.52, lat: 23 },
    { id: 'D', name: 'Delta', lon: 72.53, lat: 23 },
  ],
  footpaths: [[0, 1, 240], [0, 2, 360]],
  stop_routes: [[0], [0, 1], [0], [1]],
  route_stops: [[0, 1, 2], [1, 3]],
  cells: [
    { geometry: { type: 'Polygon', coordinates: [[[72.5, 23], [72.51, 23], [72.51, 23.01], [72.5, 23.01], [72.5, 23]]] }, links: [[0, 120]] },
    { geometry: { type: 'Polygon', coordinates: [[[72.6, 23], [72.61, 23], [72.61, 23.01], [72.6, 23.01], [72.6, 23]]] }, links: [[2, 600]] },
    { geometry: { type: 'Polygon', coordinates: [[[72.7, 23], [72.71, 23], [72.71, 23.01], [72.7, 23.01], [72.7, 23]]] }, links: [[3, 900]] },
    { geometry: { type: 'Polygon', coordinates: [[[72.8, 23], [72.81, 23], [72.81, 23.01], [72.8, 23.01], [72.8, 23]]] }, links: [[3, 901]] },
  ],
}

describe('transit isochrones', () => {
  it('uses the selected stop plus stops within five minutes to find all route stops', () => {
    const result = buildRouteReachCatchment(model, 0)
    expect(result.seedStopIndexes).toEqual([0, 1])
    expect(result.routeIndexes).toEqual([0, 1])
    expect(result.routeStopIndexes).toEqual([0, 1, 2, 3])
  })

  it('builds a 15-minute street-network catchment from every accessible route stop', () => {
    const result = buildRouteReachCatchment(model, 0)
    expect(result.minutes15.features).toHaveLength(3)
    expect(result.minutes15.features.every(({ properties }) => properties.walk_time_minutes <= 15)).toBe(true)
    expect(result.routeStops.features.map(({ properties }) => properties.stop_id)).toEqual(['A', 'B', 'C', 'D'])
  })

  it('also returns the selected-stop-only direct walking catchment', () => {
    const result = buildRouteReachCatchment(model, 0)
    expect(result.directMinutes15.features).toHaveLength(1)
    expect(result.directCellIndexes).toEqual([0])
    expect(result.routeReachCellIndexes).toEqual([0, 1, 2])
  })
})