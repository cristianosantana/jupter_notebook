import type { ReactNode } from 'react'
import { splitPipeCells } from '../../assistant/pipeTable'
import { tryMonthValueSemanticTable } from '../../assistant/pipeTable'
import {
  formatTableCell,
  inferTableCellKind,
  tableCellTooltip,
} from '../../tableCellFormat'
import { renderInlineBold } from './renderInlineBold'

export function PipeTableView({ rows }: { rows: string[] }) {
  const matrix = rows.map((r) => splitPipeCells(r))
  if (matrix.length === 0 || matrix.every((r) => r.length === 0)) return null
  const maxCols = Math.max(...matrix.map((r) => r.length), 1)
  const semantic = tryMonthValueSemanticTable(matrix)

  const wrap = (inner: ReactNode) => (
    <div className="pipe-table-wrap">{inner}</div>
  )

  if (semantic) {
    return wrap(
      <table className="w-max min-w-0 text-left text-[0.8125rem] text-slate-800">
        <thead>
          <tr className="border-b border-slate-200 bg-slate-50">
            {semantic.headers.map((h, hi) => (
              <th
                key={hi}
                className="whitespace-nowrap px-3 py-2 font-semibold text-slate-700"
              >
                {renderInlineBold(h)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr className="bg-white">
            {semantic.values.map((v, vi) => (
              <td
                key={vi}
                className="border-t border-slate-100 px-3 py-2.5 tabular-nums font-medium text-slate-900"
                data-cell-kind={inferTableCellKind(v)}
                title={tableCellTooltip(v)}
              >
                {renderInlineBold(formatTableCell(v))}
              </td>
            ))}
          </tr>
        </tbody>
      </table>,
    )
  }

  return wrap(
    <table className="w-max min-w-0 text-left text-[0.8125rem] text-slate-800">
      <tbody>
        {matrix.map((row, ri) => (
          <tr
            key={ri}
            className="border-b border-slate-100 last:border-0 odd:bg-white even:bg-slate-50/70"
          >
            {Array.from({ length: maxCols }, (_, ci) => {
              const cell = row[ci]
              const empty = cell == null || cell === ''
              return (
                <td
                  key={ci}
                  className="border-slate-100 px-3 py-2 align-top text-slate-700 [&:not(:last-child)]:border-r"
                  data-cell-kind={empty ? 'empty' : inferTableCellKind(cell)}
                  title={empty ? undefined : tableCellTooltip(cell)}
                >
                  {empty ? '—' : renderInlineBold(formatTableCell(cell))}
                </td>
              )
            })}
          </tr>
        ))}
      </tbody>
    </table>,
  )
}
