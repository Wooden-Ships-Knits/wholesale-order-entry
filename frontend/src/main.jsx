import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import AdminApp from './admin/AdminApp.jsx'
import FaqPage from './faq/FaqPage.jsx'
import RepsApp from './reps/RepsApp.jsx'
import SignPage from './sign/SignPage.jsx'
import DevBanner from './components/DevBanner.jsx'
import './index.css'
import './conflict/conflict.css'
import './faq/faq.css'

// Five pages, no router dependency:
//   /order_form   — the buyer order form
//   /faq          — public FAQ; no sign-in, because the people who need it are
//                   usually buyers stuck part-way through an order
//   /admin        — internal monitoring + the stockist conflict-check tab
//                   (asks for the admin password first)
//   /reps         — a sales rep's read-only view of their own orders
//                   (its own sign-in; a rep session is not an admin session)
//   /sign/<token> — the buyer signing an order from an emailed link
// Anything else redirects to the order form, except the old conflict-tool
// URLs, which now live inside /admin.
const path = window.location.pathname.replace(/\/+$/, '') || '/'

const PAGES = {
  '/order_form': App,
  '/admin': AdminApp,
  '/reps': RepsApp,
  // Public — no sign-in, which is the point: "I can't sign in" is one of the
  // things it answers.
  '/faq': FaqPage,
}

const CONFLICT_LEGACY = ['/check-conflict', '/conflict.html']

// Prefix match, not a PAGES entry: the token is part of the path. Checked
// before the exact-match lookup, which would otherwise miss and bounce the
// buyer to a blank order form.
const SIGN_PREFIX = '/sign/'
const signToken = path.startsWith(SIGN_PREFIX) ? path.slice(SIGN_PREFIX.length) : ''

const Page = signToken ? () => <SignPage token={signToken} /> : PAGES[path]

if (!Page) {
  window.location.replace(CONFLICT_LEGACY.includes(path) ? '/admin' : '/order_form')
} else {
  ReactDOM.createRoot(document.getElementById('root')).render(
    <React.StrictMode>
      {/* Above every page — the order form, /admin and the signing page all
          need to say which environment they are. */}
      <DevBanner />
      <Page />
    </React.StrictMode>,
  )
}
