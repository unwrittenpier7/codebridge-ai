import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'
import HealthIndicator from './HealthIndicator.jsx'

const NAV_ITEMS = [
  { to: '/dashboard', label: 'Dashboard' },
  { to: '/workspace', label: 'Workspace' },
  { to: '/history', label: 'History' },
]

export default function AppLayout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const handleLogout = () => {
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <div className="flex h-screen overflow-hidden bg-surface-950">
      <aside className="hidden w-56 flex-col border-r border-surface-800 bg-surface-900 p-4 md:flex">
        <NavLink to="/dashboard" className="mb-6 block">
          <span className="text-lg font-semibold text-slate-100">CodeBridge</span>
          <span className="ml-1 text-lg font-semibold text-accent">AI</span>
          <p className="text-xs text-slate-500">Convert. Test. Verify.</p>
        </NavLink>
        <nav className="flex flex-col gap-1">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `rounded-md px-3 py-2 text-sm transition ${
                  isActive
                    ? 'bg-surface-800 text-slate-100'
                    : 'text-slate-400 hover:bg-surface-800 hover:text-slate-200'
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto space-y-3">
          <HealthIndicator />
          <div className="border-t border-surface-800 pt-3">
            <p className="truncate text-sm text-slate-300">{user?.name}</p>
            <p className="truncate text-xs text-slate-500">{user?.email}</p>
            <button type="button" className="btn mt-2 w-full" onClick={handleLogout}>
              Log out
            </button>
          </div>
        </div>
      </aside>
      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-[1600px] p-4 md:p-6">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
