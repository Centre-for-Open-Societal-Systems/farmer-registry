// Shared data shaping for the Farmer Registry dashboard.

import { useMemo } from "react"

/**
 * What the sidebar, the choropleth and the API all narrow by.
 *
 * The four geography levels are named for Ethiopia because that is the
 * deployment this dashboard was designed against, but they are only positions:
 * region is the first level below country, kebele the fourth. A country pack
 * that calls them district/ward/village fills the same four slots, which is why
 * the sidebar takes its labels from the geo levels the API reports rather than
 * from these key names.
 */
export interface RegistryFilters {
  region: string
  zone: string
  woreda: string
  kebele: string
  farmingType: string
  recordState: string
}

export interface TrendPoint {
  period: string
  farmers: number
  totalArea: number
  ownedArea: number
  avgArea: number
}

export function toNumber(value: unknown): number {
  const parsed = typeof value === "number" ? value : parseFloat(String(value ?? 0))
  return Number.isFinite(parsed) ? parsed : 0
}

/** "2025-07" -> "Jul 2025" */
export function monthLabel(period: string): string {
  const [year, month] = String(period || "").split("-")
  const index = Number(month) - 1
  const names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
  return names[index] ? `${names[index]} ${year}` : period
}

export function useRegistryTrend(rows: any[] | undefined): { series: TrendPoint[] } {
  const series = useMemo<TrendPoint[]>(() => {
    return (rows || [])
      .map((row: any) => {
        const farmers = toNumber(row.farmers)
        const totalArea = toNumber(row.total_area)
        return {
          period: String(row.period),
          farmers,
          totalArea,
          ownedArea: toNumber(row.owned_area),
          avgArea: farmers > 0 ? totalArea / farmers : 0,
        }
      })
      .sort((a, b) => a.period.localeCompare(b.period))
  }, [rows])

  return { series }
}

/**
 * Derives a 12-point sparkline plus a period-over-period delta from a monthly
 * series. Cumulative metrics (stock, e.g. hectares registered to date) climb,
 * while rate metrics (e.g. average plot size) are plotted as-is.
 */
export function buildTrend(
  series: TrendPoint[],
  key: keyof Omit<TrendPoint, "period">,
  { cumulative = false }: { cumulative?: boolean } = {}
): { spark: number[]; delta?: { percent: number; note: string } } {
  if (series.length < 2) return { spark: [] }

  const values = series.map((point) => point[key])

  let spark: number[]
  if (cumulative) {
    let running = 0
    const cumulated = values.map((value) => (running += value))
    spark = cumulated.slice(-12)
  } else {
    spark = values.slice(-12)
  }

  const window = Math.min(12, Math.floor(series.length / 2))
  if (window < 1) return { spark }

  const recent = values.slice(-window)
  const previous = values.slice(-window * 2, -window)
  if (!previous.length) return { spark }

  const sum = (list: number[]) => list.reduce((acc, value) => acc + value, 0)
  const recentValue = cumulative ? sum(recent) : sum(recent) / recent.length
  const previousValue = cumulative ? sum(previous) : sum(previous) / previous.length

  if (previousValue === 0) return { spark }

  return {
    spark,
    delta: {
      percent: ((recentValue - previousValue) / previousValue) * 100,
      note: `vs previous ${window} months`,
    },
  }
}
