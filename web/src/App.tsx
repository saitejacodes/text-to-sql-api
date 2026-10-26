import { NavLink, Route, Routes } from 'react-router-dom'
import { About } from './pages/About'
import { Home } from './pages/Home'

const link = ({ isActive }: { isActive: boolean }) =>
  `rounded px-2 py-1 focus-visible:outline-2 focus-visible:outline-indigo-500 ${
    isActive ? 'font-semibold text-indigo-700 dark:text-indigo-300' : 'text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100'
  }`

export default function App() {
  return (
    <div className="min-h-screen bg-white text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      <header className="border-b border-slate-200 dark:border-slate-800">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-2 px-4 py-3">
          <div>
            <p className="text-lg font-bold">AskSQL</p>
            <p className="text-sm text-slate-500 dark:text-slate-400">Ask a database in plain English, safely.</p>
          </div>
          <nav aria-label="Main" className="flex items-center gap-2 text-sm">
            <NavLink to="/" end className={link}>Home</NavLink>
            <NavLink to="/about" className={link}>About</NavLink>
            <a
              href="https://github.com/saitejacodes/text-to-sql-api"
              className="rounded px-2 py-1 text-slate-600 hover:text-slate-900 focus-visible:outline-2 focus-visible:outline-indigo-500 dark:text-slate-400 dark:hover:text-slate-100"
            >
              GitHub
            </a>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/about" element={<About />} />
        </Routes>
      </main>
    </div>
  )
}
