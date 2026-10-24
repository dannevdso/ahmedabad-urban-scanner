const ROUTE_PALETTE = ['#0f62fe', '#8a3ffc', '#d12771', '#198038', '#b28600', '#005d5d', '#a2191f', '#6929c4', '#1192e8', '#fa4d56', '#009d9a', '#ee538b']

export function sumCellArea(cells, indexes) {
  return [...new Set(indexes)].reduce((total, index) => total + Number(cells[index]?.area_m2 ?? 0), 0)
}

export function routeColor(routeId) {
  let hash = 0
  for (const character of String(routeId)) hash = ((hash << 5) - hash + character.charCodeAt(0)) | 0
  return ROUTE_PALETTE[Math.abs(hash) % ROUTE_PALETTE.length]
}

export function selectedRouteFilter(routeIds) {
  if (!routeIds.length) return ['==', ['get', 'route_id'], '__no_selected_route__']
  return ['in', ['get', 'route_id'], ['literal', routeIds]]
}

export function buildStopDetails(model, originIndex, catchment = {}) {
  const stop = model.stops?.[originIndex] ?? {}
  const service = model.stop_route_service?.[originIndex] ?? []
  const routes = service.map(([routeIndex, averageHeadwayMinutes, hourlyCounts = []]) => {
    const route = model.routes?.[routeIndex] ?? model.route_ids?.[routeIndex] ?? {}
    return {
      index: routeIndex,
      id: String(route.id ?? model.route_ids?.[routeIndex] ?? routeIndex),
      shortName: route.short_name ?? route.shortName ?? String(route.id ?? routeIndex),
      longName: route.long_name ?? route.longName ?? '',
      hasGeometry: route.has_geometry ?? route.geometry_available ?? true,
      averageHeadwayMinutes: averageHeadwayMinutes == null ? null : Number(averageHeadwayMinutes),
      hourlyCounts: hourlyCounts.map(Number),
    }
  })
  return {
    stopId: String(stop.id ?? ''),
    stopName: stop.name ?? stop.stop_name ?? String(stop.id ?? 'Selected stop'),
    directRouteCount: routes.length,
    routes,
    directWalkAreaM2: sumCellArea(model.cells ?? [], catchment.directCellIndexes ?? []),
    routeReachAreaM2: sumCellArea(model.cells ?? [], catchment.routeReachCellIndexes ?? []),
    serviceHours: model.service_hours ?? [],
  }
}

export function formatAreaM2(value) {
  return `${((Number(value) || 0) / 1_000_000).toFixed(2)} km²`
}

export function hourlyTotals(routes, hourCount) {
  return Array.from({ length: hourCount }, (_, hour) => routes.reduce((total, route) => total + Number(route.hourlyCounts[hour] ?? 0), 0))
}

export function graphSeries(routes, selectedRouteIds, hourCount) {
  const selected = routes.filter(({ id }) => selectedRouteIds.has(id))
  if (routes.length > 8 && selected.length === routes.length) {
    return [{ id: 'total', label: 'Total scheduled departures', values: hourlyTotals(routes, hourCount), color: '#161616' }]
  }
  return selected.map((route) => ({
    id: route.id,
    label: route.shortName,
    values: route.hourlyCounts,
    color: routeColor(route.id),
  }))
}

export function graphHourTicks(hours) {
  if (!hours.length) return []
  return hours
    .map((hour, index) => ({ hour: Number(hour), index }))
    .filter(({ hour, index }) => index === 0 || index === hours.length - 1 || hour % 4 === 0)
    .map(({ hour, index }) => ({ index, label: String(hour).padStart(2, '0') }))
}

export function graphAxisTicks(maximum) {
  const max = Math.max(1, Number(maximum) || 0)
  if (max <= 1) return [0, 1]
  const magnitude = 10 ** Math.floor(Math.log10(max / 2))
  const rawStep = max / 2 / magnitude
  const factor = rawStep <= 1 ? 1 : rawStep <= 2 ? 2 : rawStep <= 5 ? 5 : 10
  const step = factor * magnitude
  return [0, step, step * 2]
}
