import { Navigate, Route, Routes } from 'react-router-dom'
import AppLayout from './components/AppLayout.jsx'
import ProtectedRoute from './components/ProtectedRoute.jsx'
import Landing from './pages/Landing.jsx'
import Login from './pages/Login.jsx'
import Register from './pages/Register.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Workspace from './pages/Workspace.jsx'
import History from './pages/History.jsx'
import MigrationDetails from './pages/MigrationDetails.jsx'
import VerificationResults from './pages/VerificationResults.jsx'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/workspace" element={<Workspace />} />
        <Route path="/workspace/:migrationId" element={<Workspace />} />
        <Route path="/history" element={<History />} />
        <Route path="/migrations/:migrationId" element={<MigrationDetails />} />
        <Route path="/migrations/:migrationId/results" element={<VerificationResults />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
