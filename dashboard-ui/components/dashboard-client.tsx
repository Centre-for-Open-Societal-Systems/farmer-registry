"use client"

import { useState, useEffect, useCallback, useMemo } from "react"
import { Button } from "@/components/ui/button"
import { ArrowLeft, Menu, X, Camera } from "lucide-react"
import { GlobalFiltersSidebar, DEFAULT_GEO_LABELS, type GeoLabels } from "@/components/global-filters-sidebar"
import { ExportDataButton } from "@/components/registry/export-button"
import type { RegistryFilters } from "@/components/registry/registry-data"
import { resolveReturnUrl } from "@/lib/return-url"
import dynamic from "next/dynamic"
import { DashboardSectionSkeleton } from "@/components/ui/dashboard-skeleton"

export default function DashboardClient({
  geoJsonData,
  initialFilters,
}: {
  geoJsonData: any;
  initialFilters?: RegistryFilters;
}) {
  const [filters, setFilters] = useState<RegistryFilters>(initialFilters || {
    region: 'all',
    zone: 'all',
    woreda: 'all',
    kebele: 'all',
    farmingType: 'all',
    recordState: 'all',
  })

  const [isSidebarOpen, setIsSidebarOpen] = useState(true)
  const toggleSidebar = () => setIsSidebarOpen(!isSidebarOpen)

  // Where "Back" should land. Resolved on the client because it depends on the
  // returnUrl the staff portal appended when it sent us here.
  const [returnUrl, setReturnUrl] = useState<string | null>(null)
  useEffect(() => {
    setReturnUrl(resolveReturnUrl(window.location.search, document.referrer))
  }, [])

  const goBack = useCallback(() => {
    if (returnUrl) {
      window.location.href = returnUrl
      return
    }
    // Opened directly rather than from the portal, so fall back to history.
    window.history.back()
  }, [returnUrl])

  // Value id -> label, so the active-filter chips can name what is selected. The
  // registry stores geography by the same id the filters carry, so unlike a
  // P-code deployment there is nothing to translate — only to name.
  const [regionsLookup, setRegionsLookup] = useState<Map<string, string>>(new Map())
  const [zonesLookup, setZonesLookup] = useState<Map<string, string>>(new Map())
  const [woredasLookup, setWoredasLookup] = useState<Map<string, string>>(new Map())
  const [geoLabels, setGeoLabels] = useState<GeoLabels>(DEFAULT_GEO_LABELS)

  const setFiltersIfChanged = useCallback((updater: (prev: RegistryFilters) => RegistryFilters) => {
    setFilters(prev => {
      const next = updater(prev)
      // shallow compare to avoid rerenders when nothing actually changed
      const changed = Object.keys(prev).some(key => (prev as any)[key] !== (next as any)[key])
      return changed ? next : prev
    })
  }, [])

  const handleMapFilterChange = useCallback((mapFilters: Partial<RegistryFilters>) => {
    setFiltersIfChanged(prev => ({
      ...prev,
      region: mapFilters.region ?? prev.region ?? 'all',
      zone: mapFilters.zone ?? prev.zone ?? 'all',
      woreda: mapFilters.woreda ?? prev.woreda ?? 'all',
      kebele: mapFilters.kebele ?? prev.kebele ?? 'all',
      farmingType: mapFilters.farmingType ?? prev.farmingType,
      recordState: mapFilters.recordState ?? prev.recordState,
    }))
  }, [setFiltersIfChanged])

  // Load the region lookup and the country pack's level names once, for the
  // header chips.
  useEffect(() => {
    const fetchRegions = async () => {
      try {
        const res = await fetch('/api/filter-options')
        if (!res.ok) return
        const data = await res.json()
        const map = new Map<string, string>()
        ;(data?.regions || []).forEach((r: any) => {
          if (!r?.code) return
          map.set(r.code, r.name || r.code)
        })
        setRegionsLookup(map)
        if (data?.levels) setGeoLabels({ ...DEFAULT_GEO_LABELS, ...data.levels })
      } catch (err) {
        // ignore
      }
    }
    fetchRegions()
  }, [])

  // Each level below region is named on demand, when a filter at that level is set.
  useEffect(() => {
    const loadZones = async () => {
      if (filters.region === 'all' || zonesLookup.size > 0) return
      try {
        const res = await fetch(`/api/locations?regionId=${encodeURIComponent(filters.region)}`)
        if (!res.ok) return
        const data = await res.json()
        const next = new Map<string, string>()
        ;(data?.zones || []).forEach((z: any) => {
          if (!z?.code) return
          next.set(z.code, z.name || z.code)
        })
        setZonesLookup(next)
      } catch (err) {
        // ignore
      }
    }
    loadZones()
  }, [filters.region, zonesLookup])

  useEffect(() => {
    const loadWoredas = async () => {
      if (filters.zone === 'all' || woredasLookup.size > 0) return
      try {
        const res = await fetch(`/api/locations?zoneId=${encodeURIComponent(filters.zone)}`)
        if (!res.ok) return
        const data = await res.json()
        const next = new Map<string, string>()
        ;(data?.woredas || []).forEach((w: any) => {
          if (!w?.code) return
          next.set(w.code, w.name || w.code)
        })
        setWoredasLookup(next)
      } catch (err) {
        // ignore
      }
    }
    loadWoredas()
  }, [filters.zone, woredasLookup])

  const captureElementById = useCallback(async (id: string, prefix: string) => {
    try {
      const target = document.getElementById(id)
      if (!target) return
      const { toPng } = await import("html-to-image")

      // Hide KPI elements if present to capture only charts
      const hidden: Array<{ el: HTMLElement; prev: string }> = []
      target.querySelectorAll<HTMLElement>('[data-kpi="true"], [data-export-control="true"]').forEach(el => {
        hidden.push({ el, prev: el.style.display })
        el.style.display = 'none'
      })

      const dataUrl = await toPng(target, { cacheBust: true })

      // Restore hidden elements
      hidden.forEach(({ el, prev }) => { el.style.display = prev })

      const link = document.createElement("a")
      link.href = dataUrl
      link.download = `${prefix}-${new Date().toISOString().split("T")[0]}.png`
      link.click()
    } catch (err) {
      console.error("Capture failed", err)
    }
  }, [])

  // Display active filters with proper names
  const activeFilterItems = useMemo(() => {
    const filterItems: Array<{ key: string; label: string; value: string }> = [];

    // Location filters - use lookup names, fall back to the stored ids
    if (filters.region !== 'all') {
      filterItems.push({ key: 'region', label: geoLabels.region, value: regionsLookup.get(filters.region) || filters.region });
    }

    if (filters.zone !== 'all') {
      filterItems.push({ key: 'zone', label: geoLabels.zone, value: zonesLookup.get(filters.zone) || filters.zone });
    }

    if (filters.woreda !== 'all') {
      filterItems.push({ key: 'woreda', label: geoLabels.woreda, value: woredasLookup.get(filters.woreda) || filters.woreda });
    }

    if (filters.kebele !== 'all') {
      filterItems.push({ key: 'kebele', label: geoLabels.kebele, value: filters.kebele });
    }
    if (filters.farmingType !== 'all') {
      filterItems.push({ key: 'farmingType', label: 'Farming Type', value: filters.farmingType });
    }
    if (filters.recordState !== 'all') {
      filterItems.push({ key: 'recordState', label: 'Record State', value: filters.recordState });
    }

    return filterItems;
  }, [filters, geoLabels, regionsLookup, zonesLookup, woredasLookup]);

  const clearFilter = useCallback((filterKey: string) => {
    setFiltersIfChanged(prev => {
      const next = { ...prev };

      // Clear the requested filter
      next[filterKey as keyof RegistryFilters] = 'all';

      // Cascade clears for dependent children to keep sidebar/dropdowns/map in sync
      if (filterKey === 'region') {
        next.zone = 'all';
        next.woreda = 'all';
        next.kebele = 'all';
      }
      if (filterKey === 'zone') {
        next.woreda = 'all';
        next.kebele = 'all';
      }
      if (filterKey === 'woreda') {
        next.kebele = 'all';
      }

      return next;
    })
  }, [setFiltersIfChanged]);

  return (
    <div id="dashboard-root" className="animate-page-fade max-h-screen overflow-hidden bg-background text-foreground flex flex-col bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-primary/5 via-background to-background">
      {/* Full Width Header */}
      <div className="w-full relative overflow-hidden bg-[#01215A] text-white py-1 px-4 md:px-6 flex-shrink-0 z-10 shadow-sm">
        {/* Decorative national flag; its hoist edge fades into the ribbon. */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute right-0 top-0 hidden h-full w-[240px] bg-[url('/images/ethiopia-flag-wave.svg')] bg-right bg-no-repeat opacity-95 md:block"
          style={{ backgroundSize: 'auto 100%' }}
        />

        {/* Right padding keeps the controls clear of the flag artwork. */}
        <div className="max-w-full grid grid-cols-[auto_1fr_auto] items-center relative z-10 gap-4 md:pr-[110px]">
          <div className="flex items-center">
            <img
              src="/images/ati_small.jpg"
              alt="Farmer Registry logo"
              className="h-10 w-10 md:h-12 rounded-full md:w-12 object-contain"
            />
          </div>

          <div className="flex min-w-0 flex-col items-center gap-1">
            <div className="text-center">
              <h1 className="text-lg md:text-xl font-bold text-white">Farmer Registry</h1>
              <p className="text-white/60 text[10px] md:text-sm">Agricultural Development & Farmer Analytics</p>
            </div>

            {/* Active Filters Display */}
            {activeFilterItems.length > 0 && (
              <div className="hidden md:flex justify-center px-4 gap-2 flex-wrap">
                {activeFilterItems.map((filter) => (
                  <div
                    key={filter.key}
                    className="bg-white/10 px-3 py-1 rounded-full text-xs font-medium text-white border border-white/20 flex items-center gap-2"
                  >
                    <span>{filter.label}: {filter.value}</span>
                    <button
                      onClick={() => clearFilter(filter.key)}
                      className="hover:bg-white/20 rounded-full p-0.5 transition-colors"
                      aria-label={`Clear ${filter.label} filter`}
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="flex items-center space-x-2 justify-self-end">
            <Button
              variant="outline"
              size="sm"
              onClick={goBack}
              className="border-white/30 bg-[#01215A]/80 text-white backdrop-blur-sm hover:bg-[#01215A] hover:text-white"
            >
              <ArrowLeft className="h-4 w-4 md:mr-2" />
              <span className="hidden md:inline">Back</span>
            </Button>

            <ExportDataButton
              tone="red"
              filters={filters}
              filePrefix="farmer-profiles"
              captureTargetId="dashboard-overview"
            />

            <Button
              variant="outline"
              size="sm"
              className="border-white/30 bg-[#01215A]/80 text-white backdrop-blur-sm hover:bg-[#01215A] hover:text-white"
              onClick={() => captureElementById('dashboard-overview', 'farmer-overview')}
            >
              <Camera className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>

      <div className="flex flex-1 min-h-0 max-h-screen">
        {/* Sidebar */}
        <div className={`${isSidebarOpen ? 'w-80' : 'w-0'} flex-shrink-0 transition-all duration-300 ease-in-out border-r border-[#0A2A66] bg-gradient-to-b from-[#00134B] to-[#001042] relative h-full`}>
          <div className={`${isSidebarOpen ? 'opacity-100' : 'opacity-0'} transition-opacity duration-300 h-full max-h-full overflow-y-auto p-4 space-y-6 scrollbar-thin scrollbar-thumb-white/10 scrollbar-track-transparent`}>
            <GlobalFiltersSidebar
              filters={filters}
              onFiltersChange={setFilters}
              isSidebarOpen={isSidebarOpen}
              onSidebarToggle={toggleSidebar}
            />
          </div>

          {/* Sidebar Toggle Button */}
          <button
            onClick={() => setIsSidebarOpen(!isSidebarOpen)}
            className={`absolute ${isSidebarOpen ? '-right-3' : 'left-2'} top-4 z-50 bg-[#076E7D] text-white rounded-full p-1.5 shadow-lg hover:bg-[#0A8496] transition-all duration-300`}
            aria-label={isSidebarOpen ? "Hide sidebar" : "Show sidebar"}
          >
            {isSidebarOpen ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
          </button>
        </div>

        {/* Main Content */}
        <div
          // Prefer a no-scroll screen on typical laptop heights; fall back to
          // scrolling on shorter viewports so panels are never clipped.
          className="@container flex-1 min-h-0 overflow-y-auto bg-[#F5F8F6] p-3 md:p-4"
        >
          <div id="dashboard-overview" className="h-full min-h-0">
            <FarmerOverviewDashboard
              filters={filters}
              geoJsonData={geoJsonData}
              geoLabels={geoLabels}
              onMapFilterChange={handleMapFilterChange}
            />
          </div>
        </div>
      </div>
    </div>
  )
}

const FarmerOverviewDashboard = dynamic(
  () => import("@/components/farmer-overview-dashboard").then(mod => mod.FarmerOverviewDashboard),
  { ssr: false, loading: () => <TabSkeleton /> }
)

function TabSkeleton() {
  return (
    <DashboardSectionSkeleton />
  )
}
