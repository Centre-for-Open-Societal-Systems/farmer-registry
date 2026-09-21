// HTTP surface of the dashboard. Every route reads the Farmer Registry database
// directly; nothing here serves fixtures or falls back to canned numbers, so an
// empty registry produces empty responses rather than filler.
import { Elysia } from 'elysia'
import cors from '@elysiajs/cors'
import { performance } from 'perf_hooks'
import { CHART_QUERIES, ChartFilters, DYNAMIC_FILTERS, SCOPE } from '@/lib/chart-queries'
import {
  fetchFarmingTypes,
  fetchGeoLevels,
  fetchGeoOptions,
  fetchGeoTotals,
  fetchRecordStates,
  fetchRecordsForExport,
  pool,
  testConnection,
  type GeoLevel,
} from '@/lib/db'
import type { Context } from 'elysia'
import { generateCacheKey, getCachedData, setCachedData } from './cache'

// Filterable columns, all resolved inside the `scope` CTE, so one mapping serves
// every chart. Geography is matched on the level's value id, which is what both
// the sidebar and the choropleth send.
const FILTER_COLUMNS: Record<keyof ChartFilters, string> = {
  region: 'g.geo_2_id',
  zone: 'g.geo_3_id',
  woreda: 'g.geo_4_id',
  kebele: 'g.geo_5_id',
  farmingType: 'h.main_farming_type',
  recordState: "COALESCE(d.approval_status, 'APPROVED')",
}

function buildWhereClause(filters: ChartFilters): { clause: string; values: any[] } {
  const conditions: string[] = []
  const values: any[] = []

  for (const [key, column] of Object.entries(FILTER_COLUMNS)) {
    const value = filters[key as keyof ChartFilters]
    if (!value || value === 'all') continue
    conditions.push(`${column} = $${values.length + 1}`)
    values.push(value)
  }

  if (conditions.length === 0) return { clause: '', values: [] }
  return { clause: `AND ${conditions.join(' AND ')}`, values }
}

function prepareChartSql(baseQuery: string, filters: ChartFilters) {
  const { clause, values } = buildWhereClause(filters)
  return { sql: baseQuery.replace(DYNAMIC_FILTERS, clause), values }
}

/**
 * Coverage is the one panel whose numbers do not all come from one database.
 *
 * The registry knows how many distinct units hold a record; only Master Data
 * knows how many units the country has. The two are paired here rather than in
 * SQL because they are separate connections.
 */
async function executeCoverage(filters: ChartFilters) {
  const { sql, values } = prepareChartSql(CHART_QUERIES.registryCoverage, filters)
  const [{ rows }, totals] = await Promise.all([pool.query(sql, values), fetchGeoTotals()])

  const covered = rows[0] || {}
  return [
    {
      ...covered,
      regions_total: totals.region,
      zones_total: totals.zone,
      woredas_total: totals.woreda,
      kebeles_total: totals.kebele,
    },
  ]
}

async function executeChartQuery(chartName: string, filters: ChartFilters) {
  const cacheKey = generateCacheKey(`chart:${chartName}`, filters)

  const cached = getCachedData<any>(cacheKey)
  if (cached) {
    return { ...cached, fromCache: true }
  }

  const startTime = performance.now()

  try {
    const baseQuery = CHART_QUERIES[chartName as keyof typeof CHART_QUERIES]
    if (!baseQuery) {
      throw new Error(`Query for chart "${chartName}" not found.`)
    }

    let rows: any[]
    if (chartName === 'registryCoverage') {
      rows = await executeCoverage(filters)
    } else {
      const { sql, values } = prepareChartSql(baseQuery, filters)
      rows = (await pool.query(sql, values)).rows
    }

    const result = {
      chartName,
      success: true,
      data: rows,
      error: null,
      executionTime: Math.round(performance.now() - startTime),
    }
    setCachedData(cacheKey, result)
    return result
  } catch (error: any) {
    console.error(`Error executing ${chartName}:`, error)
    return {
      chartName,
      success: false,
      data: [],
      error: error instanceof Error ? error.message : 'Unknown error',
      executionTime: Math.round(performance.now() - startTime),
    }
  }
}

function parseChartFilters(query: Context['query']): ChartFilters {
  return {
    region: (query.region as string) || 'all',
    zone: (query.zone as string) || 'all',
    woreda: (query.woreda as string) || 'all',
    kebele: (query.kebele as string) || 'all',
    farmingType: (query.farmingType as string) || 'all',
    recordState: (query.recordState as string) || (query.state as string) || 'all',
  }
}

function jsonToCsv(items: any[]): string {
  if (!items || items.length === 0) return ''
  const replacer = (_key: any, value: any) => (value === null ? '' : value)
  const header = Object.keys(items[0])
  return [
    header.join(','),
    ...items.map(row => header.map(field => JSON.stringify(row[field], replacer)).join(',')),
  ].join('\r\n')
}

