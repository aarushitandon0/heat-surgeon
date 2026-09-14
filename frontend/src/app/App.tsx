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

  return (
    <div className="app">
      <Header />
      <main className="workspace">
        {stage === 'locate' && <Workspace panel={<LocatePanel />} viewport={<LocateViewport />} />}
        {stage === 'diagnose' && street && <Workspace panel={<DiagnosePanel />} viewport={<DiagnoseViewport />} />}
        {stage === 'optimize' && street && <Workspace panel={<OptimizePanel />} viewport={<OptimizeViewport />} />}
        {stage === 'operate' && result && <OperateStage key={result.job_id} />}
      </main>
    </div>
  )
}
