export const BUILDING_HEIGHT_FINE_MIN_ZOOM = 8
export const BUILDING_HEIGHT_FINE_MAX_ZOOM = 22
export const BUILDING_HEIGHT_TILE_ZOOMS = [8, 11, 14, 16]

const BUILDING_HEIGHT_COORDINATES = [
  [72.4109191373896, 23.263714341096108],
  [72.73796268185004, 23.268770122568007],
  [72.74379212245495, 22.920265285330075],
  [72.41758925179329, 22.915293725211118],
]

export const buildingHeightSources = {
  overview: {
    type: 'image',
    url: './data/building-height-2023.png',
    coordinates: BUILDING_HEIGHT_COORDINATES,
  },
  fine: BUILDING_HEIGHT_TILE_ZOOMS.map((zoom) => ({
    type: 'raster',
    tiles: ['./data/building-height-fine/{z}/{x}/{y}.webp'],
    tileSize: 256,
    minzoom: zoom,
    maxzoom: zoom,
  })),
}

export const buildingHeightLayers = {
  overview: {
    id: 'building-height-2023-raster-overview',
    type: 'raster',
    source: 'planx-buildingHeightOverview',
    maxzoom: BUILDING_HEIGHT_FINE_MIN_ZOOM,
    layout: { visibility: 'none' },
    paint: { 'raster-opacity': 0.7 },
  },
  fine: BUILDING_HEIGHT_TILE_ZOOMS.map((zoom, index) => ({
    id: `building-height-2023-raster-fine-${zoom}`,
    type: 'raster',
    source: `planx-buildingHeightFine${zoom}`,
    minzoom: zoom,
    maxzoom: BUILDING_HEIGHT_TILE_ZOOMS[index + 1] ?? BUILDING_HEIGHT_FINE_MAX_ZOOM,
    layout: { visibility: 'none' },
    paint: { 'raster-opacity': 0.7 },
  })),
}
