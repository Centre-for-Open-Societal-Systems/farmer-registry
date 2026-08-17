'use client'

import { useEffect, useState } from 'react'

// Chart responses keyed by filter set. The dashboard re-requests the same group
// whenever a filter is cleared and restored, so completed responses are kept for
// the life of the page rather than refetched.
const chartGroupCache = new Map<string, ChartGroupResult>()

export interface ChartGroupResult {
  success: boolean
  data: Record<string, any[]>
  errors: Array<{ chart: string; error: string | null }>
  summary: {
    total: number
    successful: number
    failed: number
    totalExecutionTime: number
  }
}

interface UseChartGroupResult {
  data: ChartGroupResult | null
  loading: boolean
  error: string | null
}

/**
 * Fetches a set of chart queries in one request.
 *
 * Rows come straight from the registry database; a chart that fails is reported
 * in `errors` with an empty series rather than being padded with stand-in values,
 * so a panel with no data reads as empty instead of wrong.
 */
export function useChartGroupData(
  chartNames: string[],
  filters: Record<string, string>,
  initialData?: ChartGroupResult | null
): UseChartGroupResult {
  const [data, setData] = useState<ChartGroupResult | null>(initialData || null)
  const [loading, setLoading] = useState(!initialData)
  const [error, setError] = useState<string | null>(null)

  const chartKey = chartNames.join(',')
  const cleanedFilters = Object.fromEntries(
    Object.entries(filters || {}).filter(
      ([, value]) => value !== undefined && value !== null && value !== 'all'
    )
  )
  const cacheKey = `chart-group:${chartKey}:${JSON.stringify(cleanedFilters)}`

  useEffect(() => {
    let cancelled = false

    const fetchCharts = async () => {
      try {
        setLoading(true)
        setError(null)

        const cached = chartGroupCache.get(cacheKey)
        if (cached) {
          setData(cached)
          setLoading(false)
          return
        }

        const params = new URLSearchParams()
        params.set('charts', chartKey)
        Object.entries(cleanedFilters).forEach(([key, value]) => {
          if (value) params.append(key, value as string)
        })

        const response = await fetch(`/api/charts?${params.toString()}`)
        if (!response.ok) {
          throw new Error(`HTTP error ${response.status}`)
        }
        const result = await response.json()
        if (!result.success) {
          throw new Error(result.error || 'Failed to fetch charts')
        }

        const mapped: ChartGroupResult = {
          success: true,
          data: {},
          errors: [],
          summary: result.summary || {
            total: chartNames.length,
            successful: 0,
            failed: 0,
            totalExecutionTime: 0,
          },
        }

        chartNames.forEach(name => {
          const entry = result.data?.[name]
          mapped.data[name] = entry?.data || []
          if (!entry?.success) {
            mapped.errors.push({ chart: name, error: entry?.error || 'Unknown error' })
          }
        })

        mapped.summary.successful = chartNames.length - mapped.errors.length
        mapped.summary.failed = mapped.errors.length

        if (!cancelled) {
          setData(mapped)
          chartGroupCache.set(cacheKey, mapped)
        }
      } catch (err: any) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Unknown error')
          setData(null)
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    fetchCharts()
    return () => {
      cancelled = true
    }
  }, [cacheKey, chartKey])

  return { data, loading, error }
}
