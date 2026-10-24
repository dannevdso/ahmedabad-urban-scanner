import { describe, expect, it } from 'vitest'

import { buildStopDetails, formatAreaM2, graphAxisTicks, graphHourTicks, graphSeries, routeColor, selectedRouteFilter, sumCellArea } from './transit_details.js'

const model = {
  service_hours: [6, 7, 8, 9],
  route_ids: [{ id: 'r1', short_name: '1', long_name: 'One' }, { id: 'r2', short_name: '2', long_name: 'Two' }],
  stops: [{ id: 'A', name: 'Alpha', lon: 72.5, lat: 23 }],
  stop_route_service: [[[0, 10, [2, 4, 6, 8]], [1, null, [0, 1, 0, 2]]]],
  cells: [
    { area_m2: 100, links: [[0, 120]] },
    { area_m2: 200, links: [[0, 600]] },
    { area_m2: 300, links: [[0, 901]] },
  ],
}

describe('transit stop details', () => {
  it('calculates direct and route-reach areas from unique 250m cells', () => {
    const details = buildStopDetails(model, 0, { routeReachCellIndexes: [0, 1], directCellIndexes: [0, 1] })
    expect(details.directWalkAreaM2).toBe(300)
    expect(details.routeReachAreaM2).toBe(300)
  })

  it('summarizes directly serving routes with scheduled headways and hourly counts', () => {
    const details = buildStopDetails(model, 0, { routeReachCellIndexes: [], directCellIndexes: [] })
    expect(details.routes).toEqual([
      { index: 0, id: 'r1', shortName: '1', longName: 'One', hasGeometry: true, averageHeadwayMinutes: 10, hourlyCounts: [2, 4, 6, 8] },
      { index: 1, id: 'r2', shortName: '2', longName: 'Two', hasGeometry: true, averageHeadwayMinutes: null, hourlyCounts: [0, 1, 0, 2] },
    ])
  })

  it('uses deterministic route colors and filters only selected route ids', () => {
    expect(routeColor('r1')).toBe(routeColor('r1'))
    expect(routeColor('r1')).not.toBe(routeColor('r2'))
    expect(selectedRouteFilter(['r1', 'r2'])).toEqual(['in', ['get', 'route_id'], ['literal', ['r1', 'r2']]])
  })

  it('sums unique cell areas and ignores duplicate indexes', () => {
    expect(sumCellArea(model.cells, [0, 0, 2])).toBe(400)
  })

  it('formats catchment area in square kilometres', () => {
    expect(formatAreaM2(1_000_000)).toBe('1.00 km²')
    expect(formatAreaM2(62_500)).toBe('0.06 km²')
  })

  it('shows all small-stop routes, total busy-stop service, and isolated selections', () => {
    const routes = Array.from({ length: 9 }, (_, index) => ({
      id: `r${index}`,
      shortName: String(index),
      hourlyCounts: [index, 1],
    }))
    expect(graphSeries(routes.slice(0, 2), new Set(['r0', 'r1']), 2).map(({ id }) => id)).toEqual(['r0', 'r1'])
    expect(graphSeries(routes, new Set(routes.map(({ id }) => id)), 2)).toEqual([
      { id: 'total', label: 'Total scheduled departures', values: [36, 9], color: '#161616' },
    ])
    expect(graphSeries(routes, new Set(['r3']), 2).map(({ id }) => id)).toEqual(['r3'])
  })

  it('provides readable graph ticks for service hours and scheduled departures', () => {
    expect(graphHourTicks([4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24])).toEqual([
      { index: 0, label: '04' },
      { index: 4, label: '08' },
      { index: 8, label: '12' },
      { index: 12, label: '16' },
      { index: 16, label: '20' },
      { index: 20, label: '24' },
    ])
    expect(graphAxisTicks(9)).toEqual([0, 5, 10])
  })
})
