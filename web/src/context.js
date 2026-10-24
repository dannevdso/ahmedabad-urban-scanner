const FALLBACK_CONTEXT = {
  scopeLabel: 'Scope not verified',
  statusLabel: 'Unverified',
  temporalLabel: 'Temporal status not verified',
  caveat: 'Scope, provenance, and temporal status are not verified.',
}

export function resolveContext(metadata, contextKey) {
  const context = metadata?.contexts?.[contextKey]
  return Object.fromEntries(Object.keys(FALLBACK_CONTEXT).map((field) => [field, context?.[field] || FALLBACK_CONTEXT[field]]))
}

export function resolveItemContextKey(metadata, item, collection) {
  return metadata?.[`${collection}_contexts`]?.[item?.key] || item?.contextKey || 'scope-unverified'
}

export function contextBadge(metadata, contextKey) {
  const context = resolveContext(metadata, contextKey)
  return [context.scopeLabel, context.statusLabel].filter(Boolean).join(' · ')
}

export function contextNote(metadata, contextKey) {
  const context = resolveContext(metadata, contextKey)
  return [context.temporalLabel, context.caveat].filter(Boolean).join(' — ')
}

export { FALLBACK_CONTEXT }
