/** Realça `**negrito**` estilo Markdown comum nas respostas do modelo. */
export function renderInlineBold(text: string) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g)
  return parts.map((part, i) => {
    const m = part.match(/^\*\*([^*]+)\*\*$/)
    if (m) {
      return (
        <strong key={i} className="font-semibold text-slate-900">
          {m[1]}
        </strong>
      )
    }
    return <span key={i}>{part}</span>
  })
}
