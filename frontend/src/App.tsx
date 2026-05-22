import { Navigate, Route, Routes } from 'react-router-dom'
import { AppLayout } from './components/layout/AppLayout'
import { AnalysisPage } from './pages/AnalysisPage'
import { ChatPage } from './pages/ChatPage'
import { Health } from './pages/Health'
import { History } from './pages/History'
import { Overview } from './pages/Overview'
import { Performance } from './pages/Performance'
import { Schedule } from './pages/Schedule'

function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<Navigate to="/overview" replace />} />
        <Route path="/overview" element={<Overview />} />
        <Route path="/chat" element={<ChatPage />} />
        <Route path="/analysis" element={<AnalysisPage />} />
        <Route path="/schedule" element={<Schedule />} />
        <Route path="/progress" element={<Performance />} />
        <Route path="/health" element={<Health />} />
        <Route path="/history" element={<History />} />
        <Route path="*" element={<Navigate to="/overview" replace />} />
      </Route>
    </Routes>
  )
}

export default App
