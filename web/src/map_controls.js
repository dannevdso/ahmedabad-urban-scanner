export function captureLayerVisibility(layers = []) {
  return layers.map((layer) => [layer.id, layer.layout?.visibility ?? 'visible'])
}

export function layerVisibilityUpdates(originalVisibility, visible) {
  return originalVisibility.map(([layerId, visibility]) => [
    layerId,
    visible ? visibility : 'none',
  ])
}

export function isRoadLayer(layer = {}) {
  const sourceLayer = layer['source-layer'] ?? layer.sourceLayer ?? ''
  if (!['transportation', 'transportation_name'].includes(sourceLayer)) return false
  return /^(road_|highway[-_]|tunnel_|bridge_)/.test(layer.id ?? '') && !/(rail|transit)/.test(layer.id ?? '')
}

export function captureBaseLayerVisibility(layers = []) {
  return layers.map((layer) => ({
    id: layer.id,
    sourceLayer: layer['source-layer'] ?? '',
    visibility: layer.layout?.visibility ?? 'visible',
  }))
}

export function baseLayerVisibilityUpdates(originalVisibility, { backgroundVisible, roadsVisible }) {
  return originalVisibility.map((layer) => {
    const visible = isRoadLayer(layer) ? roadsVisible : backgroundVisible
    return [layer.id, visible ? layer.visibility : 'none']
  })
}
