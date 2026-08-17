// components/global-filters-sidebar.tsx
"use client"

import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import type { RegistryFilters } from "@/components/registry/registry-data"

/** A geography unit as the API returns it: its stored id and its label. */
interface GeoOption {
  id: string
  code: string
  name: string
}

interface CountedOption {
  code: string
  name: string
  count: number
}

/** What the country pack calls each of the four levels below country. */
export interface GeoLabels {
  region: string
  zone: string
  woreda: string
  kebele: string
}

/**
 * Used until the API reports the pack's own names, and if it never does.
 *
 * The dashboard was designed against Ethiopia, so these are the names it shows
 * by default; a pack that nests country/region/district/ward/village replaces
 * them with its own once /api/filter-options answers.
 */
export const DEFAULT_GEO_LABELS: GeoLabels = {
  region: "Region",
  zone: "Zone",
  woreda: "Woreda",
  kebele: "Kebele",
}

interface GlobalFiltersSidebarProps {
  filters: RegistryFilters
  onFiltersChange: (filters: RegistryFilters) => void
  isSidebarOpen: boolean
  onSidebarToggle: () => void
}

const CLEARED: RegistryFilters = {
  region: "all",
  zone: "all",
  woreda: "all",
  kebele: "all",
  farmingType: "all",
  recordState: "all",
}

