import type { ContentBlock } from '../../chat/types'
import {
  formatTableCell,
  inferTableCellKind,
  tableCellTooltip,
} from '../../tableCellFormat'

export function ContentBlocksView({ blocks }: { blocks: ContentBlock[] }) {
  const prose = 'assistant-prose-width'
  return (
    <div className="content-blocks">
      {blocks.map((block, i) => {
        const key = `b-${i}`
        switch (block.type) {
          case 'paragraph':
            return (
              <div key={key} className={prose}>
                <p className="whitespace-pre-wrap text-[0.9375rem] leading-7 text-slate-700">
                  {block.text}
                </p>
              </div>
            )
          case 'heading': {
            const level = block.level ?? 2
            const cls =
              level === 1
                ? 'text-lg font-bold text-slate-900'
                : level === 2
                  ? 'text-base font-semibold text-slate-900'
                  : 'text-sm font-semibold text-slate-800'
            const Tag = level === 1 ? 'h3' : level === 2 ? 'h4' : 'h5'
            return (
              <div key={key} className={prose}>
                <Tag className={cls}>{block.text}</Tag>
              </div>
            )
          }
          case 'table':
            return (
              <div key={key} className="flex w-full justify-center">
                <div className="pipe-table-wrap mx-auto min-w-0 w-max max-w-full">
                  <table className="w-max min-w-0 text-left text-[0.8125rem] text-slate-800">
                    <thead>
                      <tr className="border-b border-slate-200 bg-slate-50">
                        {block.columns.map((col, ci) => (
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
                      {block.rows.map((row, ri) => (
                        <tr
                          key={ri}
                          className="border-b border-slate-100 last:border-0 odd:bg-white even:bg-slate-50/60"
                        >
                          {block.columns.map((_, ci) => {
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
            )
          case 'metric_grid':
            return (
              <ul
                key={key}
                className="m-0 grid w-full list-none grid-cols-1 gap-2 p-0 sm:grid-cols-2 lg:grid-cols-3"
              >
                {block.items.map((item, mi) => (
                  <li
                    key={mi}
                    className="rounded-xl border border-slate-200/95 bg-slate-50/90 px-3 py-2.5 shadow-sm"
                  >
                    <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                      {item.label}
                    </div>
                    <div
                      className="mt-1 text-sm font-semibold tabular-nums text-slate-900"
                      data-cell-kind={inferTableCellKind(item.value)}
                      title={tableCellTooltip(item.value)}
                    >
                      {formatTableCell(item.value)}
                    </div>
                  </li>
                ))}
              </ul>
            )
          default:
            return null
        }
      })}
    </div>
  )
}
