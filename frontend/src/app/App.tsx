import type { ReactNode } from 'react'
import { DiagnosePanel, DiagnoseViewport } from '../stages/Diagnose.tsx'
import { LocatePanel, LocateViewport } from '../stages/Locate.tsx'
import { OperateStage } from '../stages/Operate.tsx'
import { OptimizePanel, OptimizeViewport } from '../stages/Optimize.tsx'
import { useStore } from '../store/store.ts'
import { Header } from './Header.tsx'
import './app.css'

function Workspace({ panel, viewport }: { panel: ReactNode; viewport: ReactNode }) {
  return (
    <>
      <aside className="panel" aria-label="Data">
        {panel}
      </aside>
      <section className="viewport" aria-label="Viewport">
        {viewport}
      </section>
    </>
  )
}

export default function App() {
  const stage = useStore((s) => s.stage)
  const street = useStore((s) => s.street)
  const result = useStore((s) => s.result)
  const panelCollapsed = useStore((s) => s.panelCollapsed)

  return (
    <div className="app">
      <Header />
      <main className={panelCollapsed ? 'workspace workspace-collapsed' : 'workspace'}>
        {/* Keyed by stage so each panel gets a fresh element and opens scrolled to the top, never mid-content. */}
        {stage === 'locate' && <Workspace key="locate" panel={<LocatePanel />} viewport={<LocateViewport />} />}
        {stage === 'diagnose' && street && <Workspace key={`diagnose-${street.id}`} panel={<DiagnosePanel />} viewport={<DiagnoseViewport />} />}
        {stage === 'optimize' && street && <Workspace key={`optimize-${street.id}`} panel={<OptimizePanel />} viewport={<OptimizeViewport />} />}
        {stage === 'operate' && result && <OperateStage key={result.job_id} />}
      </main>
    </div>
  )
}