export function GlobalFiltersSidebar({ filters, onFiltersChange }: GlobalFiltersSidebarProps) {
  const [labels, setLabels] = useState<GeoLabels>(DEFAULT_GEO_LABELS)
  const [regions, setRegions] = useState<GeoOption[]>([])
  const [zones, setZones] = useState<GeoOption[]>([])
  const [woredas, setWoredas] = useState<GeoOption[]>([])
  const [kebeles, setKebeles] = useState<GeoOption[]>([])
  const [recordStates, setRecordStates] = useState<CountedOption[]>([])
  const [farmingTypes, setFarmingTypes] = useState<CountedOption[]>([])

  const [isLoading, setIsLoading] = useState(true)
  const [isZonesLoading, setIsZonesLoading] = useState(false)
  const [isWoredasLoading, setIsWoredasLoading] = useState(false)
  const [isKebelesLoading, setIsKebelesLoading] = useState(false)

  const fetchJson = async (url: string) => {
    const res = await fetch(url)
    if (!res.ok) throw new Error(`Request failed: ${url}`)
    return res.json()
  }

  // Geography comes from the country pack, record states and farming types from
  // the register's own records. A level that returns nothing leaves its dropdown
  // with only "All" — the registry genuinely has nothing to offer there, and
  // inventing placeholder options would mean offering filters that match no
  // records.
  useEffect(() => {
    const loadFilterOptions = async () => {
      try {
        setIsLoading(true)
        const options = await fetchJson("/api/filter-options")

        setRegions((options?.regions || []).filter((r: GeoOption) => r?.code && r?.name))
        setRecordStates((options?.recordStatuses || []).filter((s: CountedOption) => s?.code))
        setFarmingTypes((options?.farmingTypes || []).filter((t: CountedOption) => t?.code))
        if (options?.levels) setLabels({ ...DEFAULT_GEO_LABELS, ...options.levels })
      } catch (error) {
        console.error("Failed to load filter options:", error)
        setRegions([])
        setRecordStates([])
        setFarmingTypes([])
      } finally {
        setIsLoading(false)
      }
    }

    loadFilterOptions()
  }, [])

  // Each level below region is fetched for the parent that is selected.
  useEffect(() => {
    if (!filters.region || filters.region === "all") {
      setZones([])
      return
    }

    const loadZones = async () => {
      try {
        setIsZonesLoading(true)
        const response = await fetchJson(`/api/locations?regionId=${encodeURIComponent(filters.region)}`)
        setZones((response?.zones || []).filter((z: GeoOption) => z?.code && z?.name))
      } catch (error) {
        console.error("Failed to load zones:", error)
        setZones([])
      } finally {
        setIsZonesLoading(false)
      }
    }

    loadZones()
  }, [filters.region])

  useEffect(() => {
    if (!filters.zone || filters.zone === "all") {
      setWoredas([])
      return
    }

    const loadWoredas = async () => {
      try {
        setIsWoredasLoading(true)
        const response = await fetchJson(`/api/locations?zoneId=${encodeURIComponent(filters.zone)}`)
        setWoredas((response?.woredas || []).filter((w: GeoOption) => w?.code && w?.name))
      } catch (error) {
        console.error("Failed to load woredas:", error)
        setWoredas([])
      } finally {
        setIsWoredasLoading(false)
      }
    }

    loadWoredas()
  }, [filters.zone])

  useEffect(() => {
    if (!filters.woreda || filters.woreda === "all") {
      setKebeles([])
      return
    }

    const loadKebeles = async () => {
      try {
        setIsKebelesLoading(true)
        const response = await fetchJson(`/api/locations?woredaId=${encodeURIComponent(filters.woreda)}`)
        setKebeles((response?.kebeles || []).filter((k: GeoOption) => k?.code && k?.name))
      } catch (error) {
        console.error("Failed to load kebeles:", error)
        setKebeles([])
      } finally {
        setIsKebelesLoading(false)
      }
    }

    loadKebeles()
  }, [filters.woreda])

  const handleFilterChange = (key: keyof RegistryFilters, value: string) => {
    const newFilters = { ...filters, [key]: value }

    // Selecting a new parent invalidates everything below it.
    if (key === "region") {
      newFilters.zone = "all"
      newFilters.woreda = "all"
      newFilters.kebele = "all"
    } else if (key === "zone") {
      newFilters.woreda = "all"
      newFilters.kebele = "all"
    } else if (key === "woreda") {
      newFilters.kebele = "all"
    }

    onFiltersChange(newFilters)
  }

  const clearAllFilters = () => {
    onFiltersChange({ ...CLEARED })
    setZones([])
    setWoredas([])
    setKebeles([])
  }

  const triggerClass =
    "w-full bg-white/10 text-white border-white/20 hover:border-white/40 hover:bg-white/15 transition-colors data-[placeholder]:text-white/50 [&_svg]:text-white/70"

  return (
    <div className="h-screen flex flex-col bg-transparent">
      <div className="flex items-center justify-between p-4 bg-transparent border-b border-white/15">
        <h3 className="text-lg font-bold text-white">Filters</h3>
        <Button
          variant="ghost"
          size="sm"
          onClick={clearAllFilters}
          className="text-xs text-white/60 hover:text-white hover:bg-white/10"
        >
          Clear All
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-6 scrollbar-thin scrollbar-thumb-white/10 scrollbar-track-transparent">
        {/* First level below country */}
        <div className="space-y-2">
          <label className="text-xs font-semibold uppercase tracking-wider text-white/55">{labels.region}</label>
          <Select value={filters.region} onValueChange={(value) => handleFilterChange("region", value)} disabled={isLoading}>
            <SelectTrigger className={triggerClass}>
              <SelectValue placeholder={`Select ${labels.region.toLowerCase()}`} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All {labels.region}s</SelectItem>
              {regions.map((region) => (
                <SelectItem key={region.id} value={region.code}>
                  {region.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Second level */}
        <div className="space-y-2">
          <label className="text-xs font-semibold uppercase tracking-wider text-white/55">{labels.zone}</label>
          <Select
            value={filters.zone}
            onValueChange={(value) => handleFilterChange("zone", value)}
            disabled={isZonesLoading || filters.region === "all"}
          >
            <SelectTrigger className={`${triggerClass} disabled:opacity-50`}>
              <SelectValue placeholder={isZonesLoading ? "Loading..." : `Select ${labels.zone.toLowerCase()}`} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All {labels.zone}s</SelectItem>
              {zones.map((zone) => (
                <SelectItem key={zone.id} value={zone.code}>
                  {zone.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Third level */}
        <div className="space-y-2">
          <label className="text-xs font-semibold uppercase tracking-wider text-white/55">{labels.woreda}</label>
          <Select
            value={filters.woreda}
            onValueChange={(value) => handleFilterChange("woreda", value)}
            disabled={isWoredasLoading || filters.zone === "all"}
          >
            <SelectTrigger className={`${triggerClass} disabled:opacity-50`}>
              <SelectValue placeholder={isWoredasLoading ? "Loading..." : `Select ${labels.woreda.toLowerCase()}`} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All {labels.woreda}s</SelectItem>
              {woredas.map((woreda) => (
                <SelectItem key={woreda.id} value={woreda.code}>
                  {woreda.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Fourth level */}
        <div className="space-y-2">
          <label className="text-xs font-semibold uppercase tracking-wider text-white/55">{labels.kebele}</label>
          <Select
            value={filters.kebele}
            onValueChange={(value) => handleFilterChange("kebele", value)}
            disabled={isKebelesLoading || filters.woreda === "all"}
          >
            <SelectTrigger className={`${triggerClass} disabled:opacity-50`}>
              <SelectValue placeholder={isKebelesLoading ? "Loading..." : `Select ${labels.kebele.toLowerCase()}`} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All {labels.kebele}s</SelectItem>
              {kebeles.map((kebele) => (
                <SelectItem key={kebele.id} value={kebele.code}>
                  {kebele.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Farming Type — a property of the parcel, so this narrows to farmers
            whose largest holding is of this type. */}
        <div className="space-y-2">
          <label className="text-xs font-semibold uppercase tracking-wider text-white/55">Farming Type</label>
          <Select
            value={filters.farmingType}
            onValueChange={(value) => handleFilterChange("farmingType", value)}
            disabled={isLoading}
          >
            <SelectTrigger className={triggerClass}>
              <SelectValue placeholder="Select farming type" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Farming Types</SelectItem>
              {farmingTypes.map((type) => (
                <SelectItem key={type.code} value={type.code}>
                  {type.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Record Status */}
        <div className="space-y-2">
          <label className="text-xs font-semibold uppercase tracking-wider text-white/55">Record Status</label>
          <Select
            value={filters.recordState}
            onValueChange={(value) => handleFilterChange("recordState", value)}
            disabled={isLoading}
          >
            <SelectTrigger className={triggerClass}>
              <SelectValue placeholder="Select status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Statuses</SelectItem>
              {recordStates.map((state) => (
                <SelectItem key={state.code} value={state.code}>
                  {state.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>
    </div>
  )
}
