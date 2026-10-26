import { Highlight, themes } from 'prism-react-renderer'
import { useState } from 'react'

export function SqlViewer({ sql }: { sql: string }) {
  const [copied, setCopied] = useState(false)

  async function copy() {
    try {
      await navigator.clipboard.writeText(sql)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      // clipboard blocked; the SQL is still selectable
    }
  }

  return (
    <section aria-label="Generated SQL" className="overflow-hidden rounded-lg border border-slate-800">
      <div className="flex items-center justify-between bg-slate-800 px-3 py-1.5">
        <span className="text-xs font-medium uppercase tracking-wide text-slate-300">Generated SQL</span>
        <button
          type="button"
          onClick={copy}
          className="rounded px-2 py-0.5 text-xs text-slate-200 hover:bg-slate-700 focus-visible:outline-2 focus-visible:outline-indigo-400"
        >
          {copied ? 'Copied ✓' : 'Copy'}
        </button>
      </div>
      <Highlight theme={themes.vsDark} code={sql} language="sql">
        {({ style, tokens, getLineProps, getTokenProps }) => (
          <pre style={style} className="overflow-x-auto p-3 text-sm leading-relaxed">
            {tokens.map((line, i) => (
              <div key={i} {...getLineProps({ line })}>
                {line.map((token, key) => (
                  <span key={key} {...getTokenProps({ token })} />
                ))}
              </div>
            ))}
          </pre>
        )}
      </Highlight>
    </section>
  )
}
