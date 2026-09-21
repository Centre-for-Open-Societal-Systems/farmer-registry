"use client"

// Presentation primitives for the Crop Sown and Livestock registry dashboards.
// These intentionally sit outside the shadcn Card/Chart stack so the registry
// views can match the OpenG2P reference design without restyling every tab.

import React from "react"
import { AlertTriangle, CircleAlert, Info } from "lucide-react"

export const REGISTRY_COLORS = {
  card: "#FFFFFF",
  ink: "#000000",
  ink2: "#000000",
  muted: "#000000",
  line: "#E6EAE8",
  line2: "#EFF2F0",
  g900: "#0F5132",
  g700: "#15803D",
  g600: "#1B7F4C",
  g500: "#22C55E",
  g100: "#E7F5EC",
  g50: "#F2F8F4",
  amber: "#F59E0B",
  amberSoft: "#F0A93B",
  teal: "#0D9488",
  indigo: "#6366F1",
  red: "#DC2626",
} as const

/**
 * Saturated palette for figures, series and icons, sampled from the reference
 * dashboard so charts read as vividly there as they do in the design.
 */
export const BRIGHT = {
  blue: "#2563EB",
  blueSoft: "#3B82F6",
  sky: "#0EA5E9",
  teal: "#0E7490",
  tealSoft: "#14B8A6",
  green: "#16A34A",
  greenSoft: "#22C55E",
  lime: "#84CC16",
  yellow: "#EAB308",
  amber: "#F59E0B",
  orange: "#F97316",
  red: "#EF4444",
  crimson: "#DC2626",
  violet: "#8B5CF6",
  purple: "#A855F7",
  pink: "#EC4899",
} as const

/** Icon-tile backgrounds paired with the BRIGHT foreground colours. */
export const BRIGHT_SOFT = {
  blue: "#E1EDFD",
  sky: "#E0F2FE",
  teal: "#DBF1F3",
  green: "#DCFCE7",
  lime: "#ECFCCB",
  yellow: "#FEF9C3",
  amber: "#FEF3C7",
  orange: "#FFEDD5",
  red: "#FEE2E2",
  violet: "#EDE9FE",
  purple: "#FAE8FF",
  pink: "#FCE7F3",
} as const

/**
 * Card washes for the overview KPI ribbon: a diagonal tint fading to white with
 * a matching border, as in the reference stat cards.
 */
export const STAT_TINTS = {
  blue: { from: "#D6E8FC", to: "#F8FBFE", border: "#C7DDF7" },
  green: { from: "#D6EFE6", to: "#F6FCF9", border: "#C6E7D8" },
  peach: { from: "#F9E2D4", to: "#FEF8F3", border: "#F3D6C3" },
  violet: { from: "#E1E1F8", to: "#F6F6FC", border: "#D3D3F1" },
  teal: { from: "#D8F1F8", to: "#F7FCFE", border: "#C7E8F1" },
  amber: { from: "#FBEFD2", to: "#FEFBF3", border: "#F5E3B8" },
  pink: { from: "#FBE0EE", to: "#FEF7FB", border: "#F6CFE3" },
  /** Reserved for figures that report a failure, not just a low value. */
  red: { from: "#FBD9D9", to: "#FEF6F6", border: "#F4C0C0" },
} as const

export type StatTint = keyof typeof STAT_TINTS

/** Ordered series ramp for donut slices and ranked bars. */
export const BRIGHT_SERIES = [
  BRIGHT.blue,
  BRIGHT.orange,
  BRIGHT.tealSoft,
  BRIGHT.violet,
  BRIGHT.amber,
  BRIGHT.pink,
  BRIGHT.greenSoft,
  BRIGHT.sky,
] as const

/** Five-step choropleth ramp shared by the map and its legend. */
export const REGISTRY_RAMP = ["#F0FDF4", "#BBF7D0", "#4ADE80", "#16A34A", "#15803D"] as const

export const CARD_SHADOW = "0 1px 2px rgba(16,24,40,.04), 0 1px 3px rgba(16,24,40,.06)"

// ---------------------------------------------------------------- formatting

export function formatFull(value: number, digits = 0): string {
  if (!Number.isFinite(value)) return "0"
  return value.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

export function formatCompact(value: number): string {
  if (!Number.isFinite(value)) return "0"
  const abs = Math.abs(value)
  if (abs >= 1_000_000_000) return `${trimZero(value / 1_000_000_000)}B`
  if (abs >= 1_000_000) return `${trimZero(value / 1_000_000)}M`
  if (abs >= 1_000) return `${trimZero(value / 1_000)}K`
  return formatFull(value)
}

function trimZero(value: number): string {
  const rounded = Math.round(value * 10) / 10
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1)
}

// ------------------------------------------------------------------- surface

export function RegistryCard({
  title,
  subtitle,
  actions,
  icon,
  iconBg = BRIGHT_SOFT.blue,
  iconColor = BRIGHT.blue,
  children,
  className = "",
  bodyClassName = "",
  dense = false,
}: {
  title?: React.ReactNode
  subtitle?: React.ReactNode
  actions?: React.ReactNode
  /** Tinted tile before the title, so a card can be identified without reading it. */
  icon?: React.ReactNode
  iconBg?: string
  iconColor?: string
  children: React.ReactNode
  className?: string
  bodyClassName?: string
  /** Tighter header padding and type, for panels packed into a single screen. */
  dense?: boolean
}) {
  return (
    <div
      className={`relative overflow-hidden rounded-xl border bg-white ${className}`}
      style={{ borderColor: REGISTRY_COLORS.line, boxShadow: CARD_SHADOW }}
    >
      {(title || actions) && (
        <div className={`relative ${dense ? "px-3 pt-2" : "px-4 pt-3"}`}>
          {icon && (
            <span
              className={`absolute left-3 top-2 grid flex-none place-items-center rounded-[7px] ${dense ? "h-5 w-5" : "h-6 w-6"}`}
              style={{ background: iconBg, color: iconColor }}
            >
              {icon}
            </span>
          )}
          <div className="min-w-0 text-center">
            {title && (
              <h3
                className={`truncate ${dense ? "text-[16px]" : "text-[17.5px]"} font-bold leading-tight tracking-[-0.1px]`}
                style={{ color: REGISTRY_COLORS.ink }}
              >
                {title}
              </h3>
            )}
            {subtitle && (
              <p className={`truncate ${dense ? "text-[13px] font-semibold" : "mt-0.5 text-[14px] font-semibold"}`} style={{ color: REGISTRY_COLORS.muted }}>
                {subtitle}
              </p>
            )}
          </div>
          {actions && <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-1.5">{actions}</div>}
        </div>
      )}
      <div className={`overflow-hidden ${bodyClassName}`}>{children}</div>
    </div>
  )
}

// ----------------------------------------------------------------- sparkline

export function Sparkline({
  values,
  color,
  className = "",
}: {
  values: number[]
  color: string
  className?: string
}) {
  const points = React.useMemo(() => {
    if (!values.length) return ""
    const width = 120
    const height = 34
    const pad = 3
    const min = Math.min(...values)
    const max = Math.max(...values)
    const span = max - min || 1
    const step = values.length > 1 ? (width - pad * 2) / (values.length - 1) : 0

    return values
      .map((value, index) => {
        const x = pad + index * step
        const y = height - pad - ((value - min) / span) * (height - pad * 2)
        return `${x.toFixed(1)},${y.toFixed(1)}`
      })
      .join(" ")
  }, [values])

  if (!points) return null

  return (
    <svg
      className={`h-[26px] w-[88px] flex-none ${className}`}
      viewBox="0 0 120 34"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth={1.6}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  )
}

// ------------------------------------------------------------------ kpi card

export type KpiDelta = {
  percent: number
  note: string
}

export function DeltaChip({ delta, className = "" }: { delta: KpiDelta; className?: string }) {
  const direction = Math.abs(delta.percent) < 0.05 ? "flat" : delta.percent > 0 ? "up" : "down"
  const style = {
    up: { background: BRIGHT_SOFT.green, color: BRIGHT.green },
    down: { background: BRIGHT_SOFT.red, color: BRIGHT.crimson },
    flat: { background: "#F1F5F9", color: "#64748B" },
  }[direction]
  const arrow = direction === "up" ? "▲" : direction === "down" ? "▼" : "–"

  return (
    <span
      className={`whitespace-nowrap rounded-[5px] px-1.5 py-0.5 text-[14px] font-bold ${className}`}
      style={style}
      title={delta.note}
    >
      {arrow} {Math.abs(delta.percent).toFixed(1)}%
    </span>
  )
}

export function RegistryKpi({
  icon,
  iconBg,
  iconColor,
  value,
  valueColor,
  unit,
  label,
  delta,
  spark,
  sparkColor,
  tint,
  loading = false,
}: {
  icon: React.ReactNode
  iconBg: string
  iconColor: string
  value: string
  valueColor?: string
  unit?: string
  label: string
  delta?: KpiDelta
  spark?: number[]
  sparkColor: string
  /** Applies the same pastel metric wash used by the overview ribbon. */
  tint?: StatTint
  loading?: boolean
}) {
  const direction = !delta || Math.abs(delta.percent) < 0.05 ? "flat" : delta.percent > 0 ? "up" : "down"
  const chipStyle = {
    up: { background: BRIGHT_SOFT.green, color: BRIGHT.green },
    down: { background: BRIGHT_SOFT.red, color: BRIGHT.crimson },
    flat: { background: "#F1F5F9", color: "#64748B" },
  }[direction]
  const arrow = direction === "up" ? "▲" : direction === "down" ? "▼" : "–"
  const wash = tint ? STAT_TINTS[tint] : null

  return (
    <div
      className="grid grid-cols-[auto_minmax(0,1fr)] items-center gap-x-3 rounded-xl border px-4 pb-3 pt-3"
      style={{
        background: wash ? `linear-gradient(135deg, ${wash.from} 0%, ${wash.to} 100%)` : REGISTRY_COLORS.card,
        borderColor: wash ? wash.border : REGISTRY_COLORS.line,
        boxShadow: CARD_SHADOW,
      }}
    >
      <div
        className={
          wash
            ? "grid h-12 w-12 place-items-center"
            : "grid h-[38px] w-[38px] place-items-center rounded-[10px]"
        }
        style={wash ? { color: iconColor } : { background: iconBg, color: iconColor }}
      >
        {icon}
      </div>

      <div className="min-w-0">
        <div className="truncate text-[15.5px] font-medium" style={{ color: wash ? "#000000" : REGISTRY_COLORS.muted }}>
          {label}
        </div>
        <div
          className="text-[26px] font-bold leading-[1.15] tracking-[-0.6px]"
          style={{ color: valueColor || REGISTRY_COLORS.ink }}
        >
          {loading ? <span className="text-[22px] font-semibold opacity-40">—</span> : value}
          {unit && !loading && (
            <span className="ml-1 text-[17.5px] font-semibold tracking-normal" style={{ color: REGISTRY_COLORS.ink2 }}>
              {unit}
            </span>
          )}
        </div>
      </div>

      <div className="col-span-full mt-[11px] flex items-center gap-[7px]">
        {delta && (
          <span className="whitespace-nowrap rounded-[5px] px-1.5 py-0.5 text-[14.5px] font-bold" style={chipStyle}>
            {arrow} {Math.abs(delta.percent).toFixed(1)}%
          </span>
        )}
        {delta && (
          <span className="truncate text-[14.5px] font-medium" style={{ color: REGISTRY_COLORS.muted }}>
            {delta.note}
          </span>
        )}
        {spark && spark.length > 1 && (
          <span className="ml-auto">
            <Sparkline values={spark} color={sparkColor} />
          </span>
        )}
      </div>
    </div>
  )
}

// ------------------------------------------------- compact overview elements

/**
 * KPI tile for the one-screen overview: icon block on the left, then caption,
 * figure and change note stacked beside it, as in the reference dashboard.
 */
export function RegistryStat({
  icon,
  iconBg,
  iconColor,
  value,
  valueColor,
  unit,
  label,
  delta,
  note,
  tint,
  size = "default",
  loading = false,
}: {
  icon: React.ReactNode
  iconBg: string
  iconColor: string
  value: string
  /** Overrides the figure colour, for metrics that should read as a warning. */
  valueColor?: string
  unit?: string
  label: string
  delta?: KpiDelta
  /** Static caption under the figure, used when there is no period comparison. */
  note?: string
  /** Washes the card in a tint instead of plain white. */
  tint?: StatTint
  /**
   * "lg" stacks the label above the figure instead of setting it beside the
   * icon. In a narrow column that is the only way to grow the card: the label
   * gets the full width, so it can be larger without truncating.
   */
  size?: "default" | "lg"
  loading?: boolean
}) {
  const direction = !delta || Math.abs(delta.percent) < 0.05 ? "flat" : delta.percent > 0 ? "up" : "down"
  const deltaColor = { up: BRIGHT.green, down: BRIGHT.red, flat: "#64748B" }[direction]
  const arrow = direction === "up" ? "▲" : direction === "down" ? "▼" : "–"
  const wash = tint ? STAT_TINTS[tint] : null
  const large = size === "lg"

  const caption =
    delta && !loading ? (
      <div
        className={large ? "text-[11px] font-semibold leading-tight" : "text-[14px] font-semibold leading-tight"}
        style={{ color: deltaColor }}
      >
        {arrow} {Math.abs(delta.percent).toFixed(1)}%{" "}
        <span className="font-normal" style={{ color: REGISTRY_COLORS.muted }}>
          {delta.note}
        </span>
      </div>
    ) : !delta && note && !loading ? (
      <div
        className={large ? "text-[11px] leading-tight" : "text-[14px] font-medium leading-tight"}
        style={{ color: REGISTRY_COLORS.muted }}
      >
        {note}
      </div>
    ) : null

  const figure = (
    <div className={`flex items-baseline gap-1 ${large ? "" : "justify-center"}`}>
      <span
        className={
          large
            ? "truncate text-[26px] font-bold leading-[1.1] tracking-[-0.7px] @[1180px]:text-[28px]"
            : "text-[36px] font-extrabold leading-[1.15] tracking-[-0.6px] @[1100px]:text-[40px]"
        }
        style={{ color: valueColor || REGISTRY_COLORS.ink }}
      >
        {loading ? "—" : value}
      </span>
      {unit && !loading && (
        <span
          className={
            large ? "text-[13px] font-semibold @[1180px]:text-[14px]" : "text-[20px] font-bold @[1100px]:text-[22px]"
          }
          style={{ color: REGISTRY_COLORS.ink2 }}
        >
          {unit}
        </span>
      )}
    </div>
  )

  const cardStyle = {
    background: wash ? `linear-gradient(135deg, ${wash.from} 0%, ${wash.to} 100%)` : REGISTRY_COLORS.card,
    borderColor: wash ? wash.border : REGISTRY_COLORS.line,
    boxShadow: CARD_SHADOW,
  }

  if (large) {
    return (
      <div className="flex min-w-0 flex-col gap-1 rounded-xl border px-3 py-2" style={cardStyle}>
        <div className="flex items-start gap-2">
          <div
            className={
              wash
                ? "grid h-8 w-8 flex-none place-items-center"
                : "grid h-8 w-8 flex-none place-items-center rounded-[9px]"
            }
            style={wash ? { color: iconColor } : { background: iconBg, color: iconColor }}
          >
            {icon}
          </div>
          <div
            className="min-w-0 flex-1 text-[13px] font-semibold leading-[1.25] @[1180px]:text-[13.5px]"
            style={{ color: wash ? "#475569" : REGISTRY_COLORS.muted }}
            title={label}
          >
            {label}
          </div>
        </div>
        <div className="min-w-0">
          {figure}
          {caption}
        </div>
      </div>
    )
  }

  return (
    <div className="flex min-w-0 items-center gap-3 rounded-xl border px-3 py-3.5" style={cardStyle}>
      <div
        className={
          wash
            ? "grid h-14 w-14 flex-none place-items-center"
            : "grid h-[46px] w-[46px] flex-none place-items-center rounded-[12px]"
        }
        style={wash ? { color: iconColor } : { background: iconBg, color: iconColor }}
      >
        {icon}
      </div>

      <div className="min-w-0 flex-1 text-center">
        <div
          className="truncate text-[16.5px] font-bold leading-snug @[1100px]:text-[18px]"
          style={{ color: wash ? "#000000" : REGISTRY_COLORS.muted }}
          title={label}
        >
          {label}
        </div>
        {figure}
        {caption}
      </div>
    </div>
  )
}

/** Compact figure tile with an icon and change note, for the key indicators grid. */
export function RegistryIndicatorTile({
  icon,
  iconBg,
  iconColor,
  value,
  label,
  delta,
}: {
  icon: React.ReactNode
  iconBg: string
  iconColor: string
  value: string
  label: string
  delta?: KpiDelta
}) {
  return (
    <div className="flex min-w-0 items-center gap-2.5 rounded-[10px] px-2.5 py-3" style={{ background: "#F6F8FC" }}>
      <span
        className="grid h-[32px] w-[32px] flex-none place-items-center rounded-[9px]"
        style={{ background: iconBg, color: iconColor }}
      >
        {icon}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-[20px] font-bold leading-tight" style={{ color: REGISTRY_COLORS.ink }}>
          {value}
        </span>
        <span className="block truncate text-[14px] font-semibold leading-snug" style={{ color: REGISTRY_COLORS.muted }} title={label}>
          {label}
        </span>
      </span>
      {delta && <DeltaChip delta={delta} />}
    </div>
  )
}

/** Label / bar / value row, used for shares of the registry such as land tenure or education. */
export function ProgressRow({
  label,
  value,
  percent,
  color = BRIGHT.blueSoft,
  icon,
  iconColor,
  barWidth = "72px",
}: {
  label: string
  value: string
  percent: number
  color?: string
  icon?: React.ReactNode
  /** Ties the icon to the bar colour when rows represent different categories. */
  iconColor?: string
  barWidth?: string
}) {
  const width = Math.max(0, Math.min(100, percent))

  return (
    <div
      className="grid items-center gap-2.5"
      style={{ gridTemplateColumns: `${icon ? "16px " : ""}minmax(0,1fr) ${barWidth} auto` }}
    >
      {icon && (
        <span className="grid h-4 w-4 place-items-center" style={{ color: iconColor || REGISTRY_COLORS.muted }}>
          {icon}
        </span>
      )}
      <span className="truncate text-[17px] font-semibold" style={{ color: REGISTRY_COLORS.ink2 }} title={label}>
        {label}
      </span>
      <span className="h-[9px] overflow-hidden rounded-full" style={{ background: "#F1F4F2" }}>
        <span className="block h-full rounded-full" style={{ width: `${width}%`, background: color }} />
      </span>
      <span className="min-w-[44px] text-right text-[17px] font-bold" style={{ color: REGISTRY_COLORS.ink }}>
        {value}
      </span>
    </div>
  )
}

/** Notification row for the alerts rail: severity icon, headline, detail and context. */
export function AlertRow({
  icon,
  tone,
  title,
  detail,
  context,
}: {
  icon: React.ReactNode
  tone: "danger" | "warning" | "info"
  title: string
  detail: string
  context: string
}) {
  const tones = {
    danger: { bg: BRIGHT_SOFT.red, color: BRIGHT.crimson },
    warning: { bg: BRIGHT_SOFT.amber, color: "#B45309" },
    info: { bg: BRIGHT_SOFT.blue, color: "#1D4ED8" },
  }[tone]

  return (
    <div className="flex min-h-0 items-center gap-2.5 overflow-hidden">
      <span
        className="grid h-7 w-7 flex-none place-items-center rounded-[8px]"
        style={{ background: tones.bg, color: tones.color }}
      >
        {icon}
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-baseline gap-1.5">
          <strong className="truncate text-[16.5px] font-bold" style={{ color: REGISTRY_COLORS.ink }} title={title}>
            {title}
          </strong>
          <span className="ml-auto flex-none text-[14px] font-semibold" style={{ color: REGISTRY_COLORS.muted }}>
            {context}
          </span>
        </span>
        <span
          className="mt-0.5 line-clamp-2 text-[14.5px] font-medium leading-snug"
          style={{ color: REGISTRY_COLORS.muted }}
          title={detail}
        >
          {detail}
        </span>
      </span>
    </div>
  )
}

/**
 * Severity palette for fault reporting. `wash` is the card background, `bg` the
 * icon tile, and `rank` orders the most serious checks to the top of a list.
 */
export const SEVERITY_TONES = {
  danger: { bg: BRIGHT_SOFT.red, wash: "#FEF2F2", color: BRIGHT.crimson, label: "Critical", rank: 0 },
  warning: { bg: BRIGHT_SOFT.amber, wash: "#FFFBEB", color: "#B45309", label: "Warning", rank: 1 },
  info: { bg: BRIGHT_SOFT.blue, wash: "#EFF6FF", color: "#1D4ED8", label: "Coverage", rank: 2 },
} as const

export type Severity = keyof typeof SEVERITY_TONES

/** Fault count as a filled badge, so a non-zero value cannot be skimmed past. */
export function FaultBadge({ count }: { count: number }) {
  if (count <= 0) {
    return (
      <span className="text-[10.5px] font-semibold" style={{ color: BRIGHT.green }}>
        Clear
      </span>
    )
  }

  return (
    <span
      className="inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-bold"
      style={{ background: BRIGHT_SOFT.red, color: BRIGHT.crimson }}
    >
      <CircleAlert className="h-2.5 w-2.5" />
      {formatFull(count)}
    </span>
  )
}

/** Header chip that puts the critical fault count next to a card title. */
export function CriticalCountChip({ count, noun = "critical" }: { count: number; noun?: string }) {
  if (count <= 0) return null

  return (
    <span
      className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold"
      style={{ background: BRIGHT.crimson, color: "#fff" }}
    >
      <CircleAlert className="h-3 w-3" />
      {count} {noun}
    </span>
  )
}

/**
 * A single tripped check, rendered as a tinted card with a severity accent bar
 * so faults read as alerts rather than as another table row.
 */
export function FaultAlert({
  severity,
  title,
  context,
  value,
  label,
}: {
  severity: Severity
  title: string
  context: string
  value: string
  /** Replaces the tone's default caption when the domain names severities itself. */
  label?: string
}) {
  const tone = SEVERITY_TONES[severity] || SEVERITY_TONES.info

  return (
    <div
      className="flex items-center gap-2 rounded-[8px] border-l-[3px] py-1 pl-1.5 pr-2"
      style={{ background: tone.wash, borderColor: tone.color }}
    >
      <span
        className="grid h-5 w-5 flex-none place-items-center rounded-[6px]"
        style={{ background: tone.bg, color: tone.color }}
      >
        {severity === "danger" ? (
          <CircleAlert className="h-3 w-3" />
        ) : severity === "warning" ? (
          <AlertTriangle className="h-3 w-3" />
        ) : (
          <Info className="h-3 w-3" />
        )}
      </span>
      <span className="min-w-0 flex-1">
        <strong
          className="block truncate text-[10.5px] font-semibold leading-tight"
          style={{ color: REGISTRY_COLORS.ink }}
          title={title}
        >
          {title}
        </strong>
        <span className="block truncate text-[9px] leading-tight" style={{ color: tone.color }}>
          {context} · {label ?? tone.label}
        </span>
      </span>
      <span className="flex-none text-[14px] font-bold leading-none" style={{ color: tone.color }}>
        {value}
      </span>
    </div>
  )
}

/** Grouped mini bar chart with a percentage caption per column. */
export function MiniColumnBars({
  items,
  color = BRIGHT.teal,
}: {
  items: Array<{ name: string; percent: number }>
  color?: string
}) {
  const max = items.reduce((acc, item) => Math.max(acc, item.percent), 0) || 100

  return (
    <div className="flex min-h-0 flex-1 items-end gap-1.5">
      {items.map((item) => (
        <div key={item.name} className="flex min-w-0 flex-1 flex-col items-center gap-1">
          <span className="text-[13px] font-semibold" style={{ color: REGISTRY_COLORS.ink2 }}>
            {item.percent.toFixed(0)}%
          </span>
          <span
            className="w-full rounded-t-[3px]"
            style={{ height: `${Math.max(6, (item.percent / max) * 100)}%`, background: color, minHeight: 6 }}
          />
          <span className="w-full truncate text-center text-[13px] font-medium" style={{ color: REGISTRY_COLORS.muted }} title={item.name}>
            {item.name}
          </span>
        </div>
      ))}
    </div>
  )
}

/** Icon + count + share row for the segment insights column. */
export function SegmentRow({
  icon,
  iconBg,
  iconColor,
  label,
  value,
  share,
  delta,
}: {
  icon: React.ReactNode
  iconBg: string
  iconColor: string
  label: string
  value: string
  share?: string
  delta?: KpiDelta
}) {
  return (
    <div className="flex min-h-0 items-center gap-2 overflow-hidden">
      <span
        className="grid h-8 w-8 flex-none place-items-center rounded-[8px]"
        style={{ background: iconBg, color: iconColor }}
      >
        {icon}
      </span>
      <span className="min-w-0 flex-1">
        <span
          className="block truncate text-[13.5px] font-semibold leading-tight"
          style={{ color: REGISTRY_COLORS.muted }}
          title={label}
        >
          {label}
        </span>
        <span className="flex items-baseline gap-1">
          <strong className="text-[18px] font-bold leading-tight" style={{ color: REGISTRY_COLORS.ink }}>
            {value}
          </strong>
          {share && (
            <span className="whitespace-nowrap text-[13px] font-semibold" style={{ color: REGISTRY_COLORS.muted }}>
              {share}
            </span>
          )}
        </span>
      </span>
      {delta && <DeltaChip delta={delta} />}
    </div>
  )
}

/** Boxed figure with a caption, for the small three-up stats inside a panel. */
export function MiniStat({ value, unit, label }: { value: string; unit?: string; label: string }) {
  return (
    <div className="rounded-[10px] px-2 py-2.5 text-center" style={{ background: "#F6F8FC" }}>
      <div className="text-[20px] font-bold leading-tight" style={{ color: REGISTRY_COLORS.ink }}>
        {value}
        {unit && (
          <span className="ml-0.5 text-[14.5px] font-semibold" style={{ color: REGISTRY_COLORS.ink2 }}>
            {unit}
          </span>
        )}
      </div>
      <div className="mt-1 text-[14px] font-semibold leading-snug" style={{ color: REGISTRY_COLORS.muted }}>
        {label}
      </div>
    </div>
  )
}

const STATUS_STYLES: Record<string, { background: string; color: string }> = {
  approved: { background: BRIGHT_SOFT.green, color: BRIGHT.green },
  pending: { background: BRIGHT_SOFT.amber, color: "#B45309" },
  under_review: { background: BRIGHT_SOFT.blue, color: "#1D4ED8" },
  draft: { background: "#F1F5F9", color: "#475569" },
  rejected: { background: BRIGHT_SOFT.red, color: BRIGHT.crimson },
}

export function StatusPill({ status }: { status: string }) {
  const key = String(status || "").toLowerCase()
  const style = STATUS_STYLES[key] || STATUS_STYLES.draft
  const label = key
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ")

  return (
    <span className="whitespace-nowrap rounded-full px-2 py-0.5 text-[13.5px] font-semibold" style={style}>
      {label || "Unknown"}
    </span>
  )
}

/** Full-width proportional bar, used for splits that do not deserve their own chart. */
export function SplitBar({ segments }: { segments: Array<{ name: string; value: number; color: string }> }) {
  const total = segments.reduce((acc, segment) => acc + segment.value, 0)
  if (!total) return null

  return (
    <div>
      <div className="flex h-[9px] overflow-hidden rounded-full" style={{ background: "#F1F4F2" }}>
        {segments.map((segment) => (
          <span
            key={segment.name}
            style={{ width: `${(segment.value / total) * 100}%`, background: segment.color }}
            title={`${segment.name}: ${((segment.value / total) * 100).toFixed(1)}%`}
          />
        ))}
      </div>
      <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1">
        {segments.map((segment) => (
          <span key={segment.name} className="inline-flex items-center gap-1 text-[14px] font-medium" style={{ color: REGISTRY_COLORS.ink2 }}>
            <span className="h-1.5 w-1.5 rounded-full" style={{ background: segment.color }} />
            {segment.name}
            <strong style={{ color: REGISTRY_COLORS.ink }}>{((segment.value / total) * 100).toFixed(1)}%</strong>
          </span>
        ))}
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ bar list

export function BarList({
  items,
  unitLabel,
  formatter = (value: number) => formatFull(Math.round(value)),
  emptyMessage = "No data for the current filters",
  colors = BRIGHT_SERIES as unknown as string[],
  dense = false,
}: {
  items: Array<{ name: string; value: number }>
  unitLabel: string
  formatter?: (value: number) => string
  emptyMessage?: string
  /** Per-row bar colours, cycled by row index. */
  colors?: string[]
  /** Tighter spacing that stretches to the parent's height, for single-screen bands. */
  dense?: boolean
}) {
  const max = items.reduce((acc, item) => Math.max(acc, item.value), 0)
  const axis = niceAxis(max)

  if (!items.length) {
    return <EmptyPanel message={emptyMessage} className={dense ? "px-3 pb-2 pt-1" : "px-4 pb-4 pt-2"} />
  }

  return (
    <div className={dense ? "flex min-h-0 flex-1 flex-col px-3 pb-2 pt-1" : "px-4 pb-4 pt-2.5"}>
      <div
        className={`flex justify-between font-medium ${dense ? "mb-1 flex-none text-[13.5px]" : "mb-1.5 text-[14px]"}`}
        style={{ color: REGISTRY_COLORS.muted }}
      >
        <span />
        <span>{unitLabel}</span>
      </div>

      <div className={dense ? "grid flex-1 auto-rows-fr gap-2" : "grid gap-1.5"}>
        {items.map((item, index) => (
          <div
            key={item.name}
            className={`grid items-center gap-2 ${
              dense ? "grid-cols-[92px_minmax(0,1fr)_auto]" : "grid-cols-[100px_minmax(0,1fr)_auto]"
            }`}
          >
            <span
              className={`font-medium leading-snug ${dense ? "text-[14.5px]" : "text-[15.5px]"}`}
              style={{ color: REGISTRY_COLORS.ink2 }}
            >
              {item.name}
            </span>
            <span
              className={`relative overflow-hidden rounded-[3px] ${dense ? "h-[11px]" : "h-[13px]"}`}
              style={{ background: "#F3F6F4" }}
            >
              <span
                className="block h-full rounded-[3px]"
                style={{
                  width: `${axis.max > 0 ? (item.value / axis.max) * 100 : 0}%`,
                  background: colors[index % colors.length],
                }}
              />
            </span>
            <span
              className={`whitespace-nowrap text-right font-semibold ${
                dense ? "min-w-[46px] text-[14.5px]" : "min-w-[52px] text-[15px]"
              }`}
              style={{ color: REGISTRY_COLORS.ink2 }}
            >
              {formatter(item.value)}
            </span>
          </div>
        ))}
      </div>

      <div
        className={`relative border-t ${
          dense ? "mt-1 ml-[100px] mr-[54px] h-3.5 flex-none" : "mt-2 ml-[108px] mr-[60px] h-4"
        }`}
        style={{ borderColor: REGISTRY_COLORS.line2 }}
      >
        {axis.ticks.map((tick, index) => (
          <span
            key={tick}
            className={`absolute -translate-x-1/2 font-medium ${dense ? "top-0.5 text-[13px]" : "top-1 text-[13.5px]"}`}
            style={{
              left: `${(index / (axis.ticks.length - 1)) * 100}%`,
              color: REGISTRY_COLORS.muted,
            }}
          >
            {formatCompact(tick)}
          </span>
        ))}
      </div>
    </div>
  )
}

/** Rounds an axis maximum up to a readable 1/2/5 x 10^n step with 4 ticks. */
function niceAxis(max: number): { max: number; ticks: number[] } {
  if (max <= 0) return { max: 1, ticks: [0, 1] }
  const rough = max / 3
  const magnitude = Math.pow(10, Math.floor(Math.log10(rough)))
  const normalized = rough / magnitude
  const step = (normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10) * magnitude
  const axisMax = step * 3
  return { max: axisMax, ticks: [0, step, step * 2, step * 3] }
}

// --------------------------------------------------------------------- donut

export type DonutSegment = {
  name: string
  value: number
  color: string
  sub?: string
}

export function RegistryDonut({
  segments,
  centerValue,
  centerLabel,
  totalLabel,
  totalValue,
  emptyMessage = "No data for the current filters",
  compact = false,
  ringSize,
  subInline = false,
  className = "",
}: {
  segments: DonutSegment[]
  centerValue: string
  centerLabel: string
  totalLabel: string
  totalValue: string
  emptyMessage?: string
  /** Stacks the ring above the legend, for narrow single-screen columns. */
  compact?: boolean
  /** Ring diameter in pixels; defaults to 104 when compact and 150 otherwise. */
  ringSize?: number
  /** Renders each segment's sub-label on the same line as its percentage. */
  subInline?: boolean
  className?: string
}) {
  const total = segments.reduce((acc, segment) => acc + segment.value, 0)

  if (!total) {
    return <EmptyPanel message={emptyMessage} className={compact ? "px-3 pb-3 pt-1" : "px-4 pb-5 pt-2"} />
  }

  const radius = 66
  const circumference = 2 * Math.PI * radius
  const ring = ringSize ?? (compact ? 104 : 150)
  let offset = 0

  return (
    <div
      className={`${
        compact
          ? "grid grid-cols-1 justify-items-center gap-1.5 px-3 pb-2.5 pt-1"
          : "grid items-center gap-4 px-4 pb-4 pt-2"
      } ${className}`}
      style={compact ? undefined : { gridTemplateColumns: `${ring}px minmax(0,1fr)` }}
    >
      <svg viewBox="0 0 200 200" style={{ width: ring, height: ring }} className="flex-none">
        <circle cx="100" cy="100" r={radius} fill="none" stroke="#F1F3F2" strokeWidth="26" />
        {segments.map((segment) => {
          const length = (segment.value / total) * circumference
          const dash = `${length} ${circumference - length}`
          const element = (
            <circle
              key={segment.name}
              cx="100"
              cy="100"
              r={radius}
              fill="none"
              stroke={segment.color}
              strokeWidth="26"
              strokeDasharray={dash}
              strokeDashoffset={-offset}
              transform="rotate(-90 100 100)"
            >
              <title>{`${segment.name} — ${((segment.value / total) * 100).toFixed(1)}%`}</title>
            </circle>
          )
          offset += length
          return element
        })}
        <text x="100" y="96" textAnchor="middle" className="text-[23px] font-bold" fill={REGISTRY_COLORS.ink}>
          {centerValue}
        </text>
        <text x="100" y="114" textAnchor="middle" className="text-[14.5px] font-semibold" fill={REGISTRY_COLORS.muted}>
          {centerLabel}
        </text>
      </svg>

      <div className={`grid w-full min-w-0 ${compact ? "gap-[5px]" : "gap-[11px]"}`}>
        {segments.map((segment) => (
          <div
            key={segment.name}
            className={`grid grid-cols-[auto_minmax(0,1fr)_auto] items-baseline gap-x-2 gap-y-0.5 ${compact ? "text-[15px]" : "text-[17px]"}`}
          >
            <span className="h-2.5 w-2.5 flex-none rounded-full" style={{ background: segment.color }} />
            <span className="truncate font-semibold" style={{ color: REGISTRY_COLORS.ink2 }} title={segment.name}>
              {segment.name}
            </span>
            <span className={`whitespace-nowrap text-right font-bold ${compact ? "text-[15px]" : "text-[17px]"}`}>
              {((segment.value / total) * 100).toFixed(1)}%
              {segment.sub && subInline && (
                <span className="ml-1 font-semibold" style={{ color: REGISTRY_COLORS.muted }}>
                  ({segment.sub})
                </span>
              )}
            </span>
            {segment.sub && !compact && !subInline && (
              <span className="col-start-2 col-end-4 -mt-[3px] text-[14.5px] font-medium" style={{ color: REGISTRY_COLORS.muted }}>
                {segment.sub}
              </span>
            )}
          </div>
        ))}
        <div
          className={`flex justify-between border-t font-semibold ${compact ? "mt-0.5 pt-1.5 text-[14.5px]" : "mt-1.5 pt-2 text-[16.5px]"}`}
          style={{ borderColor: REGISTRY_COLORS.line2, color: REGISTRY_COLORS.muted }}
        >
          <span>{totalLabel}</span>
          <strong style={{ color: REGISTRY_COLORS.ink }}>{totalValue}</strong>
        </div>
      </div>
    </div>
  )
}

// ----------------------------------------------------------------- rank list

export function RankList({
  items,
  nameHeader,
  valueHeader,
  formatter = (value: number) => formatFull(Math.round(value)),
  footer,
  emptyMessage = "No data for the current filters",
  dense = false,
  colors = BRIGHT_SERIES as unknown as string[],
}: {
  items: Array<{ name: string; value: number }>
  nameHeader: string
  valueHeader: string
  formatter?: (value: number) => string
  footer?: React.ReactNode
  emptyMessage?: string
  /** Tighter spacing that stretches to the parent's height, for single-screen bands. */
  dense?: boolean
  /** Per-row bar colours, cycled by row index. */
  colors?: string[]
}) {
  const max = items.reduce((acc, item) => Math.max(acc, item.value), 0)

  if (!items.length) {
    return <EmptyPanel message={emptyMessage} className={dense ? "px-3 pb-2 pt-1" : "px-4 pb-4 pt-2"} />
  }

  return (
    <div className={dense ? "flex min-h-0 flex-1 flex-col px-3 pb-2 pt-1" : "px-4 pb-3 pt-2.5"}>
      <div
        className={`flex justify-between border-b font-medium ${
          dense ? "mb-1 flex-none pb-1 text-[13.5px]" : "mb-1 pb-1.5 text-[14px]"
        }`}
        style={{ borderColor: REGISTRY_COLORS.line2, color: REGISTRY_COLORS.muted }}
      >
        <span>{nameHeader}</span>
        <span>{valueHeader}</span>
      </div>

      <div className={dense ? "grid flex-1 auto-rows-fr gap-2" : ""}>
        {items.map((item, index) => (
          <div
            key={item.name}
            className={`grid items-center gap-2 ${
              dense ? "grid-cols-[22px_auto_minmax(0,1fr)_auto]" : "grid-cols-[24px_auto_minmax(0,1fr)_auto] py-[5px]"
            }`}
          >
            <span
              className={`grid place-items-center rounded-[5px] font-bold ${
                dense ? "h-[21px] w-[21px] text-[12px]" : "h-6 w-6 text-[12.5px]"
              }`}
              style={{ background: "#F3F6F4", color: REGISTRY_COLORS.muted }}
            >
              {index + 1}
            </span>
            <span
              className={`truncate font-medium ${dense ? "max-w-[150px] text-[14.5px]" : "max-w-[170px] text-[15.5px]"}`}
              style={{ color: REGISTRY_COLORS.ink2 }}
              title={item.name}
            >
              {item.name}
            </span>
            <span
              className={`overflow-hidden rounded-[3px] ${dense ? "h-[7px]" : "h-2"}`}
              style={{ background: "#F3F6F4" }}
            >
              <span
                className="block h-full rounded-[3px]"
                style={{
                  width: `${max > 0 ? (item.value / max) * 100 : 0}%`,
                  background: colors[index % colors.length],
                }}
              />
            </span>
            <span className={`whitespace-nowrap font-semibold ${dense ? "text-[14.5px]" : "text-[15px]"}`}>
              {formatter(item.value)}
            </span>
          </div>
        ))}
      </div>

      {footer && <div className={dense ? "mt-1 flex-none" : "mt-2"}>{footer}</div>}
    </div>
  )
}

// --------------------------------------------------------------- map legend

export function RampLegend({ title, labels }: { title: string; labels: string[] }) {
  return (
    <div className="px-4 pb-3.5">
      <div className="mb-1.5 text-[14.5px] font-medium" style={{ color: REGISTRY_COLORS.muted }}>
        {title}
      </div>
      <div className="grid h-[9px] grid-cols-5 overflow-hidden rounded-[3px]">
        {REGISTRY_RAMP.map((color) => (
          <span key={color} style={{ background: color }} />
        ))}
      </div>
      <div className="mt-1 grid grid-cols-5 text-[14px] font-medium" style={{ color: REGISTRY_COLORS.muted }}>
        {labels.map((label) => (
          <span key={label} className="text-center">
            {label}
          </span>
        ))}
      </div>
    </div>
  )
}

// -------------------------------------------------------------- misc states

export function EmptyPanel({ message, className = "" }: { message: string; className?: string }) {
  return (
    <div className={`flex min-h-[120px] items-center justify-center ${className}`}>
      <p className="text-[15.5px]" style={{ color: REGISTRY_COLORS.muted }}>
        {message}
      </p>
    </div>
  )
}

export function InlineLegend({ items }: { items: Array<{ name: string; color: string }> }) {
  return (
    <div className="flex justify-end gap-3.5 px-4">
      {items.map((item) => (
        <span key={item.name} className="inline-flex items-center gap-1.5 text-[15px] font-medium" style={{ color: REGISTRY_COLORS.ink2 }}>
          <span className="h-2 w-2 rounded-full" style={{ background: item.color }} />
          {item.name}
        </span>
      ))}
    </div>
  )
}
