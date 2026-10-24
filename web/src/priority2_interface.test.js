import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'

const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8')
const styles = readFileSync(new URL('./styles.css', import.meta.url), 'utf8')
const main = readFileSync(new URL('./main.js', import.meta.url), 'utf8')
const legends = readFileSync(new URL('./legends.js', import.meta.url), 'utf8')

describe('priority 2 interface', () => {
  it('puts three compact layer toggles beside the building count with the background off by default', () => {
    expect(html).toMatch(/Prototype Dated: 24\.October\.2026[\s\S]*id="building-count"[\s\S]*id="building-toggle"[\s\S]*id="basemap-toggle"[^>]*aria-checked="false"[\s\S]*id="roads-toggle"/)
    expect(html).not.toMatch(/class="toggle-row"[^>]*id="building-toggle"/)
    expect(styles).toMatch(/\.masthead-layer-toggle/)
    expect(main).toContain('setBaseLayerVisibility()')
  })

  it('uses the local DA-ZA logo and brand brown for the masthead and interface accents', () => {
    expect(html).toContain('<img class="brand-mark" src="%BASE_URL%da-za-logo.png" alt="DA-ZA logo" />')
    expect(html).not.toContain('class="brand-subtitle"')
    expect(styles).toContain('--brand: #94412f')
    expect(styles).toContain('--brand-hover: #6f2f24')
    expect(styles).toContain('--brand-light: #e7b5aa')
    expect(styles).toContain('--logo-black: #000000')
    expect(styles).toMatch(/\.masthead\s*\{[^}]*background:\s*var\(--logo-black\)/s)
    expect(styles).toMatch(/\.masthead-layer-toggle\[aria-checked='true'\] > span\s*\{[^}]*background:\s*var\(--brand-light\)/s)
    expect(styles).toMatch(/\.primary-button\s*\{[^}]*background:\s*var\(--brand\)/s)
    expect(styles).toMatch(/\.sidebar-footer span:first-child\s*\{[^}]*color:\s*var\(--brand\)/s)
  })

  it('removes repetitive sidebar introduction and footer copy', () => {
    expect(html).not.toContain('EXPLORE THE PILOT')
    expect(html).not.toContain('Google Open Buildings and transit layers for the study area.')
    expect(html).not.toContain('Building height is available as a modelled 2023 raster overlay.')
    expect(html).toContain('<h1>Layers</h1>')
  })

  it('groups overlays into analytical, context, and experimental disclosure sections with short badges', () => {
    expect(main).toContain("['current', 'Analytical layers']")
    expect(main).toContain("['context', 'Context layers']")
    expect(main).toContain("['experimental', 'Experimental / not validated']")
    expect(main).toContain("details.open = groupKey === 'current'")
    expect(main).toContain("className = 'overlay-status-badge'")
    expect(main).not.toContain("className = 'overlay-context-heading'")
  })

  it('keeps detailed provenance in legend help rather than the visible legend', () => {
    expect(legends).not.toMatch(/if \(context\) appendText\(sectionNode/)
    expect(legends).not.toMatch(/if \(section\.caveat\) appendText\(sectionNode/)
    expect(legends).toMatch(/renderLegendHelp[\s\S]*contextText/)
  })

  it('organises Method & sources around current, contextual, and experimental products', () => {
    expect(html).toContain('<h3>Current products</h3>')
    expect(html).toContain('<h3>Context layers</h3>')
    expect(html).toContain('<h3>Experimental and modelled products</h3>')
    expect(html).toContain('ARPM Studio')
    expect(html).toContain('Development Plan for Ahmedabad 2041')
    expect(html).toContain('https://arpm.studio/projects/ahmedabad-dp-2041')
    expect(html).not.toContain('<h3>PlanX network and scenarios</h3>')
  })

  it('keeps the two interactive tools above one Map layers section containing all static controls', () => {
    expect(html).toMatch(/featured-transit-controls[\s\S]*local-profile-controls[\s\S]*id="planx-controls-title"[\s\S]*id="indicator-groups"[\s\S]*id="space-syntax-controls"[\s\S]*id="planx-overlay-controls"/)
    expect(html.indexOf('id="opacity-control"')).toBeGreaterThan(html.indexOf('id="planx-controls-title"'))
    expect(html).not.toContain('id="hide-no-data"')
    expect(main).not.toContain("groupBodies.get('experimental').append(elements.spaceSyntaxSelect.closest('.overlay-select-row'))")
  })

  it('changes only hollow route-stop stroke opacity while orange seed stops remain opaque', () => {
    expect(main).toContain("elements.routeStopOpacityControl.addEventListener('input', updateRouteStopOpacity)")
    expect(main).toContain("['case', ['get', 'seed_stop'], 1, opacity]")
    expect(main).toContain("map.setPaintProperty('transit-isochrone-route-stops-circle', 'circle-stroke-opacity'")
  })

  it('publishes fixed-style, non-selectable building polygons without display-attribute controls', () => {
    expect(html).toContain('Building footprints')
    expect(html).not.toContain('id="hide-no-data"')
    expect(main).toContain("'fill-color': BUILDING_FILL_COLOR")
    expect(main).toContain("control.className = 'planx-overlay-button building-display-control'")
    expect(main).toContain("title.textContent = 'Buildings'")
    expect(main).not.toContain('Fixed-style building footprints.')
    expect(styles).toMatch(/\.building-display-control[^}]*cursor:\s*default/s)
    expect(main).not.toContain("map.on('click', BUILDING_FILL")
    expect(main).not.toContain("map.on('mousemove', BUILDING_FILL")
    expect(main).not.toContain('makeStepExpression')
    expect(main).not.toContain('buildingFeatureFilter')
  })

  it('does not register optional space-syntax data during initial map loading', () => {
    const mapLoad = main.slice(main.indexOf("map.on('load'"), main.indexOf("map.on('error'"))
    expect(mapLoad).not.toContain('registerSpaceSyntaxLayers()')
    expect(main).toContain("if (property !== 'off') registerSpaceSyntaxLayers()")
  })
})