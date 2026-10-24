import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'

const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8')
const styles = readFileSync(new URL('./styles.css', import.meta.url), 'utf8')
const main = readFileSync(new URL('./main.js', import.meta.url), 'utf8')

describe('priority 4 accessibility and mobile interaction', () => {
  it('keeps the closed inspector inert and non-interactive', () => {
    expect(html).toMatch(/id="inspector"[^>]*aria-hidden="true"[^>]*inert/)
    expect(styles).toMatch(/\.inspector\s*\{[^}]*pointer-events:\s*none/s)
    expect(styles).toMatch(/\.inspector\.open\s*\{[^}]*pointer-events:\s*auto/s)
    expect(main).toContain('elements.inspector.inert = false')
    expect(main).toContain('elements.inspector.inert = true')
  })

  it('uses a dismissible mobile sidebar with focus restoration', () => {
    expect(html).toMatch(/id="sidebar-scrim"/)
    expect(main).toContain("event.key === 'Escape'")
    expect(main).toContain('elements.menuToggle.focus()')
    expect(main).toContain('elements.sidebar.focus()')
    expect(styles).toMatch(/\.sidebar-scrim/)
  })

  it('does not declare the map as an application or announce whole legends on every update', () => {
    expect(html).not.toContain('role="application"')
    expect(html).not.toMatch(/id="legend"[^>]*aria-live/)
    expect(html).not.toMatch(/class="summary-tile"[^>]*aria-live/)
  })
})
