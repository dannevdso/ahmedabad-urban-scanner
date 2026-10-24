import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'

import { PLANX_OVERLAYS, SPACE_SYNTAX_FIELDS } from './planx_layers.js'
import { indicators } from './indicators.js'
import {
  buildLegendState,
  legendSwatchBackground,
  resetButtonBottom,
  legendHelpText,
  renderLegend,
  renderLegendHelp,
} from './legends.js'

const metadata = {
  contexts: {
    'full-study-current': { scopeLabel: 'Full-study current', statusLabel: 'Current study', temporalLabel: '2026', caveat: 'Current caveat.' },
    'current-study-bounded': { scopeLabel: 'Current-study bounded', statusLabel: 'Subset', temporalLabel: '2026', caveat: 'Bounded caveat.' },
    'contextual-gtfs': { scopeLabel: 'Contextual GTFS', statusLabel: 'Supplied feed', temporalLabel: 'Unknown', caveat: 'Feed caveat.' },
    'supplied-external': { scopeLabel: 'Supplied external', statusLabel: 'Not rerun', temporalLabel: 'Unknown', caveat: 'External caveat.' },
  },
  building_properties: ['footprint_area_m2'],
  overlay_legends: {
    centrality: { key: 'centrality', title: 'Network centrality (full prepared network)', kind: 'classification', geometry: 'line', renderer_property: 'betweenness', context_key: 'full-study-current', entries: [{ label: '0–<10', color: '#111111' }, { label: '10+', color: '#eeeeee' }], caveat: '135,115 analysed edges.' },
    heatRisk: { key: 'heatRisk', title: 'Heat-risk morphology proxy', kind: 'classification', geometry: 'fill', renderer_property: 'heat_risk', context_key: 'current-study-proxy', entries: [{ label: '38.54–<60', color: '#ffffcc' }, { label: '60–100', color: '#800026' }], caveat: 'Not observed heat.' },


    shadowCasting: { key: 'shadowCasting', title: 'Shadow casting', kind: 'binary-raster', geometry: 'raster', context_key: 'current-study-bounded', unit: '0/1', unit_status: 'verified', validation_status: 'unverified', entries: [{ label: '0 (not shadowed)', color: 'transparent' }, { label: '1 (shadowed)', color: '#1e1e1e' }], caveat: 'Unverified height warning.' },
    solarIrradiation: { key: 'solarIrradiation', title: 'Solar irradiation', kind: 'continuous-raster', geometry: 'raster', context_key: 'current-study-bounded', unit: '', unit_status: 'not_documented', entries: [{ label: '4–8.1', color: '#000000' }], caveat: 'Solar unit not documented.' },
    'poi-parks': { key: 'poi-parks', title: 'Parks', kind: 'single-symbol', geometry: 'circle', context_key: 'contextual-gtfs', entries: [{ label: 'Parks', color: '#15803d', shape: 'circle' }], caveat: 'Symbol only.' },
    spaceSyntax: { off: { key: 'off', title: 'Off', kind: 'off', geometry: 'none', context_key: 'supplied-external', entries: [] }, closeness: { key: 'closeness', title: 'Mean closeness', kind: 'classification', geometry: 'line', renderer_property: 'closeness', context_key: 'supplied-external', entries: [{ label: '0–1', color: '#111111' }], caveat: 'Exact metadata.' } },
  },
}

function active(keys = []) { return new Set(keys) }

