import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'

const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8')
const styles = readFileSync(new URL('./styles.css', import.meta.url), 'utf8')
const main = readFileSync(new URL('./main.js', import.meta.url), 'utf8')

describe('Local Area Profile inspector integration', () => {
  it('mounts the profile dashboard inside the shared right-side inspector', () => {
    expect(html).toMatch(/id="inspector"[\s\S]*id="local-profile-dashboard"[\s\S]*id="profile-dashboard-sections"[\s\S]*<\/aside>/)
    expect(html).not.toMatch(/class="map-shell"[\s\S]*id="local-profile-dashboard"[\s\S]*id="inspector"/)
    expect(html).toMatch(/id="profile-print"[^>]*>Print Profile<\/button>/)
  })

  it('uses inspector flow styling rather than a map-covering absolute dashboard', () => {
    expect(styles).toMatch(/\.local-profile-dashboard\s*\{[^}]*padding:/s)
    expect(styles).not.toMatch(/\.local-profile-dashboard\s*\{[^}]*position:\s*absolute/s)
    expect(styles).not.toMatch(/\.local-profile-dashboard\s*\{[^}]*left:\s*calc/s)
  })

  it('opens the profile inspector while calculating and when the circle is clicked', () => {
    expect(main).toContain("map.on('click', 'local-profile-circle-fill'")
    expect(main).toContain("showInspectorMode('profile')")
    expect(main).toContain("elements.profileDashboard.hidden = mode !== 'profile'")
    expect(main).toContain("elements.buildingDetails.hidden = mode !== 'floodRisk'")
    expect(main).toContain("elements.transitDetails.hidden = mode !== 'transit'")
  })

  it('binds TPS clicks ahead of buildings and closes a stale TPS profile when the overlay is disabled', () => {
    expect(main).toContain("bindTpsInteractions()")
    expect(main).toContain("map.on('click', 'tps-provisional-fill'")
    expect(main).toContain('resolveTpsSelection(feature, await loadExactTpsFeatureIndex())')
    expect(main).toContain("requestProfile({ selection }, true)")
    expect(main).toContain("activePlanxOverlays.has('tpsProvisional')")
    expect(main).toContain("profileState.selection?.type === 'tps'")
    expect(main).not.toContain("queryRenderedFeatures(event.point, { layers: ['tps-provisional-fill'] })")
  })

  it('closes the panel without clearing the profile circle or result', () => {
    const closeFunction = main.match(/function closeInspector\(\) \{[\s\S]*?\n\}/)?.[0] ?? ''
    expect(closeFunction).not.toContain("if (inspectorMode === 'building')")
    expect(closeFunction).not.toContain("type: 'clear'")
    expect(closeFunction).not.toContain("local-profile-circle')?.setData")
  })

  it('uses the blue inspector metric for WGS84 coordinates rather than readiness status', () => {
    expect(main).toContain('const presentation = profileSelectionPresentation')
    expect(main).toContain('elements.selectedMetricLabel.textContent = presentation.metricLabel')
    expect(main).toContain('elements.selectedMetricValue.textContent = presentation.metricValue')
    expect(main).not.toContain("elements.selectedMetricLabel.textContent = 'Profile status'")
    expect(styles).toMatch(/\.selected-metric\.profile-coordinate-metric strong\s*\{[^}]*white-space:\s*pre-line/s)
  })
})
