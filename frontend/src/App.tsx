import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Config } from './pages/Config';
import { Dashboard } from './pages/Dashboard';
import './App.css';

const queryClient = new QueryClient();

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <div className="app">
          <header className="app-header">
            <h1>Video to Docs</h1>
            <p>Transcribe video/audio via Deepgram, export to Google Docs or Markdown</p>
          </header>

          <nav className="nav">
            <NavLink to="/" end className={({ isActive }) => (isActive ? 'active' : '')}>
              Transcribe
            </NavLink>
            <NavLink to="/config" className={({ isActive }) => (isActive ? 'active' : '')}>
              Settings
            </NavLink>
          </nav>

          <main>
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/config" element={<Config />} />
            </Routes>
          </main>
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