describe('legend model', () => {
  it('uses the selected building indicator when all overlays are off', () => {
    const state = buildLegendState({ activeIndicatorKey: 'buildingArea', activePlanxOverlays: active(), spaceSyntaxKey: 'off', metadata, planxOverlays: PLANX_OVERLAYS })
    expect(state.sections).toHaveLength(1)
    expect(state.sections[0].source).toBe('building')
    expect(state.sections[0].title).toBe(indicators.buildingArea.shortLabel)
  })

  it('suppresses the building legend for one active overlay', () => {
    const state = buildLegendState({ activeIndicatorKey: 'buildingArea', activePlanxOverlays: active(['centrality']), spaceSyntaxKey: 'off', metadata, planxOverlays: PLANX_OVERLAYS })
    expect(state.sections.map((section) => section.key)).toEqual(['centrality'])
  })

  it('recolors requested transit and TPS legend swatches without altering unrelated palettes', () => {
    const transitMetadata = { ...metadata, overlay_legends: { ...metadata.overlay_legends, transitIsochrones: { key: 'transitIsochrones', geometry: 'fill', entries: [{ label: 'catchment', color: '#2563eb' }, { label: 'route stop', color: '#7c3aed', shape: 'circle' }, { label: 'seed', color: '#f59e0b', shape: 'circle' }] } } }
    const transit = buildLegendState({ activeIndicatorKey: 'buildingArea', activePlanxOverlays: active(['transitIsochrones']), spaceSyntaxKey: 'off', metadata: transitMetadata, planxOverlays: PLANX_OVERLAYS })
    expect(transit.sections[0].entries.map(({ color }) => color)).toEqual(['#94412f', 'rgba(148, 65, 47, 0)', '#f59e0b'])
    const tps = buildLegendState({ activeIndicatorKey: 'buildingArea', activePlanxOverlays: active(['tpsProvisional']), spaceSyntaxKey: 'off', metadata, planxOverlays: PLANX_OVERLAYS })
    expect(tps.sections[0].entries[0].color).toBe('#94412f')
    const heat = buildLegendState({ activeIndicatorKey: 'buildingArea', activePlanxOverlays: active(['heatRisk']), spaceSyntaxKey: 'off', metadata, planxOverlays: PLANX_OVERLAYS })
    expect(heat.sections[0].entries.map(({ color }) => color)).toContain('#800026')
  })

  it('renders multiple active overlays in declaration order', () => {
    const state = buildLegendState({ activeIndicatorKey: 'buildingArea', activePlanxOverlays: active(['poi-parks', 'centrality', 'heatRisk']), spaceSyntaxKey: 'off', metadata, planxOverlays: PLANX_OVERLAYS })
    expect(state.sections.map((section) => section.key)).toEqual(['centrality', 'heatRisk', 'poi-parks'])
  })

  it('puts selected space syntax before PlanX overlays and off contributes no section', () => {
    const activeState = buildLegendState({ activeIndicatorKey: 'buildingArea', activePlanxOverlays: active(['centrality']), spaceSyntaxKey: 'closeness', metadata, planxOverlays: PLANX_OVERLAYS })
    expect(activeState.sections.map((section) => section.key)).toEqual(['closeness', 'centrality'])
    const offState = buildLegendState({ activeIndicatorKey: 'buildingArea', activePlanxOverlays: active(['centrality']), spaceSyntaxKey: 'off', metadata, planxOverlays: PLANX_OVERLAYS })
    expect(offState.sections.map((section) => section.key)).toEqual(['centrality'])
  })

  it('places the selected space-syntax explanation with its visible legend', () => {
    const state = buildLegendState({ activeIndicatorKey: null, activePlanxOverlays: active(), spaceSyntaxKey: 'connectivity', metadata, planxOverlays: PLANX_OVERLAYS })
    expect(state.sections[0].description).toMatch(/directly connected.*Higher is generally better for accessibility/i)
    expect(renderLegend.toString()).toContain('section.description')
    expect(renderLegend.toString()).toContain('legend-section-description')
  })

  it('keeps scope caveats visible in high-risk legends', () => {
    const state = buildLegendState({ activeIndicatorKey: 'buildingArea', activePlanxOverlays: active(['centrality', 'heatRisk']), spaceSyntaxKey: 'off', metadata, planxOverlays: PLANX_OVERLAYS })
    expect(state.sections.find((section) => section.key === 'centrality').caveat).toContain('135,115 analysed edges')
    expect(state.sections.find((section) => section.key === 'heatRisk').caveat.toLowerCase()).toContain('not observed heat')
    expect(state.sections.find((section) => section.key === 'heatRisk').rendererProperty).toBe('heat_risk')
  })

  it('supports numeric heat-risk legends', () => {
    const state = buildLegendState({ activeIndicatorKey: 'buildingArea', activePlanxOverlays: active(['heatRisk']), spaceSyntaxKey: 'off', metadata, planxOverlays: PLANX_OVERLAYS })
    expect(state.sections.map((section) => section.key)).toEqual(['heatRisk'])
    expect(state.sections[0].kind).toBe('classification')
    expect(state.sections[0].entries.map(({ color }) => color)).toContain('#800026')
  })

  it('renders continuous raster palette stops as a gradient rather than a no-data swatch', () => {
    const entry = {
      palette_stops: [
        { value: 0, color: '#000000' },
        { value: 0.5, color: '#777777' },
        { value: 1, color: '#ffffff' },
      ],
    }
    expect(legendSwatchBackground(entry)).toBe('linear-gradient(to right, #000000 0%, #777777 50%, #ffffff 100%)')
  })

  it('keeps modelled building-height provenance and metres visible in the legend', () => {
    const state = buildLegendState({
      activeIndicatorKey: 'buildingArea',
      activePlanxOverlays: active(['buildingHeight']),
      spaceSyntaxKey: 'off',
      metadata: {
        contexts: { 'modelled-building-height': { scopeLabel: 'Full-study modelled raster', statusLabel: 'Modelled proxy', temporalLabel: '2023 annual slice' } },
        overlay_legends: {
          buildingHeight: {
            key: 'buildingHeight', title: '2023 modelled building height', kind: 'continuous-raster', geometry: 'raster',
            context_key: 'modelled-building-height', unit: 'metres', entries: [{ label: '0.023–92.319 metres', palette_stops: [{ value: 0, color: '#440154' }, { value: 1, color: '#fde725' }] }],
            caveat: 'Google Research Open Buildings Temporal; modelled, not surveyed height; 2023; 30 m pixels; presence threshold 0.2.',
          },
        },
      },
      planxOverlays: [{ key: 'buildingHeight' }],
    })
    expect(state.sections[0].unit).toBe('metres')
    expect(state.sections[0].caveat).toContain('not surveyed')
    expect(legendSwatchBackground(state.sections[0].entries[0])).toContain('linear-gradient')
  })

  it('moves the reset control above the legend at mobile widths', () => {
    expect(resetButtonBottom(390, 270)).toBe('312px')
    expect(resetButtonBottom(1280, 270)).toBe('')
  })

  it('uses a defined opaque background token for legend help', () => {
    const styles = readFileSync(new URL('./styles.css', import.meta.url), 'utf8')
    expect(styles).not.toContain('var(--paper)')
    expect(styles).toMatch(/\.legend-help[^}]*background:\s*var\(--white\)/s)
  })

  it('falls back safely when metadata is missing and restores the building legend all-off', () => {
    const missing = buildLegendState({ activeIndicatorKey: 'buildingArea', activePlanxOverlays: active(['unknown']), spaceSyntaxKey: 'off', metadata: {}, planxOverlays: PLANX_OVERLAYS })
    expect(missing.sections).toHaveLength(1)
    expect(missing.sections[0].source).toBe('building')
    const restored = buildLegendState({ activeIndicatorKey: 'buildingArea', activePlanxOverlays: active(), spaceSyntaxKey: 'off', metadata, planxOverlays: PLANX_OVERLAYS })
    expect(restored.sections[0].source).toBe('building')
  })

  it('exposes a safe DOM rendering path with text content, not unsafe HTML', () => {
    const state = buildLegendState({ activeIndicatorKey: 'buildingArea', activePlanxOverlays: active(), spaceSyntaxKey: 'off', metadata, planxOverlays: PLANX_OVERLAYS })
    expect(renderLegend.toString()).not.toContain('innerHTML')
    expect(renderLegendHelp.toString()).not.toContain('innerHTML')
    expect(legendHelpText(state)).toContain('full-study-current')
  })

  it('resolves every PlanX overlay and space-syntax selector to a renderable record or off', () => {
    for (const overlay of PLANX_OVERLAYS) {
      const state = buildLegendState({ activeIndicatorKey: 'buildingArea', activePlanxOverlays: active([overlay.key]), spaceSyntaxKey: 'off', metadata, planxOverlays: PLANX_OVERLAYS })
      expect(state.sections).toHaveLength(1)
      expect(state.sections[0].kind).not.toBe('off')
    }
    for (const [key] of SPACE_SYNTAX_FIELDS) {
      const state = buildLegendState({ activeIndicatorKey: 'buildingArea', activePlanxOverlays: active(), spaceSyntaxKey: key, metadata, planxOverlays: PLANX_OVERLAYS })
      expect(state.sections.length).toBe(key === 'off' ? 1 : 1)
      if (key !== 'off') expect(state.sections[0].kind).not.toBe('off')
    }
  })
})
