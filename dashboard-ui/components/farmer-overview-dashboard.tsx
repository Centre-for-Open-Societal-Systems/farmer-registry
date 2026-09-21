"use client"

// Default landing dashboard: one screen, no scrolling, registry design language.
// Replaces the former tabbed analytics view whenever no registry-specific
// Farming Type filter is active. Band heights and column widths mirror the
// reference registry dashboard (measured at 1024px: KPI 53px, then bands of
// 182 / 180 / 107px, with the panel widths expressed as the same fractions).

import { useMemo } from "react"
import {
  AlertTriangle,
  BadgeCheck,
  Clock,
  Fingerprint,
  HandCoins,
  Home,
  Leaf,
  Ruler,
  Sprout,
  TrendingUp,
  UserRound,
  Users,
} from "lucide-react"
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"

import { useChartGroupData } from "@/hooks/use-data"
import { MapWhenVisible } from "@/components/lazy/map-when-visible"
import { DEFAULT_GEO_LABELS, type GeoLabels } from "@/components/global-filters-sidebar"
import {
  AlertRow,
  BRIGHT,
  BRIGHT_SERIES,
  BRIGHT_SOFT,
  DeltaChip,
  EmptyPanel,
  MiniColumnBars,
  MiniStat,
  ProgressRow,
  REGISTRY_COLORS,
  RegistryCard,
  RegistryDonut,
  RegistryIndicatorTile,
  RegistryStat,
  SegmentRow,
  SplitBar,
  formatCompact,
  formatFull,
} from "@/components/registry/registry-ui"
import {
  RegistryFilters,
  buildTrend,
  monthLabel,
  toNumber,
  useRegistryTrend,
} from "@/components/registry/registry-data"

const CHART_NAMES = [
  "farmerKpis",
  "farmersByRegion",
  "farmersByType",
  "farmersByAgeAndGender",
  "farmersByEducation",
  "farmersBySupportStatus",
  "farmersByImportStatus",
  "farmersByFarmerId",
  "farmersByRecordState",
  "landTenureSplit",
  "registryTrendByMonth",
  "registryCoverage",
]

const TYPE_PALETTE = BRIGHT_SERIES as unknown as string[]

// Keyed on the tenure labels this registry stores (LandOwnershipTypeEnum), so
// each keeps the same colour across reloads and filter changes.
const TENURE_COLORS: Record<string, string> = {
  Owner: BRIGHT.green,
  Tenant: BRIGHT.amber,
  "Crop Share": BRIGHT.tealSoft,
  Unknown: "#94A3B8",
}

const AGE_ORDER = ["0-18", "18-30", "30-50", "50-70", "70+", "Unknown"]

/** Level names come from the country pack singular ("Ward", "Woreda"). */
function plural(label: string): string {
  if (/[^aeiou]y$/i.test(label)) return `${label.slice(0, -1)}ies`
  if (/(s|x|z|ch|sh)$/i.test(label)) return `${label}es`
  return `${label}s`
}

