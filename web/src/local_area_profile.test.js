import { describe, expect, it, vi } from 'vitest'

import {
  PROFILE_RADII,
  buildCircleFeature,
  buildChartModel,
  createProfileState,
  normalizeProfileResult,
  updateProfileState,
  createPreviewScheduler,
  buildTpsSelection,
  buildTpsFeatureIndex,
  profileSelectionPresentation,
  resolveTpsSelection,
} from './local_area_profile.js'

describe('local area profile foundation', () => {
  it('supports only the approved catchment radii', () => {
    expect(PROFILE_RADII).toEqual([400, 800, 1200])
    expect(() => buildCircleFeature([72.57, 23.03], 500)).toThrow(/radius/i)
  })

  it('builds a circle feature from the chosen center and radius without map features', () => {
    const circle = buildCircleFeature([72.57, 23.03], 400, 8)
    expect(circle.type).toBe('Feature')
    expect(circle.properties).toEqual({ radiusM: 400 })
    expect(circle.geometry.type).toBe('Polygon')
    expect(circle.geometry.coordinates[0]).toHaveLength(9)
    expect(circle.geometry.coordinates[0][0]).toEqual(circle.geometry.coordinates[0][8])
  })

  it('normalizes every profile section, making missing sections explicit', () => {
    const profile = normalizeProfileResult({
      contractVersion: 'local-area-profile.v1',
      overview: { title: 'Pilot' },
      buildings: null,
    })
    expect(profile.contractVersion).toBe('local-area-profile.v1')
    expect(profile.sections.overview).toEqual({ status: 'available', data: { title: 'Pilot' } })
    expect(profile.sections.buildings).toEqual({ status: 'unavailable', data: null })
    expect(profile.sections.environment).toEqual({ status: 'unavailable', data: null })
  })

  it('keeps profile state explicit during preview, update, and clear', () => {
    const initial = createProfileState()
    expect(initial).toMatchObject({ center: null, radiusM: 400, status: 'empty', requestId: 0 })
    const preview = updateProfileState(initial, { type: 'preview', center: [72.57, 23.03], radiusM: 800 })
    expect(preview).toMatchObject({ center: [72.57, 23.03], radiusM: 800, status: 'preview' })
    const updating = updateProfileState(preview, { type: 'request', requestId: 4 })
    expect(updating).toMatchObject({ status: 'updating', requestId: 4 })
    expect(updateProfileState(updating, { type: 'clear' })).toMatchObject({ center: null, status: 'empty', requestId: 5 })
  })

  it('creates an internal TPS request while presenting only safe human identifiers', () => {
    const feature = { properties: { source_id: 'internal-only', tps_name: null, tps_no: '7', tps_status: 'provisional' }, geometry: { type: 'Polygon', coordinates: [[[72, 23], [73, 23], [73, 24], [72, 24], [72, 23]]] } }
    const selection = buildTpsSelection(feature)
    expect(selection).toMatchObject({ type: 'tps', source_id: 'internal-only', tps_name: null, tps_no: '7', tps_status: 'provisional' })
    const state = updateProfileState(createProfileState(), { type: 'select', selection })
    expect(state).toMatchObject({ center: null, selection, status: 'preview', result: null })
    const presentation = profileSelectionPresentation({ selection: { ...selection, areaM2: 1000 } })
    expect(presentation).toEqual({
      eyebrow: 'TOWN-PLANNING SCHEME PROFILE',
      title: 'TPS number 7',
      metricLabel: 'Selected TPS',
      metricValue: 'TPS name unavailable\nArea 1,000 m²',
    })
    expect(JSON.stringify(presentation)).not.toContain('internal-only')
  })

  it('resolves a rendered TPS fragment to the exact source polygon by internal identity', () => {
    const exact = { type: 'Feature', properties: { source_id: 'internal-9', tps_name: 'Exact scheme', tps_no: 'TPS-9' }, geometry: { type: 'Polygon', coordinates: [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]] } }
    const renderedFragment = { type: 'Feature', properties: { source_id: 'internal-9', tps_name: 'Exact scheme', tps_no: 'TPS-9' }, geometry: { type: 'Polygon', coordinates: [[[0, 0], [5, 0], [5, 5], [0, 5], [0, 0]]] } }

    const selection = resolveTpsSelection(renderedFragment, buildTpsFeatureIndex({ type: 'FeatureCollection', features: [exact] }))

    expect(selection.geometry).toEqual(exact.geometry)
    expect(selection.geometry).not.toEqual(renderedFragment.geometry)
  })

  it('creates chart models from fixed bins with a method subtitle', () => {
    const chart = buildChartModel({
      title: 'Building area',
      method: 'Centroid-selected buildings',
      bins: [{ label: '0–100 m²', value: 3 }, { label: '100–250 m²', value: 7 }],
    })
    expect(chart).toEqual({
      title: 'Building area',
      subtitle: 'Centroid-selected buildings',
      bins: [{ label: '0–100 m²', value: 3 }, { label: '100–250 m²', value: 7 }],
    })
  })

  it('debounces previews and invalidates stale requests', async () => {
    vi.useFakeTimers()
    const preview = vi.fn()
    const scheduler = createPreviewScheduler(preview, 100)
    scheduler.schedule({ center: [1, 2], radiusM: 400 })
    scheduler.schedule({ center: [3, 4], radiusM: 800 })
    vi.advanceTimersByTime(99)
    expect(preview).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1)
    expect(preview).toHaveBeenCalledTimes(1)
    expect(preview).toHaveBeenLastCalledWith({ center: [3, 4], radiusM: 800 })
    const first = scheduler.nextRequestId()
    const second = scheduler.nextRequestId()
    expect(scheduler.isCurrent(second)).toBe(true)
    expect(scheduler.isCurrent(first)).toBe(false)
    vi.useRealTimers()
  })
})
