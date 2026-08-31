// The "What's new" tab: renders the changelog that ships with the build.
//
// WHY THE MARKDOWN LIVES HERE AND NOT IN docs/. The frontend image is built
// with `build: ./frontend`, so the Docker context contains frontend/ and
// nothing else — a file in docs/ is simply absent at `npm run build` time and
// the import would fail the image build while working perfectly on a laptop.
// docs/version.md is a pointer to this file so the two can't drift.
//
// Imported with ?raw, so the text is inlined into the bundle at build time.
// That also means WHAT YOU SEE HERE IS THE VERSION THAT IS DEPLOYED: if the
// tab shows an old changelog, the frontend image is stale, which is a useful
// thing for this page in particular to be able to tell you.
import versionText from './version.md?raw'

/** Inline markdown: **bold** and `code`. Everything else is left alone.
 *
 * Returns an array of React nodes rather than HTML — no dangerouslySetInnerHTML
 * anywhere in this file. The changelog is ours today, but a rendering path that
 * trusts its input is the kind of thing that quietly becomes a hole the day
 * someone pastes a customer's message into a release note.
 */
function inline(text, keyPrefix) {
  const parts = []
  // One pass over both patterns, so **`code`** and `**bold**` can't interleave
  // into a mismatched pair.
  const re = /\*\*(.+?)\*\*|`(.+?)`/g
  let last = 0
  let m
  let i = 0
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index))
    if (m[1] !== undefined) parts.push(<strong key={`${keyPrefix}-b${i}`}>{m[1]}</strong>)
    else parts.push(<code key={`${keyPrefix}-c${i}`}>{m[2]}</code>)
    last = m.index + m[0].length
    i += 1
  }
  if (last < text.length) parts.push(text.slice(last))
  return parts
}

/** The small subset of markdown the changelog actually uses: h1/h2/h3, bullet
 *  lists, horizontal rules, paragraphs, and HTML comments (skipped — that is
 *  where the entry template lives, and nobody wants to read it on the page). */
function render(md) {
  const out = []
  // Drop <!-- ... --> blocks first: the file keeps a commented-out template for
  // the next release, which is guidance for whoever edits it, not content.
  const text = md.replace(/<!--[\s\S]*?-->/g, '')
  const lines = text.split('\n')
  let bullets = []

  const flush = () => {
    if (!bullets.length) return
    out.push(
      <ul key={`ul-${out.length}`}>
        {bullets.map((b, i) => (
          <li key={i}>{inline(b, `li-${out.length}-${i}`)}</li>
        ))}
      </ul>,
    )
    bullets = []
  }

  for (const raw of lines) {
    const line = raw.trimEnd()
    // A bullet's continuation lines are indented; join them onto the last
    // bullet instead of starting a paragraph mid-list.
    if (/^\s+\S/.test(raw) && bullets.length) {
      bullets[bullets.length - 1] += ' ' + line.trim()
      continue
    }
    const t = line.trim()
    if (!t) {
      flush()
      continue
    }
    if (t.startsWith('- ')) {
      bullets.push(t.slice(2))
      continue
    }
    flush()
    if (t === '---') out.push(<hr key={`hr-${out.length}`} />)
    else if (t.startsWith('### ')) out.push(<h3 key={`h-${out.length}`}>{t.slice(4)}</h3>)
    else if (t.startsWith('## ')) out.push(<h2 key={`h-${out.length}`}>{t.slice(3)}</h2>)
    else if (t.startsWith('# ')) out.push(<h1 key={`h-${out.length}`}>{t.slice(2)}</h1>)
    else out.push(<p key={`p-${out.length}`}>{inline(t, `p-${out.length}`)}</p>)
  }
  flush()
  return out
}

export default function VersionPanel() {
  return <div className="version-panel">{render(versionText)}</div>
}
