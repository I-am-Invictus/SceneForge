import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { Sidebar } from './components/Sidebar'
import { GeneralGeneration } from './pages/GeneralGeneration'
import { ImageModification } from './pages/ImageModification'
import { CharacterSwap } from './pages/CharacterSwap'
import { Characters } from './pages/Characters'
import { Scenes } from './pages/Scenes'
import { Starred } from './pages/Starred'
import { Gallery } from './pages/Gallery'
import { GalleryDetail } from './pages/GalleryDetail'
import { History } from './pages/History'
import { Workflows } from './pages/Workflows'
import { SettingsPage } from './pages/SettingsPage'
import { DeveloperOptions } from './pages/DeveloperOptions'
import { Queue } from './pages/Queue'
import { AssetDetailPage } from './components/AssetDetailPage'

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
            <Route path="/queue" element={<Queue />} />
            <Route path="/characters" element={<Characters />} />
            <Route
              path="/characters/:id"
              element={<AssetDetailPage kind="character" />}
            />
            <Route path="/scenes" element={<Scenes />} />
            <Route
              path="/scenes/:id"
              element={<AssetDetailPage kind="scene" />}
            />
            <Route path="/starred" element={<Starred />} />
            <Route path="/galleries" element={<Gallery />} />
            <Route path="/galleries/:id" element={<GalleryDetail />} />
            <Route path="/history" element={<History />} />
            <Route path="/workflows" element={<Workflows />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/developer" element={<DeveloperOptions />} />
            <Route path="*" element={<Navigate to="/generate" replace />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
