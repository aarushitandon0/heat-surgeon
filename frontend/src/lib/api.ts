// REST and WebSocket endpoints (SPEC.md §7). The Vite dev server proxies /api and /ws to the backend.
// Errors carry the backend's own detail string; nothing here substitutes data.

import type {
  CalibrationRequest,
  CalibrationResult,
  OptimizationResult,
  OptimizeJobHandle,
  OptimizeRequest,
  StreetGeometry,
  StreetSummary,
  ThermalGrid,
} from '../types/contracts.ts'

export const BACKEND_UNREACHABLE =
  'The backend did not respond. Start it with: cd backend && uvicorn app.main:app --reload --port 8000'

export class ApiError extends Error {}

function detailMessage(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown } | null)?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    // pydantic validation errors: [{ loc: [...], msg }]
    return detail
      .map((item: { loc?: unknown[]; msg?: string }) => `${(item.loc ?? []).slice(1).join('.')}: ${item.msg ?? ''}`)
      .join('; ')
  }
  return `The backend answered ${status} with no explanation.`
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, init)
  } catch {
    throw new ApiError(BACKEND_UNREACHABLE)
  }
  const text = await response.text()
  let body: unknown = null
  try {
    body = text ? JSON.parse(text) : null
  } catch {
    body = null
  }
  if (!response.ok) {
    // The dev proxy answers with an empty or non-JSON body when the backend is down.
    if (body === null) throw new ApiError(BACKEND_UNREACHABLE)
    throw new ApiError(detailMessage(body, response.status))
  }
  return body as T
}

function postJson<T>(path: string, payload: unknown): Promise<T> {
  return request<T>(path, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(payload) })
}

export const api = {
  streets: () => request<StreetSummary[]>('/api/streets'),
  geometry: (streetId: string) => request<StreetGeometry>(`/api/street/${encodeURIComponent(streetId)}/geometry`),
  thermal: (streetId: string, scope: 'street' | 'window') =>
    request<ThermalGrid>(`/api/street/${encodeURIComponent(streetId)}/thermal?scope=${scope}`),
  calibrate: (streetId: string, body: CalibrationRequest) =>
    postJson<CalibrationResult>(`/api/street/${encodeURIComponent(streetId)}/calibrate`, body),
  optimize: (streetId: string, body: OptimizeRequest) =>
    postJson<OptimizeJobHandle>(`/api/street/${encodeURIComponent(streetId)}/optimize`, body),
  result: (resultUrl: string) => request<OptimizationResult>(resultUrl),
}

export function websocketUrl(path: string): string {
  const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${scheme}://${window.location.host}${path}`
}

export function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}
