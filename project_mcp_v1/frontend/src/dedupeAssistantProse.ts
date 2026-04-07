/**
 * Remove lista em prosa duplicada de uma tabela (mesmas linhas em formato
 * "Loja — OS n · Recebido … · Pendente … · Previsto …") quando já existe
 * tabela estruturada (JSON ou TSV no texto).
 */

function isConcessionariaListLine(line: string): boolean {
  const t = line.trim()
  if (t.length < 28) return false
  if (!/\bOS\s*\d+/i.test(t)) return false
  if (!/Recebido/i.test(t)) return false
  if (!/Pendente/i.test(t)) return false
  if (!/Previsto|Faturamento\s+Previsto/i.test(t)) return false
  return true
}

/** Linha introdutória imediatamente antes da lista duplicada. */
function isListIntroLine(line: string): boolean {
  const t = line.trim()
  if (t.length > 200) return false
  return /detalhamento\s+por\s+concession/i.test(t) || /lista\s+por\s+unidade/i.test(t)
}

export function stripDuplicateConcessionariaList(
  prose: string,
  referenceRowCount: number | null,
): string {
  if (referenceRowCount == null || referenceRowCount < 3) return prose

  const lines = prose.split('\n')
  const runs: { start: number; end: number }[] = []
  let i = 0
  while (i < lines.length) {
    if (!isConcessionariaListLine(lines[i])) {
      i++
      continue
    }
    const start = i
    while (i < lines.length && isConcessionariaListLine(lines[i])) i++
    runs.push({ start, end: i })
  }

  const exact = runs.find((r) => r.end - r.start === referenceRowCount)
  const near = runs.find(
    (r) =>
      Math.abs(r.end - r.start - referenceRowCount) <= 1 &&
      r.end - r.start >= 3,
  )
  const toRemove = exact ?? near
  if (!toRemove) return prose

  let rmStart = toRemove.start
  if (rmStart > 0 && isListIntroLine(lines[rmStart - 1])) {
    rmStart -= 1
  }

  const out = [...lines.slice(0, rmStart), ...lines.slice(toRemove.end)]
  return out.join('\n').replace(/\n{3,}/g, '\n\n').trimEnd()
}

function tabSplit(line: string): string[] {
  return line.split('\t').map((c) => c.trim())
}

/** Linha parece linha de tabela TSV (várias colunas). */
function isTsvRow(line: string, minCols: number): boolean {
  if (!line.includes('\t')) return false
  const parts = tabSplit(line).filter((p) => p.length > 0)
  return parts.length >= minCols
}

export type ExtractedTsvTable = {
  titleLine: string | null
  columns: string[]
  rows: string[][]
  dataRowCount: number
}

/**
 * Localiza o maior bloco consecutivo de linhas com tabs (cabeçalho + dados).
 */
function findTsvBlock(lines: string[]): {
  start: number
  end: number
  columns: string[]
  dataRows: string[][]
} | null {
  let best: { start: number; end: number; columns: string[]; dataRows: string[][] } | null =
    null

  for (let start = 0; start < lines.length; start++) {
    if (!lines[start].includes('\t')) continue
    const firstParts = tabSplit(lines[start])
    if (firstParts.length < 3) continue

    let end = start + 1
    while (end < lines.length && isTsvRow(lines[end], 3)) {
      end++
    }
    const slice = lines.slice(start, end)
    if (slice.length < 2) continue

    const columns = tabSplit(slice[0])
    if (columns.length < 3) continue

    const dataRows = slice.slice(1).map((ln) => tabSplit(ln))
    if (dataRows.length < 2) continue

    const headerLooksTable =
      /concession|qtd|recebido|pendente|previsto|faturamento|mês|mes/i.test(
        slice[0],
      )
    if (!headerLooksTable && columns.length < 4) continue

    if (
      !best ||
      dataRows.length > best.dataRows.length ||
      (dataRows.length === best.dataRows.length && columns.length > best.columns.length)
    ) {
      best = { start, end, columns, dataRows }
    }
  }

  return best
}

/** Inspecciona texto sem remover (para contar linhas antes do strip da lista). */
export function peekTsvDataRowCount(prose: string): number | null {
  const block = findTsvBlock(prose.split('\n'))
  return block ? block.dataRows.length : null
}

export type ExtractTsvResult = {
  proseWithoutTable: string
  table: ExtractedTsvTable | null
}

/**
 * Remove o bloco TSV do texto e devolve colunas + linhas para renderizar `<table>`.
 */
export function extractTsvTableFromProse(prose: string): ExtractTsvResult {
  const lines = prose.split('\n')
  const block = findTsvBlock(lines)
  if (!block) return { proseWithoutTable: prose, table: null }

  let titleLine: string | null = null
  if (block.start > 0) {
    const prev = lines[block.start - 1].trim()
    if (
      prev.length > 0 &&
      prev.length < 220 &&
      !prev.includes('\t') &&
      !isConcessionariaListLine(lines[block.start - 1])
    ) {
      titleLine = prev
    }
  }

  const rmStart = titleLine != null ? block.start - 1 : block.start
  const before = lines.slice(0, rmStart).join('\n').trimEnd()
  const after = lines.slice(block.end).join('\n').trimStart()
  const proseWithoutTable = [before, after].filter(Boolean).join('\n\n').trim()

  return {
    proseWithoutTable,
    table: {
      titleLine,
      columns: block.columns,
      rows: block.dataRows,
      dataRowCount: block.dataRows.length,
    },
  }
}
