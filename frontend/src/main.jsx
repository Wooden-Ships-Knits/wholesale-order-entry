import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import AdminApp from './admin/AdminApp.jsx'
import './index.css'

// Two pages, no router dependency:
//   /order_form — the buyer order form
//   /admin      — internal monitoring (asks for the admin password first)
// Anything else redirects to the order form.
const path = window.location.pathname.replace(/\/+$/, '') || '/'

if (path !== '/order_form' && path !== '/admin') {
  window.location.replace('/order_form')
} else {
  ReactDOM.createRoot(document.getElementById('root')).render(
    <React.StrictMode>{path === '/admin' ? <AdminApp /> : <App />}</React.StrictMode>,
  )
}
