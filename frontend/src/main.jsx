import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import AdminApp from './admin/AdminApp.jsx'
import './index.css'
import './conflict/conflict.css'

// Two pages, no router dependency:
//   /order_form — the buyer order form
//   /admin      — internal monitoring + the stockist conflict-check tab
//                 (asks for the admin password first)
// Anything else redirects to the order form, except the old conflict-tool
// URLs, which now live inside /admin.
const path = window.location.pathname.replace(/\/+$/, '') || '/'

const PAGES = {
  '/order_form': App,
  '/admin': AdminApp,
}

const CONFLICT_LEGACY = ['/check-conflict', '/conflict.html']

const Page = PAGES[path]

if (!Page) {
  window.location.replace(CONFLICT_LEGACY.includes(path) ? '/admin' : '/order_form')
} else {
  ReactDOM.createRoot(document.getElementById('root')).render(
    <React.StrictMode>
      <Page />
    </React.StrictMode>,
  )
}
