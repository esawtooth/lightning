import React, { useState } from 'react'
import { Routes, Route } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import Dashboard from './pages/Dashboard'
import Context from './pages/Context'
import Chat from './pages/Chat'
import Tasks from './pages/Tasks'
import Events from './pages/Events'
import Notifications from './pages/Notifications'
import Providers from './pages/Providers'
import Settings from './pages/Settings'
import Instructions from './pages/Instructions'

function App() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)

  return (
    <div className="min-h-screen bg-gray-50 flex">
      <Sidebar 
        collapsed={sidebarCollapsed} 
        onToggle={() => setSidebarCollapsed(!sidebarCollapsed)} 
      />
      
      <main className={`flex-1 transition-all duration-300 ${
        sidebarCollapsed ? 'ml-16' : 'ml-64'
      }`}>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/context" element={<Context />} />
          <Route path="/chat" element={<Chat />} />
          <Route path="/chat/new" element={<Chat />} />
          <Route path="/tasks" element={<Tasks />} />
          <Route path="/events" element={<Events />} />
          <Route path="/notifications" element={<Notifications />} />
          <Route path="/providers" element={<Providers />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/instructions" element={<Instructions />} />
        </Routes>
      </main>
    </div>
  )
}

export default App