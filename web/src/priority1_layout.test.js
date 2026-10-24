import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'

const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8')
const styles = readFileSync(new URL('./styles.css', import.meta.url), 'utf8')
const main = readFileSync(new URL('./main.js', import.meta.url), 'utf8')

describe('priority 1 map layout', () => {
  it('provides a desktop sidebar collapse control without resizing or recentering the map', () => {
    expect(html).toMatch(/id="sidebar-collapse"/)
    expect(styles).toMatch(/\.workspace\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)/s)
    expect(styles).toMatch(/\.sidebar\s*\{[^}]*position:\s*absolute/s)
    expect(styles).toMatch(/\.sidebar\.collapsed\s*\{[^}]*translateX\(-100%\)/s)

    const toggleSidebar = main.match(/function toggleSidebar\(force\)\s*\{([\s\S]*?)\n\}/)?.[1] ?? ''
    expect(toggleSidebar).not.toMatch(/resize|fitBounds|easeTo|jumpTo|setCenter/)
  })

  it('aligns a narrow legend rail to the summary card and integrates the info control', () => {
    expect(html).toMatch(/class="legend-panel-header"[\s\S]*id="legend-info-button"[\s\S]*id="legend"/)
    expect(styles).toMatch(/--map-rail-width:\s*168px/)
    expect(styles).toMatch(/\.summary-tile\s*\{[^}]*width:\s*var\(--map-rail-width\)/s)
    expect(styles).toMatch(/\.legend-wrap\s*\{[^}]*right:\s*16px[^}]*width:\s*var\(--map-rail-width\)/s)
    expect(styles).toMatch(/\.legend-scale\s*\{[^}]*grid-auto-flow:\s*row/s)
  })

  it('keeps the map title concise and stops positioning controls from legend height', () => {
    expect(html).toContain('<h2 id="indicator-title">Building footprints</h2>')
    expect(main).not.toContain('elements.planxActiveSummary.style.bottom')
    expect(main).not.toContain('elements.resetView.style.bottom')
  })
})
