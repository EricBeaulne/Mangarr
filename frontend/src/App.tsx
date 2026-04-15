import { Navigate, Route, Routes } from 'react-router-dom';
import { Sidebar } from './components/layout/Sidebar';
import { Library } from './pages/Library';
import { AddSeries } from './pages/AddSeries';
import { RootFolders } from './pages/RootFolders';
import { Scanner } from './pages/Scanner';
import { SeriesDetail } from './pages/SeriesDetail';
import { Wanted } from './pages/Wanted';

function SettingsPlaceholder() {
  return (
    <div className="flex flex-col h-full">
      <div className="h-14 bg-mangarr-card border-b border-mangarr-border flex items-center px-6">
        <h1 className="text-mangarr-text font-semibold text-lg">Settings</h1>
      </div>
      <div className="p-6 text-mangarr-muted text-sm">
        Settings UI is coming next.
      </div>
    </div>
  );
}

export default function App() {
  return (
    <div className="min-h-screen bg-mangarr-bg text-mangarr-text">
      <Sidebar />
      <main className="ml-60 min-h-screen">
        <Routes>
          <Route path="/" element={<Library />} />
          <Route path="/add" element={<AddSeries />} />
          <Route path="/settings/folders" element={<RootFolders />} />
          <Route path="/scanner" element={<Scanner />} />
          <Route path="/series/:id" element={<SeriesDetail />} />
          <Route path="/wanted" element={<Wanted />} />
          <Route path="/settings" element={<SettingsPlaceholder />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
