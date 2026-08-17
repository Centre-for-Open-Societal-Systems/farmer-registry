"use client"

import { useState } from "react"
import { Check, ChevronDown, Download, FileText, Image as ImageIcon, Loader2, Sheet } from "lucide-react"

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { REGISTRY_COLORS } from "@/components/registry/registry-ui"
import { RegistryFilters } from "@/components/registry/registry-data"

type ExportFormat = "image" | "pdf" | "csv"
type ExportState = "idle" | "busy" | "done" | "error"

/**
 * One table in a multi-table CSV. Used by the reference dashboards, which have
 * no farmer records to export and instead dump the panels they display.
 */
export type CsvSection = {
  name: string
  rows: Array<Record<string, unknown>>
}

const BUSY_LABEL: Record<ExportFormat, string> = {
  image: "Rendering image",
  pdf: "Building PDF",
  csv: "Exporting CSV",
}

const PAGE_BACKGROUND = "#F5F8F6"

function triggerDownload(href: string, filename: string) {
  const link = document.createElement("a")
  link.href = href
  link.download = filename
  link.click()
}

function csvCell(value: unknown): string {
  if (value === null || value === undefined) return ""
  const text = String(value)
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

/**
 * Serialises the panels of a dashboard into one CSV, each panel as its own
 * titled block. Column order follows the first row and widens to cover any
 * keys later rows introduce.
 */
function sectionsToCsv(sections: CsvSection[]): string {
  return sections
    .filter(section => section.rows.length > 0)
    .map(section => {
      const columns: string[] = []
      section.rows.forEach(row => {
        Object.keys(row).forEach(key => {
          if (!columns.includes(key)) columns.push(key)
        })
      })

      const header = columns.map(csvCell).join(",")
      const body = section.rows.map(row => columns.map(column => csvCell(row[column])).join(","))
      return [`# ${section.name}`, header, ...body].join("\r\n")
    })
    .join("\r\n\r\n")
}

/**
 * Renders the capture target to a PNG data URL, temporarily hiding the export
 * control itself so the menu/button never appears in the exported artefact.
 */
async function captureTargetPng(targetId: string): Promise<string> {
  const target = document.getElementById(targetId)
  if (!target) throw new Error(`Capture target "${targetId}" not found`)

  const { toPng } = await import("html-to-image")

  const hidden: Array<{ el: HTMLElement; prev: string }> = []
  target.querySelectorAll<HTMLElement>('[data-export-control="true"]').forEach(el => {
    hidden.push({ el, prev: el.style.visibility })
    el.style.visibility = "hidden"
  })

  try {
    return await toPng(target, {
      cacheBust: true,
      pixelRatio: 2,
      backgroundColor: PAGE_BACKGROUND,
    })
  } finally {
    hidden.forEach(({ el, prev }) => {
      el.style.visibility = prev
    })
  }
}

/**
 * Compact multi-format export for a dashboard view. Offers an image (PNG) and
 * PDF snapshot of the current layout plus a CSV of the underlying data. Sized
 * to sit in the source/goal ribbon at the foot of a dashboard.
 *
 * The CSV comes from whichever source the view actually has: registry views
 * pass `filters` and the server returns the matching farmer records, while
 * reference views (catalogues, A2C, DevOps) have no farmer records and pass
 * `csvSections` to export the panels on screen instead.
 */
export function ExportDataButton({
  filters,
  csvSections,
  filePrefix,
  captureTargetId,
  tone = "default",
}: {
  filters?: RegistryFilters
  csvSections?: () => CsvSection[]
  filePrefix: string
  captureTargetId: string
  /** "red" renders a solid red accent button, for placement in the header. */
  tone?: "default" | "red"
}) {
  const [state, setState] = useState<ExportState>("idle")
  const [activeFormat, setActiveFormat] = useState<ExportFormat | null>(null)

  const baseName = () => `${filePrefix}-${new Date().toISOString().split("T")[0]}`

  const exportImage = async () => {
    const dataUrl = await captureTargetPng(captureTargetId)
    triggerDownload(dataUrl, `${baseName()}.png`)
  }

  const exportPdf = async () => {
    const dataUrl = await captureTargetPng(captureTargetId)

    const image = new Image()
    await new Promise<void>((resolve, reject) => {
      image.onload = () => resolve()
      image.onerror = () => reject(new Error("Failed to load captured image for PDF"))
      image.src = dataUrl
    })

    const { jsPDF } = await import("jspdf")
    const orientation = image.width >= image.height ? "landscape" : "portrait"
    const pdf = new jsPDF({ orientation, unit: "px", format: [image.width, image.height] })
    pdf.addImage(dataUrl, "PNG", 0, 0, image.width, image.height)
    pdf.save(`${baseName()}.pdf`)
  }

  const exportCsv = async () => {
    const filename = `${baseName()}.csv`

    if (csvSections) {
      const csv = sectionsToCsv(csvSections())
      if (!csv) throw new Error("Nothing to export yet")
      const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }))
      triggerDownload(url, filename)
      setTimeout(() => URL.revokeObjectURL(url), 1000)
      return
    }

    const response = await fetch("/api/data/export", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filters, format: "csv", filename }),
    })
    if (!response.ok) throw new Error(`Export failed with status ${response.status}`)

    const url = URL.createObjectURL(await response.blob())
    triggerDownload(url, filename)
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }

  const runExport = async (format: ExportFormat) => {
    if (state === "busy") return
    setActiveFormat(format)
    setState("busy")

    try {
      if (format === "image") await exportImage()
      else if (format === "pdf") await exportPdf()
      else await exportCsv()

      setState("done")
      setTimeout(() => {
        setState("idle")
        setActiveFormat(null)
      }, 2000)
    } catch (error) {
      console.error(`Export (${format}) failed`, error)
      setState("error")
      setTimeout(() => {
        setState("idle")
        setActiveFormat(null)
      }, 2500)
    }
  }

  const isError = state === "error"
  const label =
    state === "busy" && activeFormat
      ? BUSY_LABEL[activeFormat]
      : state === "done"
        ? "Downloaded"
        : isError
          ? "Retry export"
          : "Export"

  const TriggerIcon = state === "busy" ? Loader2 : state === "done" ? Check : Download

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        data-export-control="true"
        disabled={state === "busy"}
        aria-label="Export this dashboard"
        title="Export this dashboard as image, PDF or CSV"
        className={
          tone === "red"
            ? "inline-flex flex-none items-center gap-1.5 rounded-md border px-3 py-1.5 text-[12px] font-semibold text-white outline-none transition-colors hover:bg-[#B91C1C] disabled:cursor-progress"
            : "inline-flex flex-none items-center gap-1 rounded-md border bg-white px-2 py-[3px] text-[10px] font-semibold outline-none transition-colors hover:bg-[#F2F8F4] disabled:cursor-progress"
        }
        style={
          tone === "red"
            ? { borderColor: "#DC2626", background: "#DC2626", color: "#FFFFFF" }
            : {
                borderColor: isError ? REGISTRY_COLORS.red : REGISTRY_COLORS.line,
                color: isError ? REGISTRY_COLORS.red : REGISTRY_COLORS.g700,
              }
        }
      >
        <TriggerIcon className={`h-3 w-3 ${state === "busy" ? "animate-spin" : ""}`} />
        {label}
        <ChevronDown className="h-3 w-3 opacity-70" />
      </DropdownMenuTrigger>

      <DropdownMenuContent align="end" sideOffset={6} className="min-w-[168px]">
        <DropdownMenuLabel className="text-[11px] text-muted-foreground">Export as</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem className="gap-2 text-[13px]" onSelect={() => runExport("image")}>
          <ImageIcon className="h-4 w-4" />
          Image (PNG)
        </DropdownMenuItem>
        <DropdownMenuItem className="gap-2 text-[13px]" onSelect={() => runExport("pdf")}>
          <FileText className="h-4 w-4" />
          PDF document
        </DropdownMenuItem>
        <DropdownMenuItem className="gap-2 text-[13px]" onSelect={() => runExport("csv")}>
          <Sheet className="h-4 w-4" />
          CSV data
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
