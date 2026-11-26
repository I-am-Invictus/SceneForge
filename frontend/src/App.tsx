import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { Sidebar } from './components/Sidebar'
import { GeneralGeneration } from './pages/GeneralGeneration'
import { ImageModification } from './pages/ImageModification'
import { CharacterSwap } from './pages/CharacterSwap'
import { Characters } from './pages/Characters'
import { Scenes } from './pages/Scenes'
import { Starred } from './pages/Starred'
import { History } from './pages/History'
import { Workflows } from './pages/Workflows'
import { SettingsPage } from './pages/SettingsPage'

export default function App() {
  return (
    <BrowserRouter>
      <div className="app">
        <Sidebar />
        <main className="main">
          <Routes>
            <Route path="/" element={<Navigate to="/generate" replace />} />
            <Route path="/generate" element={<GeneralGeneration />} />
            <Route path="/modify" element={<ImageModification />} />
            <Route path="/swap" element={<CharacterSwap />} />
            <Route path="/characters" element={<Characters />} />
            <Route path="/scenes" element={<Scenes />} />
            <Route path="/starred" element={<Starred />} />
            <Route path="/history" element={<History />} />
            <Route path="/workflows" element={<Workflows />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="*" element={<Navigate to="/generate" replace />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
