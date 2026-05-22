import { useEffect, useState } from 'react'
import { Outlet } from 'react-router-dom'
import { ProfileDrawer } from './ProfileDrawer'
import { Sidebar } from './Sidebar'

export const AppLayout = () => {
  const [isProfileOpen, setIsProfileOpen] = useState(false)
  const [theme, setTheme] = useState<'dark' | 'light'>(() => {
    const stored = localStorage.getItem('athletecore-theme')
    return stored === 'light' ? 'light' : 'dark'
  })

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('athletecore-theme', theme)
  }, [theme])

  return (
    <>
      <div className="app-backdrop" aria-hidden />
      <div className="grain" aria-hidden />
      <div className="relative grid h-screen grid-cols-[244px_1fr]">
        <Sidebar
          onOpenProfile={() => setIsProfileOpen(true)}
          theme={theme}
          onToggleTheme={() =>
            setTheme((prev) => (prev === 'dark' ? 'light' : 'dark'))
          }
        />
        <main className="relative h-screen overflow-hidden">
          <Outlet />
        </main>
        <ProfileDrawer isOpen={isProfileOpen} onClose={() => setIsProfileOpen(false)} />
      </div>
    </>
  )
}
