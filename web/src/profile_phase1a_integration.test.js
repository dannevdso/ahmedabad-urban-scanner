import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'

const main = readFileSync(new URL('./main.js', import.meta.url), 'utf8')
const styles = readFileSync(new URL('./styles.css', import.meta.url), 'utf8')

describe('Local Area Profile Phase 1A inspector integration', () => {
  it('uses section-specific presentation models for buildings, streets, and environment', () => {
    expect(main).toContain("from './profile_presentations.js'")
    expect(main).toContain('buildBuildingsPresentation')
    expect(main).toContain('buildStreetsPresentation')
    expect(main).toContain('buildEnvironmentPresentation')
    expect(main).toContain('renderProfilePresentation')
  })

  it('uses the imported overlay category helper when rendering controls', () => {
    expect(main).toContain('const category = overlayControlCategory(overlay)')
  })

  it('renders distributions as accessible vertical columns rather than horizontal bars', () => {
    expect(main).toContain("figure.className = 'profile-column-chart'")
    expect(main).toContain("columns.className = 'profile-chart-columns'")
    expect(main).toContain("figure.setAttribute('aria-labelledby'")
    expect(main).toContain("data.className = 'profile-chart-data'")
    expect(main).toContain("mark.setAttribute('aria-hidden', 'true')")
    expect(styles).toMatch(/\.profile-chart-columns\s*\{[^}]*display:\s*grid/s)
    expect(styles).toMatch(/\.profile-chart-column\s+i\s*\{[^}]*height:\s*var\(--column-height\)/s)
  })

  it('renders categorical SUHI counts without sending them through a numeric histogram axis', () => {
    expect(main).toContain("chart.type === 'categorical-counts'")
    expect(main).toContain('Categorical class counts')
    expect(main).toContain('renderProfileCategoricalDetailTable')
    expect(main).toMatch(/function renderCategoricalCountChart\(chart\) \{[\s\S]*const \{ type: _ignoredType, categories = \[\], \.\.\.columnChart \} = chart[\s\S]*return renderProfileColumnChart\(\{[\s\S]*\.\.\.columnChart,/)
  })

  it('gives dense temperature histograms readable scrollable columns', () => {
    expect(main).toContain("columns.classList.toggle('profile-chart-columns-dense', chart.bins.length > 8)")
    expect(styles).toMatch(/\.profile-chart-columns-dense\s*\{[^}]*grid-auto-columns:\s*36px[^}]*overflow-x:\s*auto/s)
  })

  it('provides table styling for building-form detail rows', () => {
    expect(main).toContain("table.className = 'profile-detail-table'")
    expect(styles).toMatch(/\.profile-detail-table\s*\{[^}]*border-collapse:\s*collapse/s)
    expect(main).toContain("caption.textContent = 'Building-form summary statistics'")
    expect(main).toContain("heading.scope = 'col'")
  })

  it('shows explicit unavailable presentation states and resets refreshed profiles to the header', () => {
    expect(main).toContain("message.className = 'profile-unavailable-state'")
    expect(main).toContain('elements.inspector.scrollTop = 0')
  })

  it('renders only the Phase 1B profile sections and uses the renamed parks and schools label', () => {
    expect(main).toContain('buildSpaceSyntaxPresentation')
    expect(main).toContain('buildPublicTransportPresentation')
    expect(main).toContain('buildParksSchoolsPresentation')
    expect(main).toContain("parksEducation: 'Parks and schools'")
    expect(main).not.toContain("availability: 'Availability'")
    expect(main).not.toContain("methods: 'Methods'")
  })

  it('renders Phase 1B tables with semantic captions and scopes', () => {
    expect(main).toContain("renderProfilePresentationTables(model, 'Space syntax / centrality metrics')")
    expect(main).toContain("group.caption ?? group.label ?? 'Public transport reach'")
    expect(main).toContain("renderProfilePresentationTables(model, 'Parks and schools')")
    expect(main).toContain("heading.scope = 'col'")
    expect(main).toContain("cell.scope = 'row'")
  })

  it('styles Phase 1B grouped tables and transport caveats', () => {
    expect(styles).toMatch(/\.profile-grouped-table\s*\{[^}]*border-collapse:\s*collapse/s)
    expect(styles).toMatch(/\.profile-caveat\s*\{[^}]*background:\s*var\(--gray-10\)/s)
  })
})
