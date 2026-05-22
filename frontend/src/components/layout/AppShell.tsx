import { Outlet } from 'react-router-dom'
import { RightPanel } from './RightPanel'
import { Sidebar } from './Sidebar'

export const AppShell = () => {
  return (
    <div className="grid h-screen grid-cols-[220px_1fr_280px] bg-[var(--bg)]">
      <Sidebar onOpenProfile={() => {}} theme="dark" onToggleTheme={() => {}} />
      <main className="h-screen overflow-hidden">
        <Outlet />
      </main>
      <RightPanel />
    </div>
  )
}
