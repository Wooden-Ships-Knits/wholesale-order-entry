// The FAQ page at /faq. Public — no sign-in, because the people most likely to
// need it are buyers who have hit something confusing mid-order.
//
// The CONTENT lives in faqContent.js and nothing here needs touching to add a
// question. This file is only the rendering and the open/closed behaviour.

import { useState } from 'react'
import { FAQ_SECTIONS } from './faqContent'

/** One question. Open state lives here rather than in the page so that opening
 *  one answer never re-renders the others — and so a half-read answer does not
 *  close because someone clicked elsewhere.
 *
 *  A <button> rather than a clickable heading: it has to be reachable by
 *  keyboard and announce itself as expandable, which a styled <div> does not.
 */
function FaqItem({ q, a }) {
  const [open, setOpen] = useState(false)
  const paragraphs = Array.isArray(a) ? a : [a]
  return (
    <div className={open ? 'faq-item open' : 'faq-item'}>
      <button
        type="button"
        className="faq-question"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        <span>{q}</span>
        <span className="faq-marker" aria-hidden="true">
          {open ? '−' : '+'}
        </span>
      </button>
      {open && (
        <div className="faq-answer">
          {paragraphs.map((text, i) => (
            <p key={i}>{text}</p>
          ))}
        </div>
      )}
    </div>
  )
}

export default function FaqPage() {
  // A section with no questions is skipped: an empty heading reads as a
  // missing answer rather than a section nobody has filled in yet.
  const sections = FAQ_SECTIONS.filter((s) => s.items && s.items.length > 0)

  return (
    <main className="faq-page">
      <header className="faq-head">
        <h1>Frequently asked questions</h1>
        <p className="faq-sub">Wooden Ships wholesale</p>
      </header>

      {sections.length === 0 && (
        <p className="faq-empty">No questions have been added yet.</p>
      )}

      {sections.map((section) => (
        <section key={section.title} className="faq-section">
          <h2>{section.title}</h2>
          {section.items.map((item) => (
            <FaqItem key={item.q} q={item.q} a={item.a} />
          ))}
        </section>
      ))}

      <footer className="faq-foot">
        <p>
          Still stuck? Reply to any email from us, or write to{' '}
          <a href="mailto:wholesale@wooden-ships.com">wholesale@wooden-ships.com</a>.
        </p>
      </footer>
    </main>
  )
}
