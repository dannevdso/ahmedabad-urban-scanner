import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

describe('sidebar layout', () => {
  it('places transit and Local Area Profile before the consolidated Map layers controls', () => {
    const html = readFileSync(fileURLToPath(new URL('../index.html', import.meta.url)), 'utf8')
    expect(html.indexOf('featured-transit-controls')).toBeGreaterThan(-1)
    expect(html.indexOf('featured-transit-controls')).toBeLessThan(html.indexOf('local-profile-controls'))
    expect(html.indexOf('local-profile-controls')).toBeLessThan(html.indexOf('planx-controls-title'))
    expect(html.indexOf('planx-controls-title')).toBeLessThan(html.indexOf('indicator-groups'))
    expect(html).toContain('Catchment opacity')
    expect(html).toMatch(/Other route-stop opacity[\s\S]*id="route-stop-opacity-control"[^>]*min="10"[^>]*max="100"[^>]*value="60"/)
  })

  it('places the provisional TPS control immediately below Local Area Profile and outside Experimental', () => {
    const html = readFileSync(fileURLToPath(new URL('../index.html', import.meta.url)), 'utf8')
    expect(html.indexOf('id="tps-provisional-control"')).toBeGreaterThan(html.indexOf('class="local-profile-controls"'))
    expect(html.indexOf('id="tps-provisional-control"')).toBeLessThan(html.indexOf('id="planx-controls-title"'))
    expect(html).not.toMatch(/Experimental \/ not validated[\s\S]*tps-provisional-control/)
  })
})