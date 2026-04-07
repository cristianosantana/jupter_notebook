/**
 * Detecção e formatação de valores em células de tabela (números BR/US, moeda, %, datas).
 */

export type TableCellKind =
  | 'empty'
  | 'boolean'
  | 'integer'
  | 'float'
  | 'percent'
  | 'currency'
  | 'date'
  | 'datetime'
  | 'text'

const nfInt = new Intl.NumberFormat('pt-BR', {
  maximumFractionDigits: 0,
})

const nfFloat = new Intl.NumberFormat('pt-BR', {
  minimumFractionDigits: 0,
  maximumFractionDigits: 8,
})

const nfCurrency = new Intl.NumberFormat('pt-BR', {
  style: 'currency',
  currency: 'BRL',
})

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/
const ISO_DATETIME_START = /^\d{4}-\d{2}-\d{2}[T ]/
const BR_SLASH_DATE = /^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$/

/** Remove espaços internos usados como separador de milhares (ex.: "1 234,56"). */
function stripSpaces(s: string): string {
  return s.replace(/\s/g, '')
}

/**
 * Interpreta número em texto com convenções brasileiras (1.234,56) ou simples (1234.56).
 * Devolve null se não for claramente numérico.
 */
export function parseLocaleNumberString(raw: string): number | null {
  let t = stripSpaces(raw.trim())
  if (!t || !/^-?[\d.,]+$/.test(t)) return null

  const neg = t.startsWith('-')
  if (neg) t = t.slice(1)

  if (t.includes(',') && t.includes('.')) {
    const lastComma = t.lastIndexOf(',')
    const lastDot = t.lastIndexOf('.')
    if (lastComma > lastDot) {
      // 1.234,56
      t = t.replace(/\./g, '').replace(',', '.')
    } else {
      // 1,234.56 (US)
      t = t.replace(/,/g, '')
    }
  } else if (t.includes(',')) {
    const parts = t.split(',')
    if (parts.length === 2 && parts[1].length <= 2) {
      t = `${parts[0]}.${parts[1]}`
    } else {
      t = t.replace(/,/g, '')
    }
  } else if (t.includes('.')) {
    const parts = t.split('.')
    if (parts.length === 2 && parts[1].length <= 2) {
      t = `${parts[0]}.${parts[1]}`
    } else {
      // 199.550 ou 1.234.567
      t = parts.join('')
    }
  }

  const n = parseFloat(neg ? `-${t}` : t)
  return Number.isFinite(n) ? n : null
}

function looksLikeNumericOnly(s: string): boolean {
  const t = stripSpaces(s.trim())
    .replace(/^\s*R\$\s*/i, '')
    .replace(/%$/, '')
  return /^-?[\d.,]+$/.test(t)
}

function formatNumberAuto(n: number): string {
  if (Number.isInteger(n) || Math.abs(n - Math.round(n)) < 1e-9) {
    return nfInt.format(Math.round(n))
  }
  return nfFloat.format(n)
}

function formatIsoDateString(s: string): string | null {
  if (!ISO_DATE.test(s)) return null
  const d = new Date(`${s}T12:00:00`)
  if (Number.isNaN(d.getTime())) return null
  return d.toLocaleDateString('pt-PT', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  })
}

function formatIsoDateTimeString(s: string): string | null {
  const t = s.trim()
  if (!ISO_DATETIME_START.test(t)) return null
  const d = new Date(t)
  if (Number.isNaN(d.getTime())) return null
  return d.toLocaleString('pt-PT', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatBrSlashDate(s: string): string | null {
  const m = BR_SLASH_DATE.exec(s.trim())
  if (!m) return null
  const d = new Date(+m[3], +m[2] - 1, +m[1])
  if (Number.isNaN(d.getTime())) return null
  return d.toLocaleDateString('pt-PT', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  })
}

/**
 * Classifica o valor bruto para estilos ou `title` (valor original).
 */
export function inferTableCellKind(raw: unknown): TableCellKind {
  if (raw === null || raw === undefined) return 'empty'
  if (typeof raw === 'boolean') return 'boolean'
  if (typeof raw === 'number') {
    if (!Number.isFinite(raw)) return 'empty'
    return Number.isInteger(raw) ? 'integer' : 'float'
  }
  if (typeof raw !== 'string') return 'text'
  const s = raw.trim()
  if (s === '') return 'empty'
  if (ISO_DATETIME_START.test(s)) return 'datetime'
  if (ISO_DATE.test(s)) return 'date'
  if (BR_SLASH_DATE.test(s.trim())) return 'date'
  const pct = stripSpaces(s)
  if (/%$/.test(pct)) {
    const n = parseLocaleNumberString(pct.slice(0, -1))
    if (n !== null) return 'percent'
  }
  if (/^R\$\s*/i.test(s)) return 'currency'
  if (looksLikeNumericOnly(s)) {
    const n = parseLocaleNumberString(s)
    if (n === null) return 'text'
    return Number.isInteger(n) || Math.abs(n - Math.round(n)) < 1e-9
      ? 'integer'
      : 'float'
  }
  return 'text'
}

/**
 * Formata valor de célula para apresentação (pt-BR / pt-PT).
 */
export function formatTableCell(raw: unknown): string {
  if (raw === null || raw === undefined) return '—'
  if (typeof raw === 'boolean') return raw ? 'sim' : 'não'
  if (typeof raw === 'number') {
    if (!Number.isFinite(raw)) return '—'
    return formatNumberAuto(raw)
  }
  if (typeof raw !== 'string') return String(raw)

  const s = raw.trim()
  if (s === '') return '—'

  const dt = formatIsoDateTimeString(s)
  if (dt) return dt

  const d = formatIsoDateString(s)
  if (d) return d

  const br = formatBrSlashDate(s)
  if (br) return br

  const compactPct = stripSpaces(s)
  if (/%$/.test(compactPct)) {
    const n = parseLocaleNumberString(compactPct.slice(0, -1))
    if (n !== null) {
      return `${nfFloat.format(n).replace(/\s/g, '')}\u00A0%`
    }
  }

  if (/^R\$\s*/i.test(s)) {
    const n = parseLocaleNumberString(s.replace(/^R\$\s*/i, ''))
    if (n !== null) return nfCurrency.format(n)
  }

  if (looksLikeNumericOnly(s)) {
    const n = parseLocaleNumberString(s)
    if (n !== null) return formatNumberAuto(n)
  }

  return s
}

/** Tooltip com valor original quando a formatação altera o texto. */
export function tableCellTooltip(raw: unknown): string | undefined {
  if (raw === null || raw === undefined) return undefined
  if (typeof raw === 'number' || typeof raw === 'boolean') return undefined
  const rawStr = String(raw).trim()
  if (rawStr === '') return undefined
  const formatted = formatTableCell(raw)
  if (formatted === rawStr || formatted === '—') return undefined
  return rawStr
}
