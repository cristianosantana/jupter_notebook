import type { ExtractedTsvTable } from '../../dedupeAssistantProse'
import {
  formatTableCell,
  inferTableCellKind,
  tableCellTooltip,
} from '../../tableCellFormat'

export function TsvInlineTableView({ table }: { table: ExtractedTsvTable }) {
  const { titleLine, columns, rows } = table
  return (
    <div className="tsv-inline-table w-full space-y-3">
      {titleLine ? (
        <p className="assistant-prose-width mx-auto text-sm font-semibold text-slate-800">
          {titleLine}
        </p>
      ) : null}
      <div className="flex w-full justify-center">
        <div className="pipe-table-wrap mx-auto min-w-0 w-max max-w-full">
          <table className="w-max min-w-0 text-left text-[0.8125rem] text-slate-800">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50">
                {columns.map((col, ci) => (
                  <th
                    key={ci}
                    className="whitespace-nowrap px-3 py-2 font-semibold text-slate-700"
                  >
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, ri) => (
                <tr
                  key={ri}
                  className="border-b border-slate-100 last:border-0 odd:bg-white even:bg-slate-50/60"
                >
                  {columns.map((_, ci) => {
                    const raw = row[ci]
                    return (
                      <td
                        key={ci}
                        className="px-3 py-2 align-top tabular-nums"
                        data-cell-kind={inferTableCellKind(raw)}
                        title={tableCellTooltip(raw)}
                      >
                        {formatTableCell(raw)}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
