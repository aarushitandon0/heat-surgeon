// The instrument's state machine. The stage numbers are the real pipeline sequence (SPEC.md §9.2):
// locate a street, diagnose it from real data, optimize a layout, operate on the result.

import { create } from 'zustand'
import { ApiError, BACKEND_UNREACHABLE, liveSource, loadManifest, messageOf, replaySource, type DataSource } from '../lib/api.ts'
import { replayForced, type SnapshotManifest } from '../lib/replay.ts'
import { DEFAULT_REQUEST } from '../lib/search.ts'
import type {
  CalibrationResult,
  Intervention,
  OptimizationResult,
  OptimizeJobHandle,
  OptimizeProgress,
  OptimizeRequest,
  StreetBasemap,
  StreetGeometry,
  StreetRanking,
  StreetSummary,
  ThermalGrid,
} from '../types/contracts.ts'

export type StageId = 'locate' | 'diagnose' | 'optimize' | 'operate'

export const STAGES: readonly { id: StageId; number: string; name: string }[] = [
  { id: 'locate', number: '00', name: 'Locate' },
  { id: 'diagnose', number: '01', name: 'Diagnose' },
  { id: 'optimize', number: '02', name: 'Optimize' },
  { id: 'operate', number: '03', name: 'Operate' },
]

export type Load<T> =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; data: T }
  | { status: 'error'; message: string }

export type JobStatus = 'idle' | 'starting' | 'searching' | 'loading_result' | 'done' | 'error'

export interface JobState {
  status: JobStatus
  handle: OptimizeJobHandle | null
  progress: OptimizeProgress[]
  /** The most recent layout_preview; progress messages carry null when the best layout did not improve. */
  preview: Intervention[] | null
  socketOpen: boolean
  message: string | null
}

/**
 * live: every response comes from the backend.
 * replay: every response is a recording of that backend's real responses (lib/replay.ts), and the header says so.
 * `forced` is a replay-only build or ?replay; `backend_unreachable` is the fallback when nothing answered.
 */
export type DataMode =
  | { kind: 'live' }
  | { kind: 'replay'; manifest: SnapshotManifest; reason: 'forced' | 'backend_unreachable' }

/**
 * Coated cells used when coating is switched on: the Day 4 run settings in docs/methodology.md.
 * Coating is unpriced and carries the published coefficient band, so it is off by default (Day 7).
 */
export const COATED_CELLS_WHEN_ON = 150

const CALIBRATION_REQUEST = { holdout_fraction: 0.2, seed: 42 }

const IDLE_JOB: JobState = { status: 'idle', handle: null, progress: [], preview: null, socketOpen: false, message: null }

interface State {
  stage: StageId
  /** The data panel is hidden so the viewport can go wide. Kept across stage changes for the session. */
  panelCollapsed: boolean
  /** Data panel width set by dragging its edge; null keeps the default --panel-width. Kept for the session. */
  panelWidth_px: number | null
  dataMode: DataMode
  streets: Load<StreetSummary[]>
  /** Streets inside the calibrated windows, ranked offline by `python -m app.ranking`. */
  ranking: Load<StreetRanking>
  /** rankedKey() of the ranked street open in stage 00, if any. */
  rankedKey: string | null
  street: StreetSummary | null
  geometry: Load<StreetGeometry>
  /** OSM roads and footprints for the window, and the city locator. Display context, never data. */
  basemap: Load<StreetBasemap>
  thermalWindow: Load<ThermalGrid>
  thermalStreet: Load<ThermalGrid>
  calibration: Load<CalibrationResult>
  request: OptimizeRequest
  job: JobState
  result: OptimizationResult | null
}

interface Actions {
  loadStreets: () => Promise<void>
  loadRanking: () => Promise<void>
  selectRanked: (key: string | null) => void
  selectStreet: (street: StreetSummary) => void
  setRequest: (patch: Partial<OptimizeRequest>) => void
  startOptimize: () => Promise<void>
  goTo: (stage: StageId) => void
  togglePanel: () => void
  setPanelWidth: (width_px: number) => void
}

export type Store = State & Actions

// Tokens discard responses that arrive after the user has moved on.
let streetSession = 0
let jobSession = 0
let source: DataSource = liveSource
let stopStream: (() => void) | null = null

function closeStream() {
  stopStream?.()
  stopStream = null
}

type LoadKey = 'geometry' | 'basemap' | 'thermalWindow' | 'thermalStreet' | 'calibration'

function track<K extends LoadKey>(key: K, promise: Promise<State[K] extends Load<infer T> ? T : never>, token: number) {
  promise.then(
    (data) => {
      if (token === streetSession) useStore.setState({ [key]: { status: 'ready', data } } as Partial<State>)
    },
    (error) => {
      if (token === streetSession) useStore.setState({ [key]: { status: 'error', message: messageOf(error) } } as Partial<State>)
    },
  )
}

function setJob(patch: Partial<JobState>) {
  useStore.setState((state) => ({ job: { ...state.job, ...patch } }))
}

export function stageAvailable(state: State, stage: StageId): boolean {
  switch (stage) {
    case 'locate':
      return true
    case 'diagnose':
      return state.street !== null
    case 'optimize':
      return state.job.status !== 'idle'
    case 'operate':
      return state.result !== null
  }
}

