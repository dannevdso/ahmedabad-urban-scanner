import { describe, expect, it } from 'vitest'

import { contextBadge, contextNote, resolveContext, resolveItemContextKey } from './context.js'
import { indicators } from './indicators.js'
import { PLANX_OVERLAYS, SPACE_SYNTAX_CONTEXT_KEY } from './planx_layers.js'

const metadata = {
  contexts: {
    'full-study-current': { scopeLabel: 'Full-study current', statusLabel: 'Current study', temporalLabel: '2026', caveat: 'Full-study current result.' },
    'scope-unverified': { scopeLabel: 'Scope not verified', statusLabel: 'Unverified', temporalLabel: '', caveat: 'Scope and provenance have not been verified.' },
  },
}

describe('context resolution', () => {
  it('resolves explicit metadata and falls back visibly for unknown keys', () => {
    expect(resolveContext(metadata, 'full-study-current').scopeLabel).toBe('Full-study current')
    expect(resolveContext(metadata, 'missing').scopeLabel).toBe('Scope not verified')
  })

  it('generates text badges and concise notes', () => {
    expect(contextBadge(metadata, 'full-study-current')).toBe('Full-study current · Current study')
    expect(contextNote(metadata, 'full-study-current')).toContain('Full-study current result.')
    expect(contextNote(metadata, 'missing')).toContain('Scope, provenance, and temporal status are not verified.')
  })

  it('resolves metadata assignments before static item fallbacks', () => {
    const item = { key: 'heatRisk', contextKey: 'full-study-current' }
    expect(resolveItemContextKey({ overlay_contexts: { heatRisk: 'current-study-proxy' } }, item, 'overlay')).toBe('current-study-proxy')
    expect(resolveItemContextKey({}, item, 'overlay')).toBe('full-study-current')
  })

  it('fills incomplete metadata contexts with visible fallback fields', () => {
    const incomplete = { contexts: { broken: { scopeLabel: 'Broken' } } }
    expect(contextBadge(incomplete, 'broken')).toBe('Broken · Unverified')
    expect(contextNote(incomplete, 'broken')).toBe('Temporal status not verified — Scope, provenance, and temporal status are not verified.')
  })

  it('assigns context keys to every indicator and overlay control', () => {
    expect(Object.values(indicators).every((indicator) => indicator.contextKey)).toBe(true)
    expect(PLANX_OVERLAYS.every((overlay) => overlay.contextKey)).toBe(true)
    expect(PLANX_OVERLAYS.find(({ key }) => key === 'heatRisk').contextKey).toBe('current-study-proxy')
    expect(PLANX_OVERLAYS.some(({ key }) => key === 'transitAccess')).toBe(false)

    expect(SPACE_SYNTAX_CONTEXT_KEY).toBe('supplied-external')
  })
})
