import { renderInlineBold } from './renderInlineBold'

export function NumberedBlock({ raw }: { raw: string }) {
  const segments = raw
    .split(/\s+[—–]\s+/)
    .map((s) => s.trim())
    .filter(Boolean)
  const [head, ...rest] = segments
  return (
    <div className="numbered-block-card">
      {head ? (
        <p className="text-[0.9375rem] font-semibold leading-snug text-slate-900">
          {renderInlineBold(head)}
        </p>
      ) : null}
      {rest.length > 0 ? (
        <ul className="mt-3 flex list-none flex-col gap-2 pl-0 sm:flex-row sm:flex-wrap">
          {rest.map((seg, si) => (
            <li
              key={si}
              className="rounded-lg border border-slate-200/80 bg-slate-50 px-3 py-2 text-[0.8125rem] font-medium leading-snug text-slate-700"
            >
              {renderInlineBold(seg)}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}