export const useStore = create<Store>()((set, get) => ({
  stage: 'locate',
  panelCollapsed: false,
  panelWidth_px: null,
  dataMode: { kind: 'live' },
  streets: { status: 'idle' },
  ranking: { status: 'idle' },
  rankedKey: null,
  street: null,
  geometry: { status: 'idle' },
  basemap: { status: 'idle' },
  thermalWindow: { status: 'idle' },
  thermalStreet: { status: 'idle' },
  calibration: { status: 'idle' },
  request: DEFAULT_REQUEST,
  job: IDLE_JOB,
  result: null,

  loadStreets: async () => {
    set({ streets: { status: 'loading' } })
    const base = import.meta.env.BASE_URL
    const forced = replayForced(window.location.search, import.meta.env.VITE_REPLAY_ONLY === 'true')

    if (!forced) {
      try {
        const streets = await liveSource.streets()
        source = liveSource
        set({ dataMode: { kind: 'live' }, streets: { status: 'ready', data: streets } })
        return
      } catch (error) {
        // Only a backend that did not answer falls back. A backend that answered with an error shows that error.
        if (!(error instanceof ApiError && error.unreachable)) {
          set({ streets: { status: 'error', message: messageOf(error) } })
          return
        }
      }
    }

    try {
      const manifest = await loadManifest(base)
      const replay = replaySource(base, manifest)
      const recordedIds = new Set(manifest.streets.map((s) => s.id))
      const streets = (await replay.streets()).filter((s) => recordedIds.has(s.id))
      source = replay
      set({
        dataMode: { kind: 'replay', manifest, reason: forced ? 'forced' : 'backend_unreachable' },
        streets: { status: 'ready', data: streets },
        request: manifest.optimize_request,
      })
    } catch (error) {
      set({
        streets: {
          status: 'error',
          message: forced ? messageOf(error) : `${BACKEND_UNREACHABLE} No recording is available to replay instead.`,
        },
      })
    }
  },

  // Called once the streets have loaded, so `source` is already the live backend or the recording.
  loadRanking: async () => {
    set({ ranking: { status: 'loading' } })
    try {
      set({ ranking: { status: 'ready', data: await source.ranking() } })
    } catch (error) {
      set({ ranking: { status: 'error', message: messageOf(error) } })
    }
  },

  selectRanked: (key) => set({ rankedKey: key }),

  selectStreet: (street) => {
    closeStream()
    const token = ++streetSession
    jobSession++
    set({
      stage: 'diagnose',
      street,
      geometry: { status: 'loading' },
      basemap: { status: 'loading' },
      thermalWindow: { status: 'loading' },
      thermalStreet: { status: 'loading' },
      calibration: { status: 'loading' },
      job: IDLE_JOB,
      result: null,
    })
    // The window grid drives the acquisition decode; the street grid gives the street's measured mean.
    track('thermalWindow', source.thermal(street.id, 'window'), token)
    track('thermalStreet', source.thermal(street.id, 'street'), token)
    track('calibration', source.calibrate(street.id, CALIBRATION_REQUEST), token)
    // Buildings for the stage 03 scene; small, so fetched up front with the rest.
    track('geometry', source.geometry(street.id), token)
    // Streets and footprints under the stage 01 tile and over the stage 02 and 03 design grid.
    track('basemap', source.basemap(street.id), token)
  },

  setRequest: (patch) => set((state) => ({ request: { ...state.request, ...patch } })),

  startOptimize: async () => {
    const { street, calibration, request } = get()
    if (!street || calibration.status !== 'ready') return
    closeStream()
    const token = ++jobSession
    set({ stage: 'optimize', job: { ...IDLE_JOB, status: 'starting' }, result: null })

    let handle: OptimizeJobHandle
    try {
      handle = await source.optimize(street.id, request)
    } catch (error) {
      if (token === jobSession) setJob({ status: 'error', message: messageOf(error) })
      return
    }
    if (token !== jobSession) return
    setJob({ status: 'searching', handle })

    let finished = false
    stopStream = source.stream(street.id, handle, {
      onOpen: () => {
        if (token === jobSession) setJob({ socketOpen: true })
      },
      onMessage: (message) => {
        if (token !== jobSession) return
        if (message.type === 'progress') {
          const { job } = get()
          setJob({ progress: [...job.progress, message], preview: message.layout_preview ?? job.preview })
        } else if (message.type === 'done') {
          finished = true
          void loadResult(message.result_url, token)
        } else {
          finished = true
          setJob({ status: 'error', message: message.message })
        }
      },
      onClose: () => {
        if (token !== jobSession) return
        stopStream = null
        setJob({ socketOpen: false })
        if (!finished) setJob({ status: 'error', message: 'The progress stream closed before the search finished.' })
      },
    })
  },

  goTo: (stage) => {
    if (stageAvailable(get(), stage)) set({ stage })
  },

  togglePanel: () => set((state) => ({ panelCollapsed: !state.panelCollapsed })),

  setPanelWidth: (width_px) => set({ panelWidth_px: width_px }),
}))

async function loadResult(resultUrl: string, token: number) {
  setJob({ status: 'loading_result' })
  try {
    const result = await source.result(resultUrl)
    if (token !== jobSession) return
    useStore.setState({ result, stage: 'operate' })
    setJob({ status: 'done' })
  } catch (error) {
    if (token === jobSession) setJob({ status: 'error', message: messageOf(error) })
  }
}
