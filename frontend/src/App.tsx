import { Navigate, Route, Routes } from 'react-router-dom'
import { AppLayout } from './components/layout/AppLayout'
import { AnalysisPage } from './pages/AnalysisPage'
import { VideoAnalysisPage } from './pages/VideoAnalysisPage'
import { VideoDebugPage } from './pages/VideoDebugPage'
import { ChatPage } from './pages/ChatPage'
import { Health } from './pages/Health'
import { History } from './pages/History'
import { Home } from './pages/Home'
import { Performance } from './pages/Performance'
import { Schedule } from './pages/Schedule'

function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<Navigate to="/home" replace />} />
        <Route path="/home" element={<Home />} />
        <Route path="/overview" element={<Navigate to="/home" replace />} />
        <Route path="/chat" element={<ChatPage />} />
        <Route path="/analysis" element={<AnalysisPage />} />
        <Route path="/analysis/video" element={<VideoAnalysisPage />} />
        <Route path="/analysis/video/:videoId/debug" element={<VideoDebugPage />} />
        <Route path="/schedule" element={<Schedule />} />
        <Route path="/progress" element={<Performance />} />
        <Route path="/health" element={<Health />} />
        <Route path="/history" element={<History />} />
        <Route path="*" element={<Navigate to="/home" replace />} />
      </Route>
    </Routes>
  )
}

export default App
