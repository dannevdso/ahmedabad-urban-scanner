import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

import { indicators } from './indicators.js'
import { PLANX_OVERLAYS } from './planx_layers.js'
import { baseControlDescriptions, indicatorSidebarDescription, overlaySidebarDescription, spaceSyntaxSidebarDescription } from './sidebar_descriptions.js'

const VERBOSE_CONTEXT = /full[- ]study|current[- ]study|supplied|unverified|2026|source|snapshot|not rerun|not observed|analysed edges|classification|caveat/i
const main = readFileSync(new URL('./main.js', import.meta.url), 'utf8')

describe('sidebar descriptions', () => {
  it('uses concise indicator explanations without provenance context', () => {
    for (const [key, indicator] of Object.entries(indicators)) {
      const description = indicatorSidebarDescription(key, indicator)
      expect(description.length).toBeLessThanOrEqual(90)
      expect(description).not.toMatch(VERBOSE_CONTEXT)
      expect(description).not.toBe(indicator.context)
    }
  })

  it('uses concise overlay explanations for analytical, raster, and POI controls', () => {
    for (const overlay of PLANX_OVERLAYS) {
      const description = overlaySidebarDescription(overlay)
      expect(description.length).toBeLessThanOrEqual(90)
      expect(description).not.toMatch(VERBOSE_CONTEXT)
      expect(description).not.toBe(overlay.description)
    }
  })

  it('describes building height as a modelled raster, not surveyed footprint data', () => {
    expect(overlaySidebarDescription({ key: 'buildingHeight', label: '2023 modelled building height' })).toBe('Modelled 2023 height: 30 m overview, ~4 m effective detail when zoomed in.')
  })

  it('labels the supplied flood layer as VEDAS context rather than unverified scope', () => {
    expect(main).toContain("'contextual-vedas': 'VEDAS context'")
    expect(main).toContain("if (!activePlanxOverlays.has('floodRiskZones') && inspectorMode === 'floodRisk') closeInspector()")
  })

  it('provides plain descriptions for base toggles and the space-syntax selector', () => {
    expect(baseControlDescriptions.buildings).toMatch(/building footprints/i)
    expect(baseControlDescriptions.basemap).toMatch(/streets|background map/i)
    expect(baseControlDescriptions.buildings).not.toMatch(VERBOSE_CONTEXT)
    expect(baseControlDescriptions.basemap).not.toMatch(VERBOSE_CONTEXT)
    expect(spaceSyntaxSidebarDescription('off')).toMatch(/network measure/i)
    expect(spaceSyntaxSidebarDescription('off')).not.toMatch(VERBOSE_CONTEXT)
  })

  it('explains each supplied space-syntax measure and its map interpretation', () => {
    expect(spaceSyntaxSidebarDescription('connectivity')).toMatch(/directly connected.*Higher is generally better for accessibility/i)
    expect(spaceSyntaxSidebarDescription('betweenness')).toMatch(/shortest network paths.*movement potential/i)
    expect(spaceSyntaxSidebarDescription('straightness')).toMatch(/straight-line distance.*Higher is generally better for accessibility/i)
    expect(spaceSyntaxSidebarDescription('nc_400')).toMatch(/reachable within the specified analysis radius.*Higher is generally better for accessibility/i)
    expect(spaceSyntaxSidebarDescription('nc_2500')).toBe(spaceSyntaxSidebarDescription('nc_400'))
    expect(spaceSyntaxSidebarDescription('ch_400')).toMatch(/least-angular-change routes.*movement potential/i)
    expect(spaceSyntaxSidebarDescription('ch_2500')).toBe(spaceSyntaxSidebarDescription('ch_400'))
    expect(spaceSyntaxSidebarDescription('md_400')).toMatch(/Average angular cost.*Lower indicates greater integration/i)
    expect(spaceSyntaxSidebarDescription('md_2500')).toBe(spaceSyntaxSidebarDescription('md_400'))
    expect(spaceSyntaxSidebarDescription('td_400')).toMatch(/Sum of angular costs.*compare cautiously/i)
    expect(spaceSyntaxSidebarDescription('td_2500')).toBe(spaceSyntaxSidebarDescription('td_400'))
  })
})