export function FarmerOverviewDashboard({
  filters,
  geoJsonData,
  geoLabels = DEFAULT_GEO_LABELS,
  onMapFilterChange,
}: {
  filters: RegistryFilters
  geoJsonData?: any
  /** The country pack's own names for the administrative levels. */
  geoLabels?: GeoLabels
  onMapFilterChange?: (filters: Record<string, string>) => void
}) {
  const { data, loading, error } = useChartGroupData(CHART_NAMES, filters as any)
  const charts = data?.data || {}

  const kpis = charts.farmerKpis?.[0] || null
  const totalFarmers = toNumber(kpis?.total_farmers)
  const femaleFarmers = toNumber(kpis?.female_farmers)
  const maleFarmers = toNumber(kpis?.male_farmers)
  const householdHeads = toNumber(kpis?.household_heads)
  const landSize = toNumber(kpis?.total_land_size)
  const avgFarmSize = toNumber(kpis?.avg_farm_size)
  const landOwners = toNumber(kpis?.farmers_with_owned_land)
  const farmersWithId = toNumber(kpis?.farmers_with_id)

  const share = (value: number) => (totalFarmers > 0 ? (value / totalFarmers) * 100 : 0)

  const trend = useRegistryTrend(charts.registryTrendByMonth)
  const farmerTrend = buildTrend(trend.series, "farmers", { cumulative: true })
  const areaTrend = buildTrend(trend.series, "totalArea", { cumulative: true })
  const plotTrend = buildTrend(trend.series, "avgArea")

  const trendData = useMemo(
    () =>
      trend.series.slice(-24).map((point) => ({
        period: monthLabel(point.period),
        farmers: Math.round(point.farmers),
      })),
    [trend.series]
  )

  const latestMonth = trend.series.length ? trend.series[trend.series.length - 1] : null

  const typeSegments = useMemo(
    () =>
      (charts.farmersByType || [])
        .map((row: any, index: number) => {
          const value = toNumber(row.farmers)
          return {
            name: String(row.farming_type || "Unknown").replace(/_/g, " "),
            value,
            sub: formatCompact(value),
            color: TYPE_PALETTE[index % TYPE_PALETTE.length],
          }
        })
        .filter((segment: { value: number }) => segment.value > 0),
    [charts.farmersByType]
  )

  const farmersByRegion = useMemo(
    () =>
      (charts.farmersByRegion || []).map((row: any) => ({
        region: row.region,
        region_code: row.region_code,
        farmers: toNumber(row.farmers),
      })),
    [charts.farmersByRegion]
  )

  // Whether the shipped boundaries describe the country this registry holds.
  //
  // public/maps carries Ethiopia, matched on P-code (admin1Pcod = "ET14"). A
  // deployment whose country pack is something else stores different ids — the
  // Kamuntu pack uses slug paths like "kamuntu/chakula" — and no boundary would
  // ever match, so the choropleth would render a foreign outline with every unit
  // at zero and no way to drill into it. Where nothing matches, the panel falls
  // back to a ranked breakdown, which is clickable in the same way.
  const boundariesMatchRegistry = useMemo(() => {
    const features = geoJsonData?.features
    if (!Array.isArray(features) || !features.length || !farmersByRegion.length) return false

    const normalize = (value: any) => (value ? String(value).toUpperCase().replace(/[^A-Z0-9]/g, '') : '')
    const boundaryCodes = new Set(
      features.map((f: any) => normalize(f?.properties?.admin1Pcod)).filter(Boolean)
    )
    return farmersByRegion.some((row) => boundaryCodes.has(normalize(row.region_code)))
  }, [geoJsonData, farmersByRegion])

  const regionBreakdown = useMemo(() => {
    const max = farmersByRegion.reduce((acc, row) => Math.max(acc, row.farmers), 0)
    return [...farmersByRegion]
      .sort((a, b) => b.farmers - a.farmers)
      .map((row, index) => ({
        code: row.region_code,
        name: String(row.region || "Unknown"),
        farmers: row.farmers,
        // Relative to the largest region, so the bars use the full width rather
        // than all sitting at a few percent of the national total.
        percent: max > 0 ? (row.farmers / max) * 100 : 0,
        share: share(row.farmers),
        color: TYPE_PALETTE[index % TYPE_PALETTE.length],
      }))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [farmersByRegion, totalFarmers])

  const topRegionBars = useMemo(
    () =>
      [...farmersByRegion]
        .sort((a, b) => b.farmers - a.farmers)
        .slice(0, 6)
        .map((row) => ({
          name: String(row.region || "Unknown").split(/[\s/]/)[0],
          percent: share(row.farmers),
        })),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [farmersByRegion, totalFarmers]
  )

  const ageRows = useMemo(() => {
    const totals = new Map<string, number>()
    ;(charts.farmersByAgeAndGender || []).forEach((row: any) => {
      const group = String(row.age_group || "Unknown")
      totals.set(group, (totals.get(group) || 0) + toNumber(row.farmers))
    })

    return AGE_ORDER.filter((group) => (totals.get(group) || 0) > 0).map((group) => ({
      name: group === "70+" ? "70+ years" : `${group} years`,
      value: totals.get(group) || 0,
    }))
  }, [charts.farmersByAgeAndGender])

  const educationRows = useMemo(
    () =>
      (charts.farmersByEducation || [])
        .map((row: any) => ({ name: String(row.education || "Unknown"), value: toNumber(row.farmers) }))
        .filter((row: { value: number }) => row.value > 0)
        .slice(0, 6),
    [charts.farmersByEducation]
  )

  const tenureSegments = useMemo(
    () =>
      (charts.landTenureSplit || [])
        .map((row: any) => ({
          name: String(row.ownership_type || "Unknown"),
          value: toNumber(row.parcels),
          area: toNumber(row.area),
          color: TENURE_COLORS[row.ownership_type] || REGISTRY_COLORS.indigo,
        }))
        .filter((segment: { value: number }) => segment.value > 0),
    [charts.landTenureSplit]
  )
  const tenureParcels = tenureSegments.reduce((acc: number, segment: { value: number }) => acc + segment.value, 0)
  const tenureArea = tenureSegments.reduce((acc: number, segment: { area: number }) => acc + segment.area, 0)

  const recordStates = useMemo(() => {
    const totals = new Map<string, number>()
    ;(charts.farmersByRecordState || []).forEach((row: any) => {
      totals.set(String(row.record_state || "unknown").toLowerCase(), toNumber(row.farmers))
    })
    const approved = totals.get("approved") || 0
    const rejected = totals.get("rejected") || 0
    const open = ["pending", "under_review", "draft"].reduce((acc, key) => acc + (totals.get(key) || 0), 0)
    return { approved, rejected, open }
  }, [charts.farmersByRecordState])

  const coverage = charts.registryCoverage?.[0] || null
  const woredasTotal = toNumber(coverage?.woredas_total)
  const woredasCovered = toNumber(coverage?.woredas_covered)
  const woredaCoverage = woredasTotal > 0 ? (woredasCovered / woredasTotal) * 100 : 0

  // The reference dashboard tracks PSNP participation here. This registry has no
  // PSNP field; the safety-net population it does record is the farmers whose
  // income comes from government or NGO support, which is what this counts.
  const supportedFarmers = useMemo(
    () =>
      toNumber(
        (charts.farmersBySupportStatus || []).find((row: any) =>
          String(row.support_status).toLowerCase().includes("government")
        )?.farmers
      ),
    [charts.farmersBySupportStatus]
  )

  const importedFarmers = useMemo(
    () =>
      toNumber(
        (charts.farmersByImportStatus || []).find((row: any) => String(row.import_status).toLowerCase() === "imported")
          ?.farmers
      ),
    [charts.farmersByImportStatus]
  )

  const withFarmerId = useMemo(
    () =>
      toNumber(
        (charts.farmersByFarmerId || []).find((row: any) => String(row.id_status).toLowerCase().startsWith("with"))
          ?.farmers
      ),
    [charts.farmersByFarmerId]
  )

  const youthFarmers = useMemo(
    () =>
      (charts.farmersByAgeAndGender || [])
        .filter((row: any) => String(row.age_group) === "18-30")
        .reduce((acc: number, row: any) => acc + toNumber(row.farmers), 0),
    [charts.farmersByAgeAndGender]
  )

  const elderlyFarmers = useMemo(
    () =>
      (charts.farmersByAgeAndGender || [])
        .filter((row: any) => String(row.age_group) === "70+")
        .reduce((acc: number, row: any) => acc + toNumber(row.farmers), 0),
    [charts.farmersByAgeAndGender]
  )

  if (error) {
    return (
      <RegistryCard title="Farmer Profile Overview">
        <div className="px-4 pb-5 pt-3 text-[16.5px]" style={{ color: REGISTRY_COLORS.red }}>
          Failed to load dashboard data: {error}
        </div>
      </RegistryCard>
    )
  }

  return (
    <div className="flex min-h-full flex-col gap-3">
      {/* Band 1 — KPI ribbon (six tiles, content-weighted widths) */}
      <section className="grid flex-none grid-cols-2 gap-3 @[640px]:grid-cols-3 @[1400px]:grid-cols-[1.4fr_1.26fr_1.4fr_1.18fr_1.18fr_1.38fr]">
        <RegistryStat
          icon={<Users className="h-9 w-9" strokeWidth={2.5} />}
          iconBg={BRIGHT_SOFT.blue}
          iconColor={BRIGHT.blue}
          tint="blue"
          value={formatFull(totalFarmers)}
          label="Registered Farmers"
          delta={farmerTrend.delta}
          loading={loading}
        />
        <RegistryStat
          icon={<Home className="h-9 w-9" strokeWidth={2.5} />}
          iconBg={BRIGHT_SOFT.green}
          iconColor={BRIGHT.green}
          tint="green"
          value={formatFull(householdHeads)}
          label="Household Heads"
          note={`${share(householdHeads).toFixed(1)}% of farmers`}
          loading={loading}
        />
        <RegistryStat
          icon={<Sprout className="h-9 w-9" strokeWidth={2.5} />}
          iconBg={BRIGHT_SOFT.orange}
          iconColor={BRIGHT.orange}
          tint="peach"
          value={formatCompact(landSize)}
          unit="ha"
          label="Land Registered"
          delta={areaTrend.delta}
          loading={loading}
        />
        <RegistryStat
          icon={<UserRound className="h-9 w-9" strokeWidth={2.5} />}
          iconBg={BRIGHT_SOFT.violet}
          iconColor={BRIGHT.violet}
          tint="violet"
          value={`${share(femaleFarmers).toFixed(1)}%`}
          label="Women"
          note={`${formatFull(femaleFarmers)} farmers`}
          loading={loading}
        />
        <RegistryStat
          icon={<HandCoins className="h-9 w-9" strokeWidth={2.5} />}
          iconBg={BRIGHT_SOFT.teal}
          iconColor={BRIGHT.teal}
          tint="teal"
          value={`${share(landOwners).toFixed(1)}%`}
          label="Land Owners"
          note={`${formatFull(landOwners)} farmers`}
          loading={loading}
        />
        <RegistryStat
          icon={<Ruler className="h-9 w-9" strokeWidth={2.5} />}
          iconBg={BRIGHT_SOFT.amber}
          iconColor={BRIGHT.amber}
          tint="amber"
          value={avgFarmSize.toFixed(2)}
          unit="ha"
          label="Average Farm Size"
          delta={plotTrend.delta}
          loading={loading}
        />
      </section>

      {/* Band 2 — map (lead panel), trend, snapshot, group insights */}
      <section className="grid min-h-0 flex-none grid-cols-1 gap-3 @[720px]:grid-cols-2 @[1400px]:min-h-[300px] @[1400px]:grid-cols-[2.4fr_1.5fr_2.65fr_1.6fr]">
        <RegistryCard
          dense
          title={`Farmers by ${geoLabels.region}`}
          subtitle={`Click a ${geoLabels.region.toLowerCase()} to drill down`}
          className="flex min-h-[260px] flex-col overflow-hidden @[1400px]:min-h-0"
          bodyClassName={boundariesMatchRegistry ? "relative min-h-0 flex-1" : "min-h-0 flex-1 overflow-y-auto"}
        >
          {boundariesMatchRegistry ? (
            <MapWhenVisible
              fill
              legendPosition="below"
              className="absolute inset-0 flex flex-col"
              minHeight="100%"
              variant="registry"
              popOutTitle={`Farmers by ${geoLabels.region}`}
              valueLabel="farmers"
              valueFormatter={(value: number) => formatCompact(value)}
              currentFilters={{
                region: filters.region !== "all" ? filters.region : undefined,
                zone: filters.zone !== "all" ? filters.zone : undefined,
                woreda: filters.woreda !== "all" ? filters.woreda : undefined,
                kebele: filters.kebele !== "all" ? filters.kebele : undefined,
              }}
              onFilterChange={(mapFilters: any) => onMapFilterChange?.(mapFilters)}
              farmerData={farmersByRegion}
              geoJsonData={geoJsonData}
            />
          ) : regionBreakdown.length === 0 ? (
            <EmptyPanel message="No registrations yet" />
          ) : (
            <div className="flex flex-col gap-2 px-1 py-1">
              {regionBreakdown.map((row) => (
                <button
                  key={row.code || row.name}
                  type="button"
                  onClick={() => row.code && onMapFilterChange?.({ region: row.code })}
                  disabled={!row.code}
                  className="w-full rounded-[6px] px-1 py-0.5 text-left transition-colors enabled:hover:bg-black/[0.04] disabled:cursor-default"
                  title={`${row.name} — ${formatFull(row.farmers)} farmers (${row.share.toFixed(1)}%)`}
                >
                  <ProgressRow
                    label={row.name}
                    value={formatCompact(row.farmers)}
                    percent={row.percent}
                    color={row.color}
                    barWidth="96px"
                  />
                </button>
              ))}
            </div>
          )}
        </RegistryCard>

        <RegistryCard
          dense
          title="Registration Trend"
          subtitle="Farmers registered per month"
          actions={farmerTrend.delta ? <DeltaChip delta={farmerTrend.delta} /> : undefined}
          className="flex min-h-[220px] flex-col @[1400px]:min-h-0"
          bodyClassName="min-h-0 flex-1 px-1 pb-1 pt-1"
        >
          {trendData.length === 0 ? (
            <EmptyPanel message="No registrations in range" className="px-3 pb-3" />
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={trendData} margin={{ top: 6, right: 10, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="overview-trend" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={BRIGHT.blueSoft} stopOpacity={0.38} />
                    <stop offset="100%" stopColor={BRIGHT.blueSoft} stopOpacity={0.03} />
                  </linearGradient>
                </defs>
                <CartesianGrid vertical={false} stroke={REGISTRY_COLORS.line2} />
                <XAxis
                  dataKey="period"
                  tickLine={false}
                  axisLine={false}
                  interval="preserveStartEnd"
                  minTickGap={28}
                  tick={{ fontSize: 9.5, fill: REGISTRY_COLORS.muted }}
                />
                <YAxis
                  tickLine={false}
                  axisLine={false}
                  width={34}
                  tick={{ fontSize: 9.5, fill: REGISTRY_COLORS.muted }}
                  tickFormatter={(value: number) => formatCompact(value)}
                />
                <Tooltip
                  contentStyle={{ borderRadius: 10, border: `1px solid ${REGISTRY_COLORS.line}`, fontSize: 11 }}
                  formatter={(value: any) => [`${formatFull(toNumber(value))} farmers`, "Registered"]}
                />
                <Area
                  type="monotone"
                  dataKey="farmers"
                  stroke={BRIGHT.blue}
                  strokeWidth={2}
                  fill="url(#overview-trend)"
                  dot={{ r: 1.8, fill: "#fff", stroke: BRIGHT.blue, strokeWidth: 1.4 }}
                  activeDot={{ r: 3.5, fill: BRIGHT.blue, stroke: "#fff", strokeWidth: 1.6 }}
                />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </RegistryCard>

        <RegistryCard
          dense
          title="Registry Snapshot"
          subtitle="Farmers by farming type"
          className="flex min-h-[260px] flex-col @[1400px]:min-h-0"
          bodyClassName="flex min-h-0 flex-1 items-start overflow-hidden"
        >
          <RegistryDonut
            subInline
            ringSize={150}
            className="w-full"
            segments={typeSegments}
            centerValue={formatCompact(totalFarmers)}
            centerLabel="Farmers"
            totalLabel="Total"
            totalValue={formatFull(totalFarmers)}
          />
        </RegistryCard>

        <RegistryCard
          dense
          title="Farmer Group Insights"
          className="flex min-h-0 flex-col"
          bodyClassName="grid min-h-0 flex-1 auto-rows-fr gap-3 px-3 pb-3 pt-2.5"
        >
          <SegmentRow
            icon={<UserRound className="h-4 w-4" />}
            iconBg={BRIGHT_SOFT.pink}
            iconColor={BRIGHT.pink}
            label="Female farmers"
            value={formatFull(femaleFarmers)}
            share={`(${share(femaleFarmers).toFixed(1)}%)`}
          />
          <SegmentRow
            icon={<Home className="h-4 w-4" />}
            iconBg={BRIGHT_SOFT.violet}
            iconColor={BRIGHT.violet}
            label="Household heads"
            value={formatFull(householdHeads)}
            share={`(${share(householdHeads).toFixed(1)}%)`}
          />
          <SegmentRow
            icon={<Users className="h-4 w-4" />}
            iconBg={BRIGHT_SOFT.blue}
            iconColor={BRIGHT.blue}
            label="Youth farmers (18–30)"
            value={formatFull(youthFarmers)}
            share={`(${share(youthFarmers).toFixed(1)}%)`}
          />
          <SegmentRow
            icon={<Leaf className="h-4 w-4" />}
            iconBg={BRIGHT_SOFT.teal}
            iconColor={BRIGHT.teal}
            label="Farmers aged 70+"
            value={formatFull(elderlyFarmers)}
            share={`(${share(elderlyFarmers).toFixed(1)}%)`}
          />
          <SegmentRow
            icon={<HandCoins className="h-4 w-4" />}
            iconBg={BRIGHT_SOFT.amber}
            iconColor={BRIGHT.amber}
            label="Gov / NGO supported"
            value={formatFull(supportedFarmers)}
            share={`(${share(supportedFarmers).toFixed(1)}%)`}
          />
        </RegistryCard>
      </section>

      {/* Band 3 — farm profile, coverage, demography, land, alerts rail */}
      <section className="grid min-h-0 flex-none grid-cols-1 gap-3 @[720px]:grid-cols-2 @[860px]:grid-cols-3 @[1400px]:min-h-[290px] @[1400px]:grid-cols-[1.78fr_2.01fr_1.41fr_1.23fr_1.7fr]">
        <RegistryCard
          dense
          title="Farm Profile"
          className="flex min-h-0 flex-col"
          bodyClassName="flex min-h-0 flex-1 flex-col gap-2 px-3 pb-2.5 pt-2"
        >
          <div className="grid grid-cols-3 gap-2">
            <MiniStat value={avgFarmSize.toFixed(2)} unit="ha" label="Avg. farm size" />
            <MiniStat value={`${share(landOwners).toFixed(0)}%`} label="Land owners" />
            <MiniStat value={`${share(femaleFarmers).toFixed(0)}%`} label="Female" />
          </div>
          <div className="grid flex-1 auto-rows-fr gap-2">
            <ProgressRow
              icon={<Home className="h-3 w-3" />}
              label="Farmers heading a household"
              value={`${share(householdHeads).toFixed(0)}%`}
              percent={share(householdHeads)}
              color={BRIGHT.blueSoft}
            />
            <ProgressRow
              icon={<Users className="h-3 w-3" />}
              label="Youth farmers (18–30)"
              value={`${share(youthFarmers).toFixed(0)}%`}
              percent={share(youthFarmers)}
              color={BRIGHT.tealSoft}
            />
            <ProgressRow
              icon={<HandCoins className="h-3 w-3" />}
              label="Gov / NGO supported"
              value={`${share(supportedFarmers).toFixed(0)}%`}
              percent={share(supportedFarmers)}
              color={BRIGHT.violet}
            />
            <ProgressRow
              icon={<Leaf className="h-3 w-3" />}
              label="Farmers aged 70+"
              value={`${share(elderlyFarmers).toFixed(0)}%`}
              percent={share(elderlyFarmers)}
              color={BRIGHT.amber}
            />
          </div>
        </RegistryCard>

        <RegistryCard
          dense
          title="Geographic Coverage"
          subtitle={`${plural(geoLabels.woreda)} reached by the registry`}
          className="flex min-h-0 flex-col"
          bodyClassName="flex min-h-0 flex-1 flex-col gap-1 px-1 pb-2.5 pt-0"
        >
          {woredasTotal === 0 ? (
            <EmptyPanel message="No coverage data" />
          ) : (
            <>
              <RegistryDonut
                subInline
                ringSize={110}
                className="flex-none gap-3 px-2 pb-1 pt-1"
                segments={[
                  {
                    name: `Covered ${plural(geoLabels.woreda).toLowerCase()}`,
                    value: woredasCovered,
                    sub: formatFull(woredasCovered),
                    color: BRIGHT.teal,
                  },
                  {
                    name: "Not covered",
                    value: Math.max(0, woredasTotal - woredasCovered),
                    sub: formatFull(Math.max(0, woredasTotal - woredasCovered)),
                    color: BRIGHT.red,
                  },
                ]}
                centerValue={`${woredaCoverage.toFixed(1)}%`}
                centerLabel="Coverage"
                totalLabel={plural(geoLabels.woreda)}
                totalValue={formatFull(woredasTotal)}
              />
              <div className="flex min-h-[68px] flex-1 flex-col gap-1 px-2 pt-0.5">
                <span className="text-[13.5px]" style={{ color: REGISTRY_COLORS.muted }}>
                  Share of farmers by leading {geoLabels.region.toLowerCase()}
                </span>
                <MiniColumnBars items={topRegionBars} color={BRIGHT.teal} />
              </div>
            </>
          )}
        </RegistryCard>

        <RegistryCard
          dense
          title="Demographic Profile"
          className="flex min-h-0 flex-col"
          bodyClassName="flex min-h-0 flex-1 flex-col gap-2 px-3 pb-2.5 pt-2"
        >
          <SplitBar
            segments={[
              { name: "Male", value: maleFarmers, color: BRIGHT.blue },
              { name: "Female", value: femaleFarmers, color: BRIGHT.pink },
              {
                name: "Unknown",
                value: Math.max(0, totalFarmers - maleFarmers - femaleFarmers),
                color: "#CBD5E1",
              },
            ].filter((segment) => segment.value > 0)}
          />
          {ageRows.length === 0 ? (
            <EmptyPanel message="No age data" />
          ) : (
            <div className="grid flex-1 auto-rows-fr gap-2">
              {ageRows.map((row) => (
                <ProgressRow
                  key={row.name}
                  label={row.name}
                  value={`${share(row.value).toFixed(1)}%`}
                  percent={share(row.value)}
                  color={BRIGHT.blueSoft}
                  barWidth="46px"
                />
              ))}
            </div>
          )}
        </RegistryCard>

        <RegistryCard
          dense
          title="Land Tenure"
          className="flex min-h-0 flex-col"
          bodyClassName="flex min-h-0 flex-1 flex-col gap-2 px-3 pb-2.5 pt-1.5"
        >
          {tenureSegments.length === 0 ? (
            <EmptyPanel message="No land records" />
          ) : (
            <>
              <div>
                <div className="flex items-baseline gap-1.5">
                  <span className="text-[24px] font-bold leading-none" style={{ color: REGISTRY_COLORS.ink }}>
                    {formatCompact(tenureArea)}
                  </span>
                  <span className="text-[15px] font-semibold" style={{ color: REGISTRY_COLORS.ink2 }}>
                    ha
                  </span>
                </div>
                <div className="mt-0.5 text-[14px]" style={{ color: REGISTRY_COLORS.muted }}>
                  {formatFull(tenureParcels)} parcels registered
                </div>
              </div>
              <div className="grid flex-1 auto-rows-fr gap-2">
                {tenureSegments.map((segment: { name: string; value: number; area: number; color: string }) => (
                  <ProgressRow
                    key={segment.name}
                    label={segment.name}
                    value={formatCompact(segment.value)}
                    percent={tenureParcels > 0 ? (segment.value / tenureParcels) * 100 : 0}
                    color={segment.color}
                    barWidth="40px"
                  />
                ))}
              </div>
            </>
          )}
        </RegistryCard>

        <RegistryCard
          dense
          title="Alerts & Notifications"
          className="flex min-h-0 flex-col"
          bodyClassName="grid min-h-0 flex-1 auto-rows-fr gap-3 px-3 pb-3 pt-2.5"
        >
          <AlertRow
            icon={<Clock className="h-4 w-4" />}
            tone="warning"
            title="Records awaiting approval"
            detail={`${formatFull(recordStates.open)} profiles are pending, in review or still draft.`}
            context={`${share(recordStates.open).toFixed(1)}%`}
          />
          <AlertRow
            icon={<AlertTriangle className="h-4 w-4" />}
            tone="danger"
            title="Rejected records"
            detail={`${formatFull(recordStates.rejected)} profiles need correction before approval.`}
            context={`${share(recordStates.rejected).toFixed(1)}%`}
          />
          <AlertRow
            icon={<Fingerprint className="h-4 w-4" />}
            tone="info"
            title="Missing national ID"
            detail={`${formatFull(Math.max(0, totalFarmers - farmersWithId))} profiles have no national ID linked.`}
            context={`${(100 - share(farmersWithId)).toFixed(1)}%`}
          />
          <AlertRow
            icon={<TrendingUp className="h-4 w-4" />}
            tone="info"
            title="Latest registrations"
            detail={`${formatFull(Math.round(latestMonth?.farmers || 0))} farmers registered in the most recent month.`}
            context={latestMonth ? monthLabel(latestMonth.period) : "—"}
          />
        </RegistryCard>
      </section>

      {/* Band 4 — education, key indicators */}
      <section className="grid min-h-0 flex-none grid-cols-1 gap-3 @[720px]:grid-cols-2 @[860px]:min-h-[210px] @[860px]:grid-cols-[1fr_1fr]">
        <RegistryCard
          dense
          title="Education Profile"
          className="flex min-h-0 flex-col overflow-hidden"
          bodyClassName="grid min-h-0 flex-1 auto-rows-fr gap-1.5 px-3 pb-2.5 pt-2"
        >
          {educationRows.length === 0 ? (
            <EmptyPanel message="No education data" />
          ) : (
            educationRows.map((row: { name: string; value: number }, index: number) => (
              <ProgressRow
                key={row.name}
                label={row.name}
                value={`${share(row.value).toFixed(1)}%`}
                percent={share(row.value)}
                color={BRIGHT_SERIES[index % BRIGHT_SERIES.length]}
                barWidth="96px"
              />
            ))
          )}
        </RegistryCard>

        <RegistryCard
          dense
          title="Key Indicators"
          className="flex min-h-0 flex-col"
          bodyClassName="grid min-h-0 flex-1 grid-cols-2 content-center gap-2.5 px-3 pb-3 pt-2"
        >
          <RegistryIndicatorTile
            icon={<BadgeCheck className="h-4 w-4" />}
            iconBg={BRIGHT_SOFT.green}
            iconColor={BRIGHT.green}
            value={`${share(recordStates.approved).toFixed(1)}%`}
            label="Approved records"
          />
          <RegistryIndicatorTile
            icon={<Fingerprint className="h-4 w-4" />}
            iconBg={BRIGHT_SOFT.teal}
            iconColor={BRIGHT.teal}
            value={`${share(farmersWithId).toFixed(1)}%`}
            label="With national ID"
          />
          <RegistryIndicatorTile
            icon={<UserRound className="h-4 w-4" />}
            iconBg={BRIGHT_SOFT.blue}
            iconColor={BRIGHT.blue}
            value={`${share(withFarmerId).toFixed(1)}%`}
            label="With farmer ID"
          />
          <RegistryIndicatorTile
            icon={<Sprout className="h-4 w-4" />}
            iconBg={BRIGHT_SOFT.amber}
            iconColor={BRIGHT.amber}
            value={`${share(importedFarmers).toFixed(1)}%`}
            label="Imported records"
          />
        </RegistryCard>
      </section>

      {/* Goal ribbon */}
      <div
        className="flex flex-none items-center gap-2 rounded-xl border px-4 py-1 text-[15px]"
        style={{ borderColor: "#CBE9D6", background: REGISTRY_COLORS.g100, color: REGISTRY_COLORS.g900 }}
      >
        <strong className="font-semibold">Our Goal:</strong>
        <span className="min-w-0 flex-1 truncate">
          Every farmer registered, every hectare mapped — one trusted farmer profile for inclusive agricultural
          services.
        </span>
        <Leaf className="h-4 w-4 flex-none" style={{ color: REGISTRY_COLORS.g700 }} />
      </div>
    </div>
  )
}
