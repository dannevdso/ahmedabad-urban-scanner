import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

import {
  PRINT_PAGE_SIZES,
  PRINT_SECTION_LABELS,
  buildPrintSnapshot,
  getPrintAvailability,
  renderPrintProfileHTML,
  PRINT_DISCLAIMER,
  PRINT_TEMPLATES,
} from './print_profile.js'

const printStyles = readFileSync(new URL('./print_profile.css', import.meta.url), 'utf8')
const printSource = readFileSync(new URL('./print_profile.js', import.meta.url), 'utf8')

describe('monochrome Local Area Profile print system', () => {
  const result = {
    contractVersion: 'local-area-profile.v1',
    center: [72.57, 23.03],
    radiusM: 800,
    profileId: 'lap-800-001',
    date: '2026-10-20',
    provenance: { source: 'Prepared local area profile', method: 'Centroid-selected buildings' },
    overview: { charts: [{ title: 'Building area', method: 'Centroid-selected buildings', bins: [{ label: '0–100 m²', value: 3 }, { label: '100–250 m²', value: 7 }] }] },
    buildings: null,
    streetsConnectivity: { metrics: { intersectionDensity: 1.2 } },
  }

  it('loads the boundary only when print preview opens', () => {
    const boundaryFetch = 'fetch(`${import.meta.env.BASE_URL}data/local-profile/ahmedabad-boundary.geojson`)'
    expect(printSource).toContain(boundaryFetch)
    expect(printSource.indexOf(boundaryFetch)).toBeGreaterThan(printSource.indexOf('export function openPrintProfilePreview'))
  })

  it('keeps the exact normalized result object in the print snapshot', () => {
    const state = { status: 'ready', center: result.center, radiusM: result.radiusM, result }
    const snapshot = buildPrintSnapshot(state, 'A3')
    expect(snapshot.result).toBe(result)
    expect(snapshot).toMatchObject({ pageSize: 'A3', center: result.center, radiusM: 800, profileId: 'lap-800-001', date: '2026-10-20' })
  })

  it('prints TPS name and number from the normalized selection without exposing internal source_id', () => {
    const tpsResult = { ...result, center: null, radiusM: null, selection: { type: 'tps', source_id: 'internal-only', tps_name: null, tps_no: '7', tps_status: 'provisional', areaM2: 1000 } }
    const html = renderPrintProfileHTML(buildPrintSnapshot({ status: 'ready', result: tpsResult }, 'A3'))
    expect(html).toContain('TPS name unavailable')
    expect(html).toContain('<dt>TPS number</dt><dd>7</dd>')
    expect(html).not.toContain('Status provisional')
    expect(html).toContain('<dt>Area</dt><dd>1,000 m²</dd>')
    expect(html).not.toContain('internal-only')
    expect(html).not.toContain('<dt>Center</dt>')
    expect(html).not.toContain('<dt>Radius</dt>')
  })

  it('prints three numeric building distributions, categorical SUHI counts, and stored-area share caveat from the normalized presentation', () => {
    const buildingsResult = { ...result, sections: { buildings: { status: 'available', data: {
      totalLocationCount: 5, centralLocationCount: 2, enrichedLocationCount: 3,
      provisionalHeightM: { unit: 'm', summary: { mean: 8 }, availability: { available: 3, denominator: 3 }, distribution: { bins: [0, 10, 20], counts: [1, 1], method: 'fixed' } },
      provisionalAreaM2: { unit: 'm²', summary: { mean: 40 }, availability: { available: 3, denominator: 3 }, distribution: { bins: [0, 10, 20], counts: [1, 1], method: 'fixed' } },
      derivedVolumeM3: { unit: 'm³', summary: { mean: 320 }, availability: { available: 3, denominator: 3 }, distribution: { bins: [0, 10, 20], counts: [1, 1], method: 'fixed' } },
      suhi: { kind: 'categorical', unit: 'unverified categorical class', summary: { dominantClass: 'High' }, availability: { available: 3, denominator: 3 }, distribution: { categories: [{ key: 'low', label: 'Low', count: 1 }, { key: 'moderate', label: 'Moderate', count: 0 }, { key: 'high', label: 'High', count: 2 }, { key: 'veryHigh', label: 'Very High', count: 0 }, { key: 'extremeHigh', label: 'Extreme High', count: 0 }], totalCount: 3 } },
      summedStoredAreaM2: 1200, storedAreaSharePct: 12.5,
      storedAreaSelectionBasis: 'Full stored area values of point-selected enriched records divided by exact circle/TPS area; Central is count-only; not footprint-union coverage.',
    } } } }
    const html = renderPrintProfileHTML(buildPrintSnapshot({ status: 'ready', result: buildingsResult }, 'A2'))
    expect(html).toContain('Provisional area')
    expect(html).toContain('Provisional height')
    expect(html).toContain('Derived volume')
    expect(html).toContain('SUHI')
    expect(html).toContain('Stored building area share')
    expect(html).toContain('not footprint-union coverage')
    expect(html).toContain('exact selected area/TPS area')
    expect(html).not.toContain('exact circle/TPS area')
    expect(html).toContain('SUHI class distribution')
    expect(html).toContain('High')
  })

  it('exposes independent A2 landscape, A3 landscape, and A3 portrait formats', () => {
    expect(PRINT_PAGE_SIZES).toEqual({
      A2: { width: '594mm', height: '420mm', orientation: 'landscape' },
      A3: { width: '420mm', height: '297mm', orientation: 'landscape' },
      A3_PORTRAIT: { width: '297mm', height: '420mm', orientation: 'portrait' },
    })
    expect(buildPrintSnapshot({ status: 'ready', result }, 'A3_PORTRAIT').pageClass).toBe('print-page-a3-portrait')
  })

  it('renders the exact experimental accuracy disclaimer on every format', () => {
    for (const pageSize of ['A2', 'A3', 'A3_PORTRAIT']) {
      const html = renderPrintProfileHTML(buildPrintSnapshot({ status: 'ready', result }, pageSize))
      expect(html).toContain(PRINT_DISCLAIMER)
      expect(html).toContain('print-disclaimer')
    }
  })

  it('uses the approved numbered A3 atlas composition for landscape printing', () => {
    const atlasResult = {
      ...result,
      radiusM: 400,
      sections: {
        overview: { status: 'available', data: { totalLocationCount: 336, intersectionDensityPerKm2: 73.61, vegetationFractionMean: 0.4228, publicTransportStops: 4, directlyServingRoutes: 5 } },
        buildings: { status: 'available', data: {
          totalLocationCount: 336,
          provisionalAreaM2: { unit: 'm²', summary: { mean: 288.15, median: 225, min: 6, max: 3015 }, availability: { available: 336, denominator: 336 }, distribution: { bins: [0, 25, 100, 250, 500, 1000, 5000], counts: [5, 35, 153, 107, 28, 8], method: 'fixed' } },
          provisionalHeightM: { unit: 'm', summary: { mean: 8.08, median: 7, min: 3, max: 27 }, availability: { available: 336, denominator: 336 }, distribution: { bins: [0, 3, 6, 10, 20, 50, 100], counts: [0, 116, 117, 97, 6, 0], method: 'fixed' } },
          suhi: { summary: { dominantClass: 'Very High' } }, summedStoredAreaM2: 96817, storedAreaSharePct: 19.26,
        } },
        streetsConnectivity: { status: 'available', data: { clippedLengthKm: 10.92, intersectionDensityPerKm2: 73.61, linkNodeRatio: 1.57, connectedNodeRatio: 0.0811 } },
        spaceSyntaxCentrality: { status: 'available', data: {
          centrality: { betweenness: { weightedMean: 2338085.44 }, closeness: { weightedMean: 0.001899 }, straightness: { weightedMean: 18.03 } },
          spaceSyntax: { betweenness: { weightedMean: 173.72 }, closeness: { weightedMean: 0.000001346 }, straightness: { weightedMean: 0.764 } },
        } },
        environment: { status: 'available', data: {
          lst: { mean: 38.12, median: 37.93, maximum: 41.39, validPixelCount: 554, coveragePercentage: 100, distribution: { bins: [35, 36, 37, 38, 39, 40, 41, 42], counts: [6, 62, 222, 162, 53, 35, 14] } },
          ndvi: { mean: 0.293, median: 0.249, validPixelCount: 5028, coveragePercentage: 100, distribution: { bins: [-1, 0, 0.3, 0.6, 1], counts: [56, 2846, 1703, 423] } },
          vegetationFraction: { mean: 0.4228, provenance: { threshold: 0.3 } },
        } },
        publicTransport: { status: 'available', data: { stopsInsideCircle: 4, routesServingStopsInsideCircle: [1, 2, 3, 4, 5], routeReachAreaM2: 89550000 } },
        parksEducation: { status: 'available', data: { parks: { count: 5 }, schools: { count: 0 } } },
      },
    }
    const html = renderPrintProfileHTML(buildPrintSnapshot({ status: 'ready', result: atlasResult }, 'A3'))
    expect(html).toContain('class="print-sheet print-page-a3 atlas-sheet"')
    for (const index of ['00', '01', '02', '03', '04', '05', '06', '07', '08', '09', '10']) expect(html).toContain(`data-atlas-index="${index}"`)
    expect(html).toContain('PROTOTYPE')
    expect(html).not.toContain('SPATIAL ANALYSIS FOR A MORE LIVABLE CITY')
    expect(html).not.toContain('MODULAR ATLAS SYSTEM')
    expect(html).toContain('Stops inside selected area')
    expect(html).not.toContain('Stops inside circle')
    expect(html).toContain('Footprint-area distribution')
    expect(html).toContain('Building-height field distribution')
    expect(html).toContain('LST distribution')
    expect(html).toContain('NDVI distribution')
    expect(html).toContain('Syntax closeness')
    expect(html).toContain('Syntax straightness')
    expect(html).not.toContain('pattern-dots')
    expect(html).toContain('Experimental data limitation')
    expect(html).toContain(PRINT_DISCLAIMER)
  })

  it('defines the A3 atlas as four chart columns with one consistent 45-degree hatch', () => {
    expect(printStyles).toMatch(/\.atlas-chart-row\s*\{[^}]*grid-template-columns:\s*repeat\(4, minmax\(0, 1fr\)\)/s)
    expect(printStyles).toMatch(/\.atlas-bar\s*\{[^}]*background-image:\s*var\(--atlas-hatch\)/s)
    expect(printStyles).toMatch(/--atlas-hatch:\s*url\([^;]*M-2 2L2-2[^;]*M0 8L8 0/s)
    expect(printStyles).not.toMatch(/\.atlas-bar[^}]*pattern-dots/s)
  })

  it('matches the approved V5 A3 typography, page rows, and module grids', () => {
    expect(printStyles).toMatch(/\.print-sheet\.atlas-sheet\s*\{[^}]*grid-template-rows:\s*31mm 1\.4mm 72mm 3mm 53mm 3mm 87mm 3mm 23\.6mm/s)
    expect(printStyles).toMatch(/\.atlas-header\s*\{[^}]*grid-template-columns:\s*155mm 1fr 72mm[^}]*column-gap:\s*8mm/s)
    expect(printStyles).toMatch(/\.atlas-row-one\s*\{[^}]*grid-template-columns:\s*90mm 90mm 100mm 111mm/s)
    expect(printStyles).toMatch(/\.atlas-row-two\s*\{[^}]*grid-template-columns:\s*132mm 132mm 130mm/s)
    expect(printStyles).toMatch(/\.atlas-brand h1[^}]*font:\s*900 34pt\/.77 var\(--print-font-heading\)/s)
    expect(printStyles).toMatch(/\.atlas-module[^}]*border-top:\s*1mm solid var\(--print-black\)[^}]*border-right:\s*0/s)
    expect(printStyles).toMatch(/\.atlas-module-head[^}]*height:\s*10mm[^}]*margin-bottom:\s*3mm/s)
    expect(printStyles).toMatch(/\.atlas-module-head::after[^}]*width:\s*16mm[^}]*height:\s*\.8mm/s)
    expect(printStyles).toMatch(/\.atlas-module-head > span[^}]*font:\s*800 18pt\/.75 var\(--print-font-mono\)/s)
    expect(printStyles).toMatch(/\.atlas-chart-wrap[^}]*height:\s*71mm[^}]*grid-template-rows:\s*8mm 1fr 9mm/s)
  })

  it('uses the V5 header and footer structure in the dynamic A3 report', () => {
    const html = renderPrintProfileHTML(buildPrintSnapshot({ status: 'ready', result }, 'A3'))
    expect(html).toContain('<span class="city">AHMEDABAD</span><span class="system">URBAN SCANNER</span>')
    expect(html).toContain('<p class="atlas-prototype">PROTOTYPE</p>')
    expect(html).toContain('class="atlas-meta-row"')
    expect(html).toContain('class="atlas-disclaimer print-disclaimer"')
  })

  it('fills the A3 profile and date metadata when the live result omits both', () => {
    const liveResult = { ...result, profileId: undefined, date: undefined, requestId: 7 }
    const html = renderPrintProfileHTML(buildPrintSnapshot({ status: 'ready', result: liveResult, printDate: '2026-10-24' }, 'A3'))
    expect(html).toContain('<dt>PROFILE</dt><dd>ID 07</dd>')
    expect(html).toContain('<dt>DATE</dt><dd>2026-10-24</dd>')
    expect(html).not.toContain('<dt>PROFILE</dt><dd>No data</dd>')
    expect(html).not.toContain('<dt>DATE</dt><dd>No data</dd>')
  })

  it('keeps only A3 LANDSCAPE beneath the main report title', () => {
    const html = renderPrintProfileHTML(buildPrintSnapshot({ status: 'ready', result }, 'A3'))
    expect(html).toContain('<small>A3 LANDSCAPE</small>')
    expect(html).not.toContain('MODULAR URBAN ATLAS')
  })

  it('keeps the street-length value clear of its divider at the shared KPI size', () => {
    expect(printStyles).toMatch(/\.atlas-streets > div:first-child\s*\{[^}]*padding:\s*0 7mm 0 0/s)
    expect(printStyles).toMatch(/\.atlas-streets > div:first-child dd\s*\{[^}]*font-size:\s*15pt/s)
  })

  it('stacks the three connectivity metrics like the syntax metric column', () => {
    const html = renderPrintProfileHTML(buildPrintSnapshot({ status: 'ready', result }, 'A3'))
    expect(html).toContain('<dl class="atlas-streets">')
    expect(html).not.toContain('<dl class="atlas-streets print-metrics">')
    expect(html).toMatch(/Intersections \/ km².*Link \/ node ratio.*Connected-node share/s)
    expect(printStyles).toMatch(/\.atlas-streets > div:nth-child\(n \+ 2\)\s*\{[^}]*grid-column:\s*2[^}]*flex-direction:\s*column/s)
    expect(printStyles).toMatch(/\.atlas-streets > div:nth-child\(2\)\s*\{[^}]*grid-row:\s*1/s)
    expect(printStyles).toMatch(/\.atlas-streets > div:nth-child\(n \+ 2\) dd\s*\{[^}]*font-size:\s*12\.5pt/s)
  })

  it('stacks footprint and building-height summaries like the centrality and syntax columns', () => {
    expect(printStyles).toMatch(/\.atlas-building-summaries section > div\s*\{[^}]*grid-template-rows:\s*repeat\(3, 1fr\)/s)
    expect(printStyles).toMatch(/\.atlas-building-summaries section > div > div\s*\{[^}]*flex-direction:\s*column[^}]*justify-content:\s*center/s)
    expect(printStyles).toMatch(/\.atlas-building-summaries b\s*\{[^}]*font:\s*700 12\.5pt\/\.95 var\(--print-font-mono\)/s)
  })

  it('offsets chart labels from the baseline and uses a uniform SVG 45-degree hatch', () => {
    expect(printStyles).toMatch(/\.atlas-chart-labels\s*\{[^}]*padding:\s*\.8mm 0 0 2mm/s)
    expect(printStyles).toMatch(/--atlas-hatch:\s*url\([^;]*M-2 2L2-2[^;]*M0 8L8 0/s)
    expect(printStyles).toMatch(/\.atlas-bar\s*\{[^}]*background-size:\s*2mm 2mm/s)
  })

  it('renders an Ahmedabad boundary-only SVG key map and selected circle geometry', () => {
    const circleResult = { ...result, selection: { type: 'circle', center: [72.57, 23.03], radiusM: 400 } }
    const html = renderPrintProfileHTML(buildPrintSnapshot({ status: 'ready', result: circleResult }, 'A3'))
    expect(html).toContain('class="print-key-map"')
    expect(html).toContain('ahmedabad-boundary')
    expect(html).toContain('<svg')
    expect(html).toContain('selected-circle')
    expect(html).toContain('north-arrow')
    expect(html).toContain('scale-bar')
    expect(html).not.toContain('road')
    expect(html).not.toContain('basemap')
  })

  it('positions the small-circle locator halo at the selected center rather than the map center', () => {
    const circleResult = { ...result, center: [72.46, 23.11], radiusM: 400, selection: { type: 'circle', center: [72.46, 23.11], radiusM: 400 } }
    const html = renderPrintProfileHTML(buildPrintSnapshot({ status: 'ready', result: circleResult }, 'A3'))
    const halo = html.match(/class="locator-halo" cx="([\d.]+)" cy="([\d.]+)"/)
    expect(halo).not.toBeNull()
    expect(Number(halo[1])).toBeLessThan(20)
    expect(Number(halo[2])).toBeLessThan(20)
  })

  it('renders exact TPS Polygon and MultiPolygon geometry in the key map', () => {
    const polygon = { type: 'Polygon', coordinates: [[[72.55, 23.01], [72.58, 23.01], [72.58, 23.04], [72.55, 23.01]]] }
    const multiPolygon = { type: 'MultiPolygon', coordinates: [[[[72.55, 23.01], [72.58, 23.01], [72.58, 23.04], [72.55, 23.01]]]] }
    for (const geometry of [polygon, multiPolygon]) {
      const tpsResult = { ...result, center: null, radiusM: null, selection: { type: 'tps', tps_no: '7', geometry } }
      const html = renderPrintProfileHTML(buildPrintSnapshot({ status: 'ready', result: tpsResult }, 'A3_PORTRAIT'))
      expect(html).toContain('selected-tps')
      expect(html).toContain('ahmedabad-boundary')
      expect(html).not.toContain('road')
      expect(html).not.toContain('basemap')
    }
  })

  it('provides truthful selector labels and separate page specifications', () => {
    const html = renderPrintProfileHTML(buildPrintSnapshot({ status: 'ready', result }, 'A3_PORTRAIT'))
    expect(html).toContain('A2 landscape')
    expect(html).toContain('A3 landscape')
    expect(html).toContain('A3 portrait')
    expect(printStyles).toMatch(/@page print-a3-portrait\s*\{[^}]*size:\s*297mm 420mm/s)
    expect(printStyles).toContain('.print-page-a3-portrait')
  })

  it('defines fixed physical width and height for every sheet instead of min-height-only containment', () => {
    for (const [pageClass, width, height] of [
      ['.print-sheet', '420mm', '297mm'],
      ['.print-sheet.print-page-a2', '594mm', '420mm'],
      ['.print-sheet.print-page-a3-portrait', '297mm', '420mm'],
    ]) {
      const rule = printStyles.match(new RegExp(`${pageClass.replaceAll('.', '\\.')}\\s*\\{[^}]*\\}`, 's'))?.[0] ?? ''
      expect(rule).toContain(`width: ${width}`)
      expect(rule).toContain(`height: ${height}`)
      expect(rule).not.toContain('min-height:')
    }
  })

  it('keeps the live preview proportional and lets print sheets use their physical dimensions', () => {
    expect(printStyles).toMatch(/\.print-preview-mount\s*\{[^}]*aspect-ratio:/s)
    expect(printStyles).toMatch(/\.print-preview-mount\s*\{[^}]*place-items:\s*start/s)
    expect(printStyles).toMatch(/\.print-sheet\s*\{[^}]*transform-origin:\s*top left/s)
    expect(printStyles).toMatch(/\.print-sheet\s*\{[^}]*box-sizing:\s*border-box/s)
    expect(printStyles).not.toMatch(/\.print-sheet\s*\{[^}]*max-width:/s)
    expect(printStyles).toMatch(/@media print[\s\S]*?\.print-sheet[\s\S]*?height:/s)
  })

  it('uses compact four-column metrics and bounded portrait content for one-page A3 compositions', () => {
    expect(printStyles).toMatch(/\.print-page-a3 \.print-metrics[^}]*grid-template-columns:\s*repeat\(4,/s)
    expect(printStyles).toMatch(/\.print-page-a3-portrait \.print-metrics[^}]*grid-template-columns:\s*repeat\(4,/s)
    expect(printStyles).toMatch(/\.print-page-a3-portrait \.print-key-map svg[^}]*max-height:\s*42mm/s)
    expect(printStyles).toMatch(/\.print-page-a3-portrait \.print-section\[data-slot="buildings"\][^}]*max-height:\s*none/s)
    expect(printStyles).toMatch(/\.print-page-a3 \.print-section\[data-section="buildings"\] > \.print-metrics[^}]*grid-column:\s*span 3/s)
    expect(printStyles).toMatch(/\.print-page-a3-portrait \.print-section\[data-section="buildings"\] > \.print-notes[^}]*grid-column:\s*span 1/s)
    expect(printStyles).toMatch(/\.print-page-a3-portrait \.print-notes[^}]*margin-top:\s*0[^}]*line-height:\s*1/s)
    expect(printStyles).toMatch(/\.print-page-a3-portrait \.print-metrics div[^}]*padding-bottom:\s*0/s)
    expect(printStyles).toMatch(/\.print-page-a3-portrait \.print-metrics dd[^}]*margin:\s*0/s)
  })

  it('keeps the A2 composition inside its fixed sheet with bounded page and anchor spacing', () => {
    expect(printStyles).toMatch(/\.print-sheet\.print-page-a2[^}]*padding:\s*15mm/s)
    expect(printStyles).toMatch(/\.print-page-a2 \.print-key-map[^}]*width:\s*101mm/s)
  })

  it('prefers the approved A3 atlas as the default print sheet while preserving explicit A2 selection', () => {
    const state = { status: 'ready', result }
    expect(buildPrintSnapshot(state).pageSize).toBe('A3')
    expect(buildPrintSnapshot(state, 'A2').pageSize).toBe('A2')
  })

  it('fits the three Environment charts on one print row', () => {
    expect(printStyles).toMatch(/\.print-section\[data-section="environment"\]\s*\{[^}]*grid-template-columns:\s*repeat\(3,/s)
  })

  it('fits the four building distributions on one wide print row', () => {
    expect(printStyles).toMatch(/\.print-section\[data-section="buildings"\]\s*\{[^}]*grid-column:\s*span\s+2[^}]*grid-template-columns:\s*repeat\(4,/s)
    expect(printStyles).toMatch(/\.print-section\[data-section="buildings"\]\s*>\s*\.print-chart\s*\{[^}]*min-width:\s*0/s)
  })

  it('wraps print notes and keeps chart grids inside narrow section columns', () => {
    expect(printStyles).toMatch(/\.print-notes span\s*\{[^}]*white-space:\s*normal[^}]*overflow-wrap:\s*anywhere/s)
    expect(printStyles).toMatch(/\.print-chart-columns\s*\{[^}]*width:\s*100%[^}]*box-sizing:\s*border-box[^}]*overflow:\s*hidden/s)
  })

  it('reduces nested normalized sections to curated metrics and compact chart rows', () => {
    const nestedResult = {
      ...result,
      sections: {
        overview: {
          status: 'available',
          data: {
            summary: { buildingCount: 8862, footprintCoverageM2: 971959.11 },
            distributions: { buildingArea: [{ label: '0–100 m²', value: 3 }, { label: '100–250 m²', value: 7 }] },
            diagnostics: { hugePayload: { nested: { shouldNot: 'be rendered' } } },
          },
        },
      },
    }
    const html = renderPrintProfileHTML(buildPrintSnapshot({ status: 'ready', result: nestedResult }, 'A2'))
    expect(html).toContain('Summary / Buildings')
    expect(html).toContain('Footprint Coverage M2')
    expect(html).not.toContain('0–100 m²')
    expect(html).not.toContain('hugePayload')
    expect(html).not.toContain('shouldNot')
    expect(html).not.toContain('"buildingCount"')
  })

  it('curates buildings KPIs and renders footprint-area histograms vertically', () => {
    const buildingsResult = {
      ...result,
      sections: {
        buildings: {
          status: 'available',
          data: {
            buildingCount: 12,
            footprintCoverageM2: 4200,
            footprintCoveragePct: 21.5,
            footprintAreaM2: {
              mean: 350,
              histogram: { method: 'fixed', bins: [0, 100, 250, 500], counts: [3, 4, 5] },
            },
            diagnostics: { shouldNot: 'be rendered' },
          },
        },
      },
    }
    const html = renderPrintProfileHTML(buildPrintSnapshot({ status: 'ready', result: buildingsResult }, 'A2'))
    const section = html.match(/data-section="buildings">([\s\S]*?)<\/section>/)?.[1] ?? ''
    expect(section).toContain('Building-footprint coverage (%)')
    expect(section).toContain('Footprint area (m²)')
    expect(section).toContain('print-chart-columns')
    expect(section).toContain('0–100')
    expect(section).not.toContain('shouldNot')
    expect(section).not.toContain('print-chart-row')
  })

  it('uses four street KPIs and suppresses misleading fixedBins charts', () => {
    const streetsResult = {
      ...result,
      sections: {
        streetsConnectivity: {
          status: 'available',
          data: {
            clippedLengthKm: 4.2,
            intersectionDensityPerKm2: 31,
            linkNodeRatio: 1.8,
            connectedNodeRatio: 0.92,
            fixedBins: { streetLengthKm: { bins: [0, 1, 3, 5], counts: [0, 0, 1] } },
          },
        },
      },
    }
    const html = renderPrintProfileHTML(buildPrintSnapshot({ status: 'ready', result: streetsResult }, 'A3'))
    const section = html.match(/data-section="streetsConnectivity">([\s\S]*?)<\/section>/)?.[1] ?? ''
    expect((section.match(/<dd/g) ?? []).length).toBe(4)
    expect(section).not.toContain('print-chart')
    expect(section).toContain('<dt>Street length</dt><dd>4.2 km</dd>')
  })

  it('curates environment raster charts and omits empty heat-risk bins', () => {
    const environmentResult = {
      ...result,
      sections: {
        environment: {
          status: 'available',
          data: {
            heatRisk: { mean: null, distribution: { bins: [0, 1, 2], counts: [0, 0] } },
            lst: { mean: 40.7, validPixelCount: 12, coveragePercentage: 98, distribution: { bins: [30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48], counts: [0, 0, 0, 0, 0, 0, 0, 1, 2, 3, 2, 1, 1, 0, 0, 0, 0, 0] } },
            ndvi: { mean: 0.32, distribution: { bins: [-1, 0, 0.5, 1], counts: [1, 3, 2] } },
            vegetationFraction: { mean: 0.4, distribution: { bins: [0, 1, 2], counts: [6, 4] }, provenance: { threshold: 0.3 } },
            height2023: { mean: 8.1, distribution: { bins: [0, 5, 10], counts: [2, 8] } },
          },
        },
      },
    }
    const html = renderPrintProfileHTML(buildPrintSnapshot({ status: 'ready', result: environmentResult }, 'A2'))
    const section = html.match(/data-section="environment">([\s\S]*?)<\/section>/)?.[1] ?? ''
    expect(section).toContain('LST')
    expect(section).toContain('NDVI')
    expect(section).toContain('print-chart-columns')
    expect(section).toContain('Outside 30–48')
    expect(section).toContain('print-chart-columns-dense')
    expect(section).toContain('grid-template-columns:repeat(19, minmax(0, 1fr))')
    expect((section.match(/print-chart-vertical/g) ?? []).length).toBe(2)
    expect(section).not.toContain('Vegetation threshold</strong>')
    expect(section).not.toContain('Heat risk</strong>')
    expect(section).not.toContain('print-chart-row')
  })

  it('prints the environment flood-risk categorical area chart, including unavailable Low', () => {
    const environmentResult = {
      ...result,
      sections: { environment: { status: 'available', data: { floodRiskArea: {
        status: 'available', unit: 'm²',
        categories: [
          { key: 'veryHigh', label: 'Very high', sourceClass: 'Very High Risk Areas', areaM2: 1200, status: 'available' },
          { key: 'high', label: 'High', sourceClass: 'High Risk Areas', areaM2: 3400, status: 'available' },
          { key: 'moderate', label: 'Moderate', sourceClass: 'Moderate Risk Areas', areaM2: 5600, status: 'available' },
          { key: 'low', label: 'Low', sourceClass: null, areaM2: null, status: 'unavailable' },
        ],
        totalClassifiedAreaM2: 10200, caveat: 'Low is not a source class.',
      } } } },
    }
    const html = renderPrintProfileHTML(buildPrintSnapshot({ status: 'ready', result: environmentResult }, 'A2'))
    const section = html.match(/data-section="environment">([\s\S]*?)<\/section>/)?.[1] ?? ''
    expect(section).toContain('Flood-risk area by category')
    expect(section).toContain('Very high')
    expect(section).toContain('Low')
    expect(section).toContain('Unavailable')
  })

  it('omits availability and methods from the print presentation', () => {
    const verboseResult = {
      ...result,
      provenance: { source: 'A'.repeat(5000), method: 'B'.repeat(5000), caveat: 'C'.repeat(5000) },
      sections: { methods: { status: 'available', data: { method: 'D'.repeat(5000), caveat: 'E'.repeat(5000) } } },
    }
    const html = renderPrintProfileHTML(buildPrintSnapshot({ status: 'ready', result: verboseResult }, 'A2'))
    expect(html.length).toBeLessThan(20000)
    expect(html).toContain('Source / provenance')
    expect(PRINT_SECTION_LABELS).not.toHaveProperty('availability')
    expect(PRINT_SECTION_LABELS).not.toHaveProperty('methods')
    expect(html).not.toContain('data-section="availability"')
    expect(html).not.toContain('data-section="methods"')
    expect(html).not.toContain('A'.repeat(1000))
  })

  it('prints nested labels, method/status strings, and concise numeric values', () => {
    const nestedResult = {
      ...result,
      sections: {
        parksEducation: { status: 'available', data: { parks: { count: 5, available: 9 }, schools: { count: 3, available: 9 } } },
        availability: { status: 'available', data: { buildings: 'available', environment: 'available', methods: 'available' } },
        methods: { status: 'available', data: { circle: 'metric CRS circle', centroidSelection: 'exact centroid within circle' } },
        buildings: { status: 'available', data: { footprintCoverageM2: 971959.1082763672, mean: 0.0017886045962701984 } },
      },
    }
    const html = renderPrintProfileHTML(buildPrintSnapshot({ status: 'ready', result: nestedResult }, 'A2'))
    expect(html).toContain('Parks / count')
    expect(html).toContain('Schools / count')
    expect(html).toContain('Footprint Coverage M2</dt><dd')
    expect(html).not.toContain('metric CRS circle')
    expect(html).toContain('971,959.11')
    expect(html).toContain('0.0018')
    expect(html).not.toContain('971959.1082763672')
    expect(html).not.toContain('<div class="print-notes"><span>available</span>')
  })

  it('caps each section at four summary metrics so one-sheet cards do not clip', () => {
    const denseResult = {
      ...result,
      sections: { buildings: { status: 'available', data: Object.fromEntries(Array.from({ length: 10 }, (_, index) => [`metric${index + 1}`, index + 1])) } },
    }
    const html = renderPrintProfileHTML(buildPrintSnapshot({ status: 'ready', result: denseResult }, 'A2'))
    const buildingSection = html.match(/data-section="buildings">([\s\S]*?)<\/section>/)?.[1] ?? ''
    expect((buildingSection.match(/<dd/g) ?? []).length).toBe(4)
    expect(buildingSection).not.toContain('Metric 5')
  })

  it.each(['A2', 'A3'])('keeps %s sheet markup bounded and structurally one-sheet', (pageSize) => {
    const html = renderPrintProfileHTML(buildPrintSnapshot({ status: 'ready', result }, pageSize))
    expect(html).toMatch(new RegExp(`data-page-size="${pageSize}"`))
    expect((html.match(/class="print-section /g) ?? []).length).toBe(7)
    expect(html.length).toBeLessThan(20000)
    expect(html).not.toContain('undefined')
  })

  it('labels point-based TPS overview counts as Building locations without footprint coverage', () => {
    const tpsResult = {
      ...result,
      selection: { type: 'tps', tps_name: 'Example TPS', tps_no: '7', areaM2: 1000 },
      sections: { ...result.sections, overview: { status: 'available', data: { totalLocationCount: 327, intersectionDensityPerKm2: 42.25 } } },
    }
    const html = renderPrintProfileHTML(buildPrintSnapshot({ status: 'ready', result: tpsResult }, 'A3'))
    const overview = html.match(/data-section="overview">([\s\S]*?)<\/section>/)?.[1] ?? ''
    expect(overview).toContain('Building locations')
    expect(overview).toContain('327')
    expect(overview).not.toContain('Building-footprint coverage')
  })

  it('defines fixed independent master templates with stable slot geometry', () => {
    expect(PRINT_TEMPLATES).toMatchObject({
      A2: { widthMm: 594, heightMm: 420, columns: 16, marginMm: 15 },
      A3: { widthMm: 420, heightMm: 297, columns: 12, marginMm: 12 },
      A3_PORTRAIT: { widthMm: 297, heightMm: 420, columns: 8, marginMm: 12 },
    })
    for (const template of Object.values(PRINT_TEMPLATES)) {
      expect(template.slots.map(({ id }) => id)).toEqual([
        'header', 'key-map', 'overview', 'buildings', 'streets-connectivity',
        'space-syntax-centrality', 'environment', 'public-transport', 'parks-education', 'footer',
      ])
      expect(template.slots.every(({ x, y, width, height }) => [x, y, width, height].every(Number.isFinite))).toBe(true)
    }
  })

  it('renders one fixed key map and stable analytical slots without the computed-result box', () => {
    const html = renderPrintProfileHTML(buildPrintSnapshot({ status: 'ready', result }, 'A3'))
    expect((html.match(/class="print-key-map"/g) ?? []).length).toBe(1)
    for (const slotId of ['header', 'key-map', 'overview', 'buildings', 'streets-connectivity', 'space-syntax-centrality', 'environment', 'public-transport', 'parks-education', 'footer']) {
      expect(html).toContain(`data-slot="${slotId}"`)
    }
    expect(html).not.toContain('Computed result')
    expect(html).not.toContain('Exact normalized dashboard result; no values recalculated for print.')
  })

  it('keeps the fixed grid physical, monochrome, and free of runtime layout rearrangement', () => {
    expect(printStyles).toContain('--print-black: #000000')
    expect(printStyles).toContain('--print-white: #FFFFFF')
    expect(printStyles).not.toMatch(/border-radius\s*:/)
    expect(printStyles).not.toMatch(/box-shadow\s*:/)
    expect((printStyles.match(/gradient/gi) ?? []).length).toBe(0)
    expect(printStyles).toMatch(/--atlas-hatch:\s*url\([^;]*M-2 2L2-2[^;]*M0 8L8 0/s)
    expect(printStyles).toContain('grid-template-columns: repeat(16,')
    expect(printStyles).toContain('grid-template-columns: repeat(12,')
    expect(printStyles).toContain('grid-template-columns: repeat(8,')
    expect(printStyles).not.toMatch(/@media\s*\([^)]*(width|orientation)/i)
  })

  it('uses the sheet grid as the master layout so fixed slots cannot overlap', () => {
    expect(printStyles).toMatch(/\.print-sheet\s*\{[^}]*display:\s*grid/s)
    expect(printStyles).toMatch(/\.print-sections\s*\{[^}]*display:\s*contents/s)
    expect(printStyles).toMatch(/\.print-page-a3 \.print-key-map[^}]*grid-column:\s*1 \/ span 3[^}]*grid-row:\s*2/s)
    expect(printStyles).toMatch(/\.print-page-a3 \.print-section\[data-slot="buildings"\][^}]*grid-column:\s*1 \/ span 8[^}]*grid-row:\s*3/s)
    expect(printStyles).toMatch(/\.print-page-a3 \.print-section\[data-slot="environment"\][^}]*grid-column:\s*1 \/ span 8[^}]*grid-row:\s*4/s)
  })

  it('renders all required sections and monochrome encoding hooks', () => {
    const html = renderPrintProfileHTML(buildPrintSnapshot({ status: 'ready', result }, 'A3'))
    for (const label of ['Overview', 'Buildings', 'Streets &amp; connectivity', 'Space syntax / centrality', 'Land surface temperature', 'Public transport', 'Parks and schools']) {
      expect(html).toContain(label)
    }
    expect(html).toContain('print-map-placeholder')
    expect(printStyles).toContain('.pattern-hatch')
    expect(html).toContain('Source: Prepared local area profile')
    expect(html).toContain('<dt>PROFILE</dt><dd>lap-800-001</dd>')
  })

  it('renders Phase 1B sections from normalized values with compact KPIs and caveats', () => {
    const phase1bResult = {
      ...result,
      sections: {
        spaceSyntaxCentrality: { status: 'available', data: { centrality: { betweenness: { weightedMean: 2.25 }, closeness: { weightedMean: 0.42 }, straightness: { weightedMean: 0.81 } } } },
        publicTransport: { status: 'available', data: { stopsInsideCircle: 12, routesServingStopsInsideCircle: ['R1', 'R2'], routeReachAreaM2: 1500000, routeReachCells: 4, routeSelectionRule: 'routes serving GTFS stops inside circle' } },
        parksEducation: { status: 'available', data: { parks: { count: 5 }, schools: { count: 3 } } },
      },
    }
    const html = renderPrintProfileHTML(buildPrintSnapshot({ status: 'ready', result: phase1bResult }, 'A2'))
    const section = (key) => html.match(new RegExp(`data-section="${key}">([\\s\\S]*?)</section>`))?.[1] ?? ''
    expect(section('spaceSyntaxCentrality')).toContain('Betweenness / weighted mean')
    expect(section('spaceSyntaxCentrality')).toContain('2.25')
    expect(section('publicTransport')).toContain('Stops inside selected area')
    expect(section('publicTransport')).toContain('Routes serving stops')
    expect(section('publicTransport')).toContain('Route-associated reach area (km²)')
    expect(section('publicTransport')).toContain('1.5')
    expect(section('publicTransport')).not.toContain('R1, R2')
    expect(section('publicTransport')).toContain('routes serving GTFS stops inside selected area')
    expect(section('parksEducation')).toContain('Parks / count')
    expect(section('parksEducation')).toContain('Schools / count')
    for (const key of ['overview', 'spaceSyntaxCentrality', 'publicTransport', 'parksEducation']) expect(section(key)).not.toContain('print-chart-row')
  })

  it('renders explicit no-data treatment for unavailable and null metrics', () => {
    const html = renderPrintProfileHTML(buildPrintSnapshot({ status: 'ready', result }, 'A2'))
    expect(html).toContain('No data')
    expect(html).toContain('Unavailable in this result')
    expect(html).toContain('no-data')
  })

  it('disallows print until the profile is ready with a result', () => {
    expect(getPrintAvailability({ status: 'empty', result: null })).toEqual({ available: false, reason: 'Profile is not ready.' })
    expect(getPrintAvailability({ status: 'updating', result })).toEqual({ available: false, reason: 'Profile is not ready.' })
    expect(getPrintAvailability({ status: 'ready', result })).toEqual({ available: true, reason: '' })
  })
})
