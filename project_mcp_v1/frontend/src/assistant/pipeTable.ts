/** Divide uma linha em células por `|` (vazios omitidos). */
export function splitPipeCells(line: string): string[] {
  return line
    .split('|')
    .map((c) => c.trim())
    .filter((c) => c.length > 0)
}

export function countPipes(s: string): number {
  return (s.match(/\|/g) ?? []).length
}

/** Pelo menos dois pipes e duas células não vazias — padrão tipo `| Jun 1 | Jul 2 |`. */
export function isPipeDenseLine(s: string): boolean {
  return countPipes(s) >= 2 && splitPipeCells(s).length >= 2
}

/**
 * Separa texto introdutório do primeiro `|` quando o resto continua a ser tabular.
 */
export function extractPipeTableFromLine(line: string): {
  caption: string | null
  pipeLine: string
} {
  const trimmed = line.trim()
  if (!isPipeDenseLine(trimmed)) {
    return { caption: null, pipeLine: trimmed }
  }
  const firstPipe = trimmed.indexOf('|')
  const preamble = trimmed.slice(0, firstPipe).trim()
  const rest = trimmed.slice(firstPipe).trim()
  if (!isPipeDenseLine(rest)) {
    return { caption: null, pipeLine: trimmed }
  }
  return {
    caption: preamble.length > 0 ? preamble : null,
    pipeLine: rest,
  }
}

/** Células no formato mês + valor (ex.: `Jun 199.550`, `Oct 200.`, `Jan R$ 1.234,56`). */
export const PIPE_CELL_MONTH_VALUE =
  /^([A-Za-zÀ-ú]{3,})\s+(?:R\$\s*)?([\d\s.,]+(?:\s*[%‰])?)$/

export function tryMonthValueSemanticTable(matrix: string[][]): {
  headers: string[]
  values: string[]
} | null {
  if (matrix.length !== 1) return null
  const cells = matrix[0]
  const headers: string[] = []
  const values: string[] = []
  for (const c of cells) {
    const m = c.trim().match(PIPE_CELL_MONTH_VALUE)
    if (!m) return null
    headers.push(m[1])
    values.push(m[2].trim())
  }
  return headers.length >= 2 ? { headers, values } : null
}
