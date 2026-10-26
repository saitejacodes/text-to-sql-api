import type { Cell } from '../types'

function escape(value: Cell): string {
  if (value === null) return ''
  const text = String(value)
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

export function toCsv(columns: string[], rows: Cell[][]): string {
  return [columns, ...rows].map((row) => row.map(escape).join(',')).join('\r\n')
}

export function downloadCsv(filename: string, columns: string[], rows: Cell[][]): void {
  const blob = new Blob([toCsv(columns, rows)], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