export function createElysiaApp(prefix = '/api') {
  return new Elysia({ prefix })
    .use(cors())
    .get('/health', async () => ({
      status: (await testConnection()) ? 'ok' : 'degraded',
      service: 'farmer-registry-dashboard',
      timestamp: new Date().toISOString(),
    }))

    // Options for the sidebar's dropdowns. Geography comes from the country pack
    // in Master Data, everything else from the register's own records, so the
    // filters can only offer what the registry recognises. `levels` carries the
    // pack's names for the four geography levels, which is what the sidebar
    // titles them with.
    .get('/filter-options', async ({ set }) => {
      try {
        const [regions, recordStatuses, farmingTypes, levels] = await Promise.all([
          fetchGeoOptions('region'),
          fetchRecordStates(),
          fetchFarmingTypes(),
          fetchGeoLevels(),
        ])
        return { regions, recordStatuses, farmingTypes, levels }
      } catch (error: any) {
        console.error('API Error fetching filter options:', error)
        set.status = 500
        return {
          message: 'Failed to fetch filter options',
          error: error instanceof Error ? error.message : 'Unknown error',
        }
      }
    })

    // One step of the geography cascade. The caller passes the parent it has
    // selected and gets that parent's children back.
    .get('/locations', async ({ query, set }) => {
      const steps: Array<{ param: string; parent: GeoLevel; child: GeoLevel; key: string }> = [
        { param: 'regionId', parent: 'region', child: 'zone', key: 'zones' },
        { param: 'zoneId', parent: 'zone', child: 'woreda', key: 'woredas' },
        { param: 'woredaId', parent: 'woreda', child: 'kebele', key: 'kebeles' },
      ]

      try {
        for (const step of steps) {
          const value = query[step.param] as string | undefined
          if (!value || value === 'all') continue
          return { [step.key]: await fetchGeoOptions(step.child, value) }
        }

        set.status = 400
        return { error: 'A valid query parameter (regionId, zoneId, or woredaId) is required.' }
      } catch (error: any) {
        console.error('API Error fetching locations:', error)
        set.status = 500
        return { error: 'An internal server error occurred.' }
      }
    })

    // The rows behind the current view, as CSV.
    .post('/data/export', async ({ body, set }) => {
      try {
        const { filters, format, filename } = (body || {}) as any

        if (!format || !filename) {
          set.status = 400
          return { message: 'Missing required parameters' }
        }
        if (format !== 'csv') {
          set.status = 400
          return { message: 'Unsupported format' }
        }

        const { sql, values } = prepareChartSql(SCOPE, (filters || {}) as ChartFilters)
        const rows = await fetchRecordsForExport(sql, values)

        return new Response(jsonToCsv(rows), {
          status: 200,
          headers: {
            'Content-Type': 'text/csv',
            'Content-Disposition': `attachment; filename="${filename}"`,
          },
        })
      } catch (error: any) {
        console.error('API Export Error:', error)
        set.status = 500
        return {
          message: 'Failed to export data',
          error: error instanceof Error ? error.message : 'Unknown error',
        }
      }
    })

    // Chart data. `charts` selects a subset; without it every panel's query runs.
    .get('/charts', async ({ query, set }) => {
      try {
        const filters = parseChartFilters(query)
        const requested = (query.charts as string | undefined)?.split(',').filter(Boolean)
        const targetCharts = requested?.length ? requested : Object.keys(CHART_QUERIES)

        const resultsArray = await Promise.all(
          targetCharts.map(chartId => executeChartQuery(chartId, filters))
        )

        const results: Record<string, any> = {}
        let successful = 0
        let failed = 0
        let totalExecutionTime = 0

        resultsArray.forEach(result => {
          results[result.chartName] = result
          totalExecutionTime += result.executionTime || 0
          if (result.success) successful++
          else failed++
        })

        return {
          success: true,
          data: results,
          summary: { total: targetCharts.length, successful, failed, totalExecutionTime },
          filters,
          timestamp: new Date().toISOString(),
        }
      } catch (error: any) {
        console.error('Charts API Error:', error)
        set.status = 500
        return {
          success: false,
          error: 'Failed to fetch chart data',
          message: error instanceof Error ? error.message : 'Unknown error',
        }
      }
    })

    .get('/charts/:chartId', async ({ params, query, set }) => {
      const chartName = params.chartId

      try {
        if (!CHART_QUERIES[chartName as keyof typeof CHART_QUERIES]) {
          set.status = 404
          return { success: false, error: `Chart query '${chartName}' not found.` }
        }

        const filters = parseChartFilters(query)
        const result = await executeChartQuery(chartName, filters)

        if (!result.success) {
          set.status = 500
          return { success: false, error: result.error }
        }

        return { success: true, data: result.data, executionTime: result.executionTime }
      } catch (error: any) {
        console.error(`API Error for [${chartName}]:`, error)
        set.status = 500
        return {
          success: false,
          error: error instanceof Error ? error.message : 'An unknown database error occurred',
        }
      }
    })
}
