// The instrument's state machine. The stage numbers are the real pipeline sequence (SPEC.md §9.2):
// locate a street, diagnose it from real data, optimize a layout, operate on the result.

import { create } from 'zustand'
import { api, messageOf, websocketUrl } from '../lib/api.ts'
import type {
  CalibrationResult,
  Intervention,
  OptimizationResult,
  OptimizeJobHandle,
  OptimizeMessage,
  OptimizeProgress,
  OptimizeRequest,
  StreetGeometry,
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

/** The Day 4 run settings in docs/methodology.md: 20 trees, 150 coated cells, population 120, 400 generations. */
export const DEFAULT_REQUEST: OptimizeRequest = {
  trees_max: 20,
  reflective_cells_max: 150,
  budget_inr_max: null,
  generations: 400,
  population: 120,
  cost_weight_c_per_inr: 0,
  run_baselines: true,
  seed: 42,
}

const IDLE_JOB: JobState = { status: 'idle', handle: null, progress: [], preview: null, socketOpen: false, message: null }

interface State {
  stage: StageId
  streets: Load<StreetSummary[]>
  street: StreetSummary | null
  geometry: Load<StreetGeometry>
  thermalWindow: Load<ThermalGrid>
  thermalStreet: Load<ThermalGrid>
  calibration: Load<CalibrationResult>
  request: OptimizeRequest
  job: JobState
  result: OptimizationResult | null
}

interface Actions {
  loadStreets: () => Promise<void>
  selectStreet: (street: StreetSummary) => void
  setRequest: (patch: Partial<OptimizeRequest>) => void
  startOptimize: () => Promise<void>
  goTo: (stage: StageId) => void
}

export type Store = State & Actions

// Tokens discard responses that arrive after the user has moved on.
let streetSession = 0
let jobSession = 0
let socket: WebSocket | null = null

function closeSocket() {
  if (!socket) return
  socket.onopen = socket.onmessage = socket.onclose = socket.onerror = null
  socket.close()
  socket = null
}

type LoadKey = 'geometry' | 'thermalWindow' | 'thermalStreet' | 'calibration'

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
  streets: { status: 'idle' },
  street: null,
  geometry: { status: 'idle' },
  thermalWindow: { status: 'idle' },
  thermalStreet: { status: 'idle' },
  calibration: { status: 'idle' },
  request: DEFAULT_REQUEST,
  job: IDLE_JOB,
  result: null,

  loadStreets: async () => {
    set({ streets: { status: 'loading' } })
    try {
      set({ streets: { status: 'ready', data: await api.streets() } })
    } catch (error) {
      set({ streets: { status: 'error', message: messageOf(error) } })
    }
  },

  selectStreet: (street) => {
    closeSocket()
    const token = ++streetSession
    jobSession++
    set({
      stage: 'diagnose',
      street,
      geometry: { status: 'loading' },
      thermalWindow: { status: 'loading' },
      thermalStreet: { status: 'loading' },
      calibration: { status: 'loading' },
      job: IDLE_JOB,
      result: null,
    })
    // The window grid drives the acquisition decode; the street grid gives the street's measured mean.
    track('thermalWindow', api.thermal(street.id, 'window'), token)
    track('thermalStreet', api.thermal(street.id, 'street'), token)
    track('calibration', api.calibrate(street.id, { holdout_fraction: 0.2, seed: 42 }), token)
    // Buildings for the stage 03 scene; small, so fetched up front with the rest.
    track('geometry', api.geometry(street.id), token)
  },

  setRequest: (patch) => set((state) => ({ request: { ...state.request, ...patch } })),

  startOptimize: async () => {
    const { street, calibration, request } = get()
    if (!street || calibration.status !== 'ready') return
    closeSocket()
    const token = ++jobSession
    set({ stage: 'optimize', job: { ...IDLE_JOB, status: 'starting' }, result: null })

    let handle: OptimizeJobHandle
    try {
      handle = await api.optimize(street.id, request)
    } catch (error) {
      if (token === jobSession) setJob({ status: 'error', message: messageOf(error) })
      return
    }
    if (token !== jobSession) return
    setJob({ status: 'searching', handle })

    let finished = false
    const ws = new WebSocket(websocketUrl(handle.ws_url))
    socket = ws
    ws.onopen = () => {
      if (token === jobSession) setJob({ socketOpen: true })
    }
    ws.onmessage = (event: MessageEvent<string>) => {
      if (token !== jobSession) return
      const message = JSON.parse(event.data) as OptimizeMessage
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
    }
    ws.onclose = () => {
      if (token !== jobSession) return
      socket = null
      setJob({ socketOpen: false })
      if (!finished) setJob({ status: 'error', message: 'The progress stream closed before the search finished.' })
    }
  },

  goTo: (stage) => {
    if (stageAvailable(get(), stage)) set({ stage })
  },
}))

async function loadResult(resultUrl: string, token: number) {
  setJob({ status: 'loading_result' })
  try {
    const result = await api.result(resultUrl)
    if (token !== jobSession) return
    useStore.setState({ result, stage: 'operate' })
    setJob({ status: 'done' })
  } catch (error) {
    if (token === jobSession) setJob({ status: 'error', message: messageOf(error) })
  }
}
