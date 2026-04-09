export function shortId(uuid: string | null): string {
  if (!uuid) return 'Aguardando primeira msg…'
  return uuid.slice(0, 8)
}

export function formatWhen(iso: string | null): string {
  if (!iso) return '—'
  try {
    const d = new Date(iso)
    return d.toLocaleString('pt-PT', {
      day: '2-digit',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}
