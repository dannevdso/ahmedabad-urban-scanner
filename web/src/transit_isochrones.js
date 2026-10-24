const EMPTY_COLLECTION = Object.freeze({ type: 'FeatureCollection', features: [] })

function featureCollection(features) {
  return { type: 'FeatureCollection', features }
}

function sortedIndexes(values) {
  return [...values].sort((left, right) => left - right)
}

function cellArea(cells, indexes) {
  return [...new Set(indexes)].reduce((total, index) => total + Number(cells[index]?.area_m2 ?? 0), 0)
}

export function buildRouteReachCatchment(model, originIndex) {
  if (!model?.stops?.[originIndex]) {
    return {
      seedStopIndexes: [],
      routeIndexes: [],
      routeStopIndexes: [],
      minutes15: EMPTY_COLLECTION,
      directMinutes15: EMPTY_COLLECTION,
      routeStops: EMPTY_COLLECTION,
      directCellIndexes: [],
      routeReachCellIndexes: [],
      directAreaM2: 0,
      routeReachAreaM2: 0,
    }
  }

  const seedStopIndexes = new Set([originIndex])
  for (const [from, to, seconds] of model.footpaths ?? []) {
    if (from === originIndex && seconds <= model.nearby_stop_seconds) seedStopIndexes.add(to)
  }

  const routeIndexes = new Set()
  for (const stopIndex of seedStopIndexes) {
    for (const routeIndex of model.stop_routes?.[stopIndex] ?? []) routeIndexes.add(routeIndex)
  }

  const routeStopIndexes = new Set()
  for (const routeIndex of routeIndexes) {
    for (const stopIndex of model.route_stops?.[routeIndex] ?? []) routeStopIndexes.add(stopIndex)
  }

  const catchmentFeatures = []
  const directCatchmentFeatures = []
  const directCellIndexes = []
  const routeReachCellIndexes = []
  for (const cell of model.cells ?? []) {
    const reachableLinks = cell.links.filter(([stopIndex, seconds]) => (
      routeStopIndexes.has(stopIndex) && seconds <= model.catchment_seconds
    ))
    const directLinks = cell.links.filter(([stopIndex, seconds]) => stopIndex === originIndex && seconds <= model.catchment_seconds)
    if (reachableLinks.length) {
      const walkSeconds = Math.min(...reachableLinks.map(([, seconds]) => seconds))
      routeReachCellIndexes.push(model.cells.indexOf(cell))
      catchmentFeatures.push({
        type: 'Feature',
        properties: {
          walk_time_minutes: Math.round(walkSeconds / 6) / 10,
          reachable_route_stop_count: reachableLinks.length,
        },
        geometry: cell.geometry,
      })
    }
    if (directLinks.length) {
      const walkSeconds = Math.min(...directLinks.map(([, seconds]) => seconds))
      directCellIndexes.push(model.cells.indexOf(cell))
      directCatchmentFeatures.push({
      type: 'Feature',
      properties: {
        walk_time_minutes: Math.round(walkSeconds / 6) / 10,
        reachable_route_stop_count: 1,
      },
      geometry: cell.geometry,
      })
    }
  }

  const routeStopFeatures = sortedIndexes(routeStopIndexes).map((stopIndex) => {
    const stop = model.stops[stopIndex]
    return {
      type: 'Feature',
      properties: {
        stop_id: String(stop.id),
        stop_name: stop.name,
        seed_stop: seedStopIndexes.has(stopIndex),
      },
      geometry: { type: 'Point', coordinates: [stop.lon, stop.lat] },
    }
  })

  return {
    seedStopIndexes: sortedIndexes(seedStopIndexes),
    routeIndexes: sortedIndexes(routeIndexes),
    routeStopIndexes: sortedIndexes(routeStopIndexes),
    minutes15: featureCollection(catchmentFeatures),
    directMinutes15: featureCollection(directCatchmentFeatures),
    routeStops: featureCollection(routeStopFeatures),
    directCellIndexes: sortedIndexes(directCellIndexes),
    routeReachCellIndexes: sortedIndexes(routeReachCellIndexes),
    directAreaM2: cellArea(model.cells ?? [], directCellIndexes),
    routeReachAreaM2: cellArea(model.cells ?? [], routeReachCellIndexes),
  }
}
