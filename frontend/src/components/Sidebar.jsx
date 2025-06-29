import React, { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { 
  Bars3Icon,
  ChatBubbleLeftRightIcon,
  DocumentTextIcon,
  BookOpenIcon,
  ListBulletIcon,
  BellIcon,
  CpuChipIcon,
  Cog6ToothIcon,
  ArrowRightOnRectangleIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  PlusIcon,
  RectangleStackIcon
} from '@heroicons/react/24/outline'

const Sidebar = ({ collapsed, onToggle }) => {
  const location = useLocation()
  const [chatExpanded, setChatExpanded] = useState(false)
  const [systemExpanded, setSystemExpanded] = useState(false)

  const isActive = (path) => location.pathname === path

  const navItems = [
    {
      name: 'Chat',
      icon: ChatBubbleLeftRightIcon,
      expandable: true,
      expanded: chatExpanded,
      onToggle: () => setChatExpanded(!chatExpanded),
      children: [
        { name: 'New Chat', path: '/chat/new', icon: PlusIcon }
      ]
    },
    {
      name: 'My Context',
      path: '/context',
      icon: DocumentTextIcon
    },
    {
      name: 'Instructions',
      path: '/instructions',
      icon: BookOpenIcon
    },
    {
      name: 'System Overview',
      icon: RectangleStackIcon,
      expandable: true,
      expanded: systemExpanded,
      onToggle: () => setSystemExpanded(!systemExpanded),
      children: [
        { name: 'Dashboard', path: '/dashboard', icon: RectangleStackIcon },
        { name: 'Tasks', path: '/tasks', icon: ListBulletIcon },
        { name: 'Events', path: '/events', icon: CpuChipIcon },
        { name: 'Notifications', path: '/notifications', icon: BellIcon },
        { name: 'Providers', path: '/providers', icon: CpuChipIcon }
      ]
    }
  ]

  const bottomItems = [
    { name: 'Settings', path: '/settings', icon: Cog6ToothIcon },
    { name: 'Logout', path: '/logout', icon: ArrowRightOnRectangleIcon }
  ]

  return (
    <div className={`fixed left-0 top-0 h-full bg-gray-800 text-white transition-all duration-300 ${
      collapsed ? 'w-16' : 'w-64'
    } z-30`}>
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-gray-700">
        <div className={`flex items-center ${collapsed ? 'justify-center' : ''}`}>
          <div className="w-8 h-8 bg-blue-500 rounded-lg flex items-center justify-center">
            <span className="text-white font-bold">V</span>
          </div>
          {!collapsed && <span className="ml-3 text-xl font-semibold">Vextir</span>}
        </div>
        <button
          onClick={onToggle}
          className="p-1 rounded-lg hover:bg-gray-700"
        >
          <Bars3Icon className="w-5 h-5" />
        </button>
      </div>

      {/* User Info */}
      <div className="p-4 border-b border-gray-700">
        <div className={`flex items-center ${collapsed ? 'justify-center' : ''}`}>
          <div className="w-8 h-8 bg-green-500 rounded-full flex items-center justify-center">
            <span className="text-white text-sm font-medium">D</span>
          </div>
          {!collapsed && (
            <div className="ml-3">
              <div className="text-sm font-medium">demo-user</div>
              <div className="text-xs text-green-400">Online</div>
            </div>
          )}
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-4">
        <ul className="space-y-2">
          {navItems.map((item) => (
            <li key={item.name}>
              {item.expandable ? (
                <>
                  <button
                    onClick={item.onToggle}
                    className={`w-full flex items-center p-2 rounded-lg hover:bg-gray-700 transition-colors ${
                      collapsed ? 'justify-center' : 'justify-between'
                    }`}
                  >
                    <div className="flex items-center">
                      <item.icon className="w-5 h-5" />
                      {!collapsed && <span className="ml-3">{item.name}</span>}
                    </div>
                    {!collapsed && (
                      item.expanded ? 
                        <ChevronDownIcon className="w-4 h-4" /> : 
                        <ChevronRightIcon className="w-4 h-4" />
                    )}
                  </button>
                  {item.expanded && !collapsed && (
                    <ul className="ml-8 mt-2 space-y-1">
                      {item.children.map((child) => (
                        <li key={child.name}>
                          <Link
                            to={child.path}
                            className={`flex items-center p-2 rounded-lg hover:bg-gray-700 transition-colors ${
                              isActive(child.path) ? 'bg-blue-600' : ''
                            }`}
                          >
                            <child.icon className="w-4 h-4" />
                            <span className="ml-2 text-sm">{child.name}</span>
                          </Link>
                        </li>
                      ))}
                    </ul>
                  )}
                </>
              ) : (
                <Link
                  to={item.path}
                  className={`flex items-center p-2 rounded-lg hover:bg-gray-700 transition-colors ${
                    isActive(item.path) ? 'bg-blue-600' : ''
                  } ${collapsed ? 'justify-center' : ''}`}
                >
                  <item.icon className="w-5 h-5" />
                  {!collapsed && <span className="ml-3">{item.name}</span>}
                </Link>
              )}
            </li>
          ))}
        </ul>
      </nav>

      {/* Bottom Navigation */}
      <div className="p-4 border-t border-gray-700">
        <ul className="space-y-2">
          {bottomItems.map((item) => (
            <li key={item.name}>
              <Link
                to={item.path}
                className={`flex items-center p-2 rounded-lg hover:bg-gray-700 transition-colors ${
                  isActive(item.path) ? 'bg-blue-600' : ''
                } ${collapsed ? 'justify-center' : ''}`}
              >
                <item.icon className="w-5 h-5" />
                {!collapsed && <span className="ml-3">{item.name}</span>}
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}

export default Sidebar