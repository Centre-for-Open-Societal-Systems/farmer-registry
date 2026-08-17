"use client"

import React, { useState, useEffect, useMemo, useCallback, useRef } from "react"
import { Button } from "@/components/ui/button"
import { ChevronLeft, Home, MapPin, X, List, Download, Camera, Eye, Maximize2 } from "lucide-react"
import { toPng } from "html-to-image"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { feature } from "topojson-client"
import type { Topology } from "topojson-specification"

interface MapLevel {
  type: 'regions' | 'zones' | 'woredas' | 'kebeles';
  selectedRegionPcod?: string;
  selectedZonePcod?: string;
  selectedWoredaPcod?: string;
}

interface EthiopiaMapProps {
  onFilterChange: (filters: {
    region?: string;
    zone?: string;
    woreda?: string;
    kebele?: string;
    farmerType?: string;
    recordState?: string;
    farmingType?: string;
  }) => void;
  currentFilters: {
    region?: string;
    zone?: string;
    woreda?: string;
    kebele?: string;
    farmerType?: string;
    recordState?: string;
    farmingType?: string;
    /** A2C only: the selected credit provider, passed through to drill-down queries. */
    provider?: string;
  };
  farmerData?: Array<{
    region: string;
    farmers: number;
  }>;
  geoJsonData?: {
    regions: Topology | null;
    zones: Topology | null;
    woredas: Topology | null;
  };
  /** "registry" swaps the HSL shading for the flat five-step ramp used by the registry dashboards. */
  variant?: 'default' | 'registry';
  /** Noun for the measured value, e.g. "farmers" or "hectares". */
  valueLabel?: string;
  valueFormatter?: (value: number) => string;
  /** Overrides the chart keys used to load drill-down counts, so the metric stays consistent. */
  childChartKeys?: {
    zones: string;
    woredas: string;
    kebeles: string;
  };
  height?: string;
  /** Registry variant only: stretch to the parent's height instead of holding a 4:3 box. */
  fill?: boolean;
  /** Floats the ramp key over the map instead of stacking it below. */
  legendPosition?: 'below' | 'overlay';
  /** Heading for the pop-out modal; defaults to a label built from the metric. */
  popOutTitle?: string;
  /** Off for the copy rendered inside the pop-out, so it cannot open another one. */
  allowPopOut?: boolean;
}

interface GeoJSONFeature {
  type: string;
  properties: {
    admin1Name?: string;
    admin1Pcod?: string;
    admin2Name?: string;
    admin2Pcod?: string;
    admin3Name?: string;
    admin3Pcod?: string;
  };
  geometry: any;
}

interface GeoJSONData {
  type: string;
  features: GeoJSONFeature[];
}

// Calculate the label anchor point for a feature: the area-weighted centroid
// (shoelace formula) of its largest ring, rather than a plain vertex average.
// A vertex average drifts toward wherever a shape's outline has the most
// points and can land outside thin/concave regions or in the gap between a
// multi-polygon's disconnected parts; the area centroid of the largest part
// sits reliably inside the region's main body instead.
// Even-odd ray-casting point-in-polygon test, used to keep a label's jittered
// position from drifting outside the region it's labelling.
const pointInPolygon = (point: { x: number; y: number }, ring: [number, number][]): boolean => {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    const intersects =
      yi > point.y !== yj > point.y &&
      point.x < ((xj - xi) * (point.y - yi)) / (yj - yi) + xi;
    if (intersects) inside = !inside;
  }
  return inside;
};

const calculateCentroid = (
  coordinates: any[],
  viewBox: { minX: number; minY: number; width: number; height: number }
): { x: number; y: number; ring: [number, number][]; area: number } | null => {
  try {
    const project = (coord: [number, number]): [number, number] => {
      const [lng, lat] = coord;
      const x = ((lng - viewBox.minX) / viewBox.width) * 800;
      const y = ((viewBox.minY + viewBox.height - lat) / viewBox.height) * 600;
      return [x, y];
    };

    const ringCentroid = (
      ring: [number, number][]
    ): { x: number; y: number; area: number; pts: [number, number][] } | null => {
      if (!ring || ring.length < 3) return null;
      const pts = ring
        .filter((c) => c && c.length === 2 && typeof c[0] === 'number' && typeof c[1] === 'number')
        .map(project);
      if (pts.length < 3) return null;

      let signedArea = 0;
      let cx = 0;
      let cy = 0;
      for (let i = 0; i < pts.length; i++) {
        const [x0, y0] = pts[i];
        const [x1, y1] = pts[(i + 1) % pts.length];
        const cross = x0 * y1 - x1 * y0;
        signedArea += cross;
        cx += (x0 + x1) * cross;
        cy += (y0 + y1) * cross;
      }
      signedArea *= 0.5;

      if (Math.abs(signedArea) < 1e-6) {
        const avg = pts.reduce((acc, [x, y]) => ({ x: acc.x + x, y: acc.y + y }), { x: 0, y: 0 });
        return { x: avg.x / pts.length, y: avg.y / pts.length, area: 0, pts };
      }

      return { x: cx / (6 * signedArea), y: cy / (6 * signedArea), area: Math.abs(signedArea), pts };
    };

    if (!coordinates || !Array.isArray(coordinates)) return null;

    const outerRings: [number, number][][] = [];

    // Handle MultiPolygon
    if (Array.isArray(coordinates[0]) && Array.isArray(coordinates[0][0]) && Array.isArray(coordinates[0][0][0])) {
      coordinates.forEach((polygon: any) => {
        if (Array.isArray(polygon) && polygon.length > 0 && Array.isArray(polygon[0])) {
          outerRings.push(polygon[0]);
        }
      });
    }
    // Handle Polygon
    else if (Array.isArray(coordinates[0]) && Array.isArray(coordinates[0][0])) {
      outerRings.push(coordinates[0]);
    }

    let best: { x: number; y: number; area: number; pts: [number, number][] } | null = null;
    outerRings.forEach((ring) => {
      const result = ringCentroid(ring);
      if (result && (!best || result.area > best.area)) {
        best = result;
      }
    });

    if (!best) return null;
    const resolved = best as { x: number; y: number; area: number; pts: [number, number][] };
    return { x: resolved.x, y: resolved.y, ring: resolved.pts, area: resolved.area };
  } catch (error) {
    console.warn('Error calculating centroid:', error);
    return null;
  }
};

const geoJsonToSvgPath = (
  coordinates: any[],
  viewBox: { minX: number; minY: number; width: number; height: number }
) => {
  const paths: string[] = [];

  const convertCoord = (coord: [number, number]) => {
    const [lng, lat] = coord;
    const x = ((lng - viewBox.minX) / viewBox.width) * 800;
    const y = ((viewBox.minY + viewBox.height - lat) / viewBox.height) * 600;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  };

  const processRing = (ring: [number, number][]) => {
    if (!ring || ring.length === 0) return '';
    try {
      const pathCommands = ring
        .map((coord, index) => {
          if (
            !coord ||
            coord.length !== 2 ||
            typeof coord[0] !== 'number' ||
            typeof coord[1] !== 'number'
          )
            return '';
          const point = convertCoord(coord);
          return index === 0 ? `M ${point}` : `L ${point}`;
        })
        .filter((cmd) => cmd !== '');
      if (pathCommands.length === 0) return '';
      return pathCommands.join(' ') + ' Z';
    } catch (error) {
      console.warn('Error processing ring:', error);
      return '';
    }
  };

  try {
    if (!coordinates || !Array.isArray(coordinates)) {
      console.warn('Invalid coordinates:', coordinates);
      return '';
    }
    if (
      Array.isArray(coordinates[0]) &&
      Array.isArray(coordinates[0][0]) &&
      Array.isArray(coordinates[0][0][0])
    ) {
      coordinates.forEach((polygon: any) => {
        if (Array.isArray(polygon) && polygon.length > 0) {
          const outerRing = polygon[0];
          if (Array.isArray(outerRing)) {
            const pathData = processRing(outerRing);
            if (pathData) {
              paths.push(pathData);
            }
          }
        }
      });
    } else if (
      Array.isArray(coordinates[0]) &&
      Array.isArray(coordinates[0][0])
    ) {
      const outerRing = coordinates[0];
      if (Array.isArray(outerRing)) {
        const pathData = processRing(outerRing);
        if (pathData) {
          paths.push(pathData);
        }
      }
    }
  } catch (error) {
    console.warn('Error processing coordinates:', error);
  }

  return paths.join(' ');
};

const getViewBox = (features: GeoJSONFeature[]) => {
  if (!features || features.length === 0) {
    return {
      minX: 32.5,
      minY: 3.0,
      width: 15.5,
      height: 12.0,
    };
  }

  let minLng = Infinity;
  let maxLng = -Infinity;
  let minLat = Infinity;
  let maxLat = -Infinity;

  features.forEach(feature => {
    const processCoordinates = (coords: any) => {
      if (!coords) return;
      
      if (Array.isArray(coords[0]) && Array.isArray(coords[0][0])) {
        // MultiPolygon or Polygon
        coords.forEach((ring: any) => {
          if (Array.isArray(ring[0]) && typeof ring[0][0] === 'number') {
            // This is a ring of coordinates
            ring.forEach((coord: [number, number]) => {
              if (coord && coord.length === 2) {
                const [lng, lat] = coord;
                minLng = Math.min(minLng, lng);
                maxLng = Math.max(maxLng, lng);
                minLat = Math.min(minLat, lat);
                maxLat = Math.max(maxLat, lat);
              }
            });
          } else {
            // Nested deeper
            processCoordinates(ring);
          }
        });
      }
    };

    if (feature.geometry && feature.geometry.coordinates) {
      processCoordinates(feature.geometry.coordinates);
    }
  });

  // Add padding (10% of dimensions)
  const lngPadding = (maxLng - minLng) * 0.1;
  const latPadding = (maxLat - minLat) * 0.1;

  return {
    minX: minLng - lngPadding,
    minY: minLat - latPadding,
    width: (maxLng - minLng) + (lngPadding * 2),
    height: (maxLat - minLat) + (latPadding * 2),
  };
};

/** Flat choropleth ramp shared with the registry legend. */
const REGISTRY_RAMP = ['#F0FDF4', '#BBF7D0', '#4ADE80', '#16A34A', '#15803D'];

export function EthiopiaMap(props: EthiopiaMapProps) {
  const {
    onFilterChange,
    currentFilters,
    farmerData = [],
    geoJsonData,
    variant = 'default',
    valueLabel = 'farmers',
    valueFormatter,
    childChartKeys,
    height = '600px',
    fill = false,
    legendPosition = 'overlay',
    popOutTitle,
    allowPopOut = true,
  } = props;
  const isRegistry = variant === 'registry';
  const formatValue = useCallback(
    (value: number) => (valueFormatter ? valueFormatter(value) : value.toLocaleString()),
    [valueFormatter]
  );
  // Cache expensive geometry/path calculations across renders to keep the map snappy
  // Cache only geometry-derived data (paths/centroids); counts are re-read to reflect latest data
  const pathCacheRef = useRef<Map<string, { pathData: string; centroid: { x: number; y: number; ring: [number, number][]; area: number } | null }>>(new Map())
  const [mounted, setMounted] = useState(false);
  const [regionsData, setRegionsData] = useState<GeoJSONData | null>(null);
  const [zonesData, setZonesData] = useState<GeoJSONData | null>(null);
  const [woredasData, setWoredasData] = useState<GeoJSONData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hoveredFeatureData, setHoveredFeatureData] = useState<{
    id: string;
    name: string;
    count: number;
    centroid: { x: number; y: number };
  } | null>(null);

  const [mapLevel, setMapLevel] = useState<MapLevel>({ type: 'regions' });
  const [childData, setChildData] = useState<any[]>([]);
  const [isAnimating, setIsAnimating] = useState(false);
  const [showStaticLabels, setShowStaticLabels] = useState(true);
  const mapContainerRef = useRef<HTMLDivElement | null>(null)

  // Build a code -> count map with variants to match topo codes
  const codeToCount = useMemo(() => {
    const normalize = (value: any) => (value ? String(value).toUpperCase().replace(/[^A-Z0-9]/g, '') : '');
    const map = new Map<string, number>();
    const source = mapLevel.type === 'regions' ? farmerData : childData;
    source?.forEach((item: any) => {
      const raw = item.code || item.region_code || item.zone_code || item.woreda_code || item.kebele_code;
      const code = normalize(raw);
      const farmers = parseInt(item.farmers || 0, 10);
      if (!code) return;
      const variants = new Set<string>();
      variants.add(code);
      variants.add(code.replace(/^ET/, ''));
      variants.add(code.replace(/^ET0*/, ''));
      variants.add(code.replace(/^0+/, ''));
      if (code.length > 6) variants.add(code.slice(-6));
      if (code.length > 5) variants.add(code.slice(-5));
      variants.forEach(v => {
        const existing = map.get(v);
        map.set(v, existing !== undefined ? Math.max(existing, farmers) : farmers);
      });
    });
    return map;
  }, [childData, farmerData, mapLevel.type]);

  // Helper function to get farmer count for a specific region/zone/woreda
  const getFarmerCount = useCallback((feature: GeoJSONFeature | null | undefined): number => {
    if (!feature) return 0;
    const normalize = (value: any) => (value ? String(value).toUpperCase().replace(/[^A-Z0-9]/g, '') : '');

    const featureCode = normalize(
      feature.properties.admin3Pcod ||
      feature.properties.admin2Pcod ||
      feature.properties.admin1Pcod
    );
    if (!featureCode) return 0;

    const variants = [
      featureCode,
      featureCode.replace(/^ET/, ''),
      featureCode.replace(/^ET0*/, ''),
      featureCode.replace(/^0+/, ''),
      featureCode.length > 6 ? featureCode.slice(-6) : '',
      featureCode.length > 5 ? featureCode.slice(-5) : '',
    ].filter(Boolean);

    for (const key of variants) {
      const val = codeToCount.get(key);
      if (typeof val === 'number') return val;
    }
    return 0;
  }, [codeToCount]);

  const captureMap = async () => {
    try {
      const target = mapContainerRef.current
      if (!target) return
      const dataUrl = await toPng(target, { cacheBust: true })
      const link = document.createElement("a")
      link.href = dataUrl
      link.download = `map-${new Date().toISOString().split("T")[0]}.png`
      link.click()
    } catch (err) {
      console.error("Map capture failed", err)
    }
  }

  // Convert Topology to GeoJSON FeatureCollection
  const topoToGeo = (topology: Topology | null): GeoJSONData | null => {
    // Already a FeatureCollection
    if ((topology as any)?.features) {
      return topology as any as GeoJSONData
    }

    if (!topology || !(topology as any).objects) return null
    const key = Object.keys((topology as any).objects)[0]
    if (!key) return null
    // @ts-ignore topojson types
    return feature(topology as any, (topology as any).objects[key]) as GeoJSONData
  }

  // Load map data on mount (TopoJSON only)
  useEffect(() => {
    const t0 = performance.now();
    setMounted(true);
    
    // Use SSR data if available
    if (geoJsonData && geoJsonData.regions) {
      setRegionsData(topoToGeo(geoJsonData.regions));
      setZonesData(topoToGeo(geoJsonData.zones));
      setWoredasData(topoToGeo(geoJsonData.woredas));
      setLoading(false);
      if (process.env.NODE_ENV === 'development') {
        console.log('[Map] SSR geoJSON applied in', Math.round(performance.now() - t0), 'ms');
      }
      return;
    }

    // Otherwise fetch client-side TopoJSON
    const loadData = async () => {
      try {
        setLoading(true);
        const fetchGeoJson = async (level: 'regions' | 'zones' | 'woredas') => {
          const res = await fetch(`/api/maps/${level}`);
          if (!res.ok) throw new Error('Failed');
          return res.json();
        };

        const [regions, zones, woredas] = await Promise.all([
          fetchGeoJson('regions'),
          fetchGeoJson('zones'),
          fetchGeoJson('woredas'),
        ]);

        setRegionsData(topoToGeo(regions));
        setZonesData(topoToGeo(zones));
        setWoredasData(topoToGeo(woredas));
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load map data');
      } finally {
        setLoading(false);
        if (process.env.NODE_ENV === 'development') {
          console.log('[Map] Client geoJSON load duration', Math.round(performance.now() - t0), 'ms');
        }
      }
    };

    loadData();
  }, [geoJsonData]);

  // Fetch child data for list view when drilling down
  useEffect(() => {
    const t0 = performance.now();
    const fetchChildData = async () => {
      try {
        const chartKey =
          mapLevel.type === 'zones'
            ? (childChartKeys?.zones ?? 'farmersByZone')
            : mapLevel.type === 'woredas'
              ? (childChartKeys?.woredas ?? 'farmersByWoreda')
              : mapLevel.type === 'kebeles'
                ? (childChartKeys?.kebeles ?? 'farmersByKebele')
                : null;

        if (!chartKey) {
          setChildData([]);
          return;
        }

        // Build filter parameters based on current selection
        const params = new URLSearchParams({ charts: chartKey });
        
        // Add parent filters to get only relevant children
        if (currentFilters.region && currentFilters.region !== 'all') {
          params.append('region', currentFilters.region);
        }
        if (currentFilters.zone && currentFilters.zone !== 'all') {
          params.append('zone', currentFilters.zone);
        }
        if (currentFilters.woreda && currentFilters.woreda !== 'all') {
          params.append('woreda', currentFilters.woreda);
        }
        if (currentFilters.farmingType && currentFilters.farmingType !== 'all') {
          params.append('farmingType', currentFilters.farmingType);
        }
        if (currentFilters.farmerType && currentFilters.farmerType !== 'all') {
          params.append('farmerType', currentFilters.farmerType);
        }
        // A2C only: keeps the drill-down series on the same lender as the panels.
        if (currentFilters.provider && currentFilters.provider !== 'all') {
          params.append('provider', currentFilters.provider);
        }

        const response = await fetch(`/api/charts?${params.toString()}`);
        const result = await response.json();

        const rows = result?.data?.[chartKey]?.data || result?.data?.data || [];
        const mapped = (rows || []).map((item: any) => ({
          name: item.region || item.zone || item.woreda || item.kebele,
          code: item.region_code || item.zone_code || item.woreda_code || item.kebele_code,
          farmers: parseInt(item.farmers || 0, 10),
        })).filter((item: any) => !(String(item.name || '').toLowerCase() === 'unknown' && item.farmers === 0));

        setChildData(mapped);
        if (process.env.NODE_ENV === 'development') {
          console.log('[Map] Loaded child data', {
            chartKey,
            count: mapped.length,
            duration: Math.round(performance.now() - t0),
          });
        }
      } catch (error) {
        setChildData([]);
        if (process.env.NODE_ENV === 'development') {
          console.warn('[Map] Failed to load child data', error);
        }
      }
    };

    fetchChildData();
  }, [mapLevel, currentFilters, childChartKeys]);

  // Update map level based on filters; if code isn't present in map data, keep current view
  useEffect(() => {
    const regionCode = currentFilters.region && currentFilters.region !== 'all' ? currentFilters.region : undefined;
    const zoneCode = currentFilters.zone && currentFilters.zone !== 'all' ? currentFilters.zone : undefined;
    const woredaCode = currentFilters.woreda && currentFilters.woreda !== 'all' ? currentFilters.woreda : undefined;

    const regionExists = regionCode && regionsData?.features?.some(
      (f) => f.properties.admin1Pcod === regionCode
    );
    const zoneExists = zoneCode && zonesData?.features?.some(
      (f) => f.properties.admin2Pcod === zoneCode
    );
    const woredaExists = woredaCode && woredasData?.features?.some(
      (f) => f.properties.admin3Pcod === woredaCode
    );

    if (woredaCode && woredaExists) {
      setMapLevel({
        type: 'woredas',
        selectedRegionPcod: regionCode,
        selectedZonePcod: zoneCode,
        selectedWoredaPcod: woredaCode,
      });
    } else if (zoneCode && zoneExists) {
      setMapLevel({
        type: 'woredas',
        selectedRegionPcod: regionCode,
        selectedZonePcod: zoneCode,
      });
    } else if (regionCode && regionExists) {
      setMapLevel({
        type: 'zones',
        selectedRegionPcod: regionCode,
      });
    } else if (!regionCode && !zoneCode && !woredaCode) {
      setMapLevel({ type: 'regions' });
    }
    // If invalid codes are provided, do nothing and keep the current map level.
  }, [currentFilters, regionsData, zonesData, woredasData]);

  const handleFeatureClick = (feature: GeoJSONFeature) => {
    setIsAnimating(true);
    setTimeout(() => setIsAnimating(false), 500);

    if (feature.properties.admin1Pcod && !feature.properties.admin2Pcod) {
      // Clicked a region - drill down to zones
      onFilterChange({
        region: feature.properties.admin1Pcod,
        zone: 'all',
        woreda: 'all',
        kebele: 'all',
        farmerType: currentFilters.farmerType,
        recordState: currentFilters.recordState,
        farmingType: currentFilters.farmingType,
      });
    } else if (feature.properties.admin2Pcod && !feature.properties.admin3Pcod) {
      // Clicked a zone - drill down to woredas
      onFilterChange({
        region: currentFilters.region,
        zone: feature.properties.admin2Pcod,
        woreda: 'all',
        kebele: 'all',
        farmerType: currentFilters.farmerType,
        recordState: currentFilters.recordState,
        farmingType: currentFilters.farmingType,
      });
    } else if (feature.properties.admin3Pcod) {
      // Clicked a woreda - drill down to kebeles
      onFilterChange({
        region: currentFilters.region,
        zone: currentFilters.zone,
        woreda: feature.properties.admin3Pcod,
        kebele: 'all',
        farmerType: currentFilters.farmerType,
        recordState: currentFilters.recordState,
        farmingType: currentFilters.farmingType,
      });
    }
  };

  const currentFeatures = useMemo(() => {
    if (mapLevel.type === 'woredas' && woredasData) {
      if (currentFilters.woreda) {
        return woredasData.features.filter(
          (feature) => feature.properties.admin3Pcod === currentFilters.woreda
        );
      }
      return woredasData.features.filter(
        (feature) => feature.properties.admin2Pcod === currentFilters.zone
      );
    }
    if (mapLevel.type === 'zones' && zonesData) {
      return zonesData.features.filter(
        (feature) => feature.properties.admin1Pcod === currentFilters.region
      );
    }
      return regionsData ? regionsData.features : [];
  }, [mapLevel, regionsData, zonesData, woredasData, currentFilters]);

  const viewBox = useMemo(() => {
    if (!currentFeatures || currentFeatures.length === 0) return { minX: 0, minY: 0, width: 100, height: 100 };
    return getViewBox(currentFeatures);
  }, [currentFeatures]);

  // Precompute expensive geometry transforms so hover tooltips don't rerun them
  const featureShapes = useMemo(() => {
    const cache = pathCacheRef.current;
    const viewKey = `${viewBox.minX.toFixed(2)}-${viewBox.minY.toFixed(2)}-${viewBox.width.toFixed(2)}-${viewBox.height.toFixed(2)}`;

    return currentFeatures.map((feature, index) => {
      const featureId = `${feature.properties.admin1Pcod}-${feature.properties.admin2Pcod}-${feature.properties.admin3Pcod}-${index}`;
      const cacheKey = `${featureId}-${viewKey}`;

      let cached = cache.get(cacheKey);
      if (!cached) {
        const pathData = geoJsonToSvgPath(feature.geometry.coordinates, viewBox);
        if (!pathData) return null;
        const centroid = calculateCentroid(feature.geometry.coordinates, viewBox);
        cached = { pathData, centroid };
        cache.set(cacheKey, cached);
      }

      const farmerCount = getFarmerCount(feature);
      const featureName =
        mapLevel.type === 'zones'
          ? feature.properties.admin2Name
          : mapLevel.type === 'woredas'
            ? feature.properties.admin3Name
            : feature.properties.admin1Name || feature.properties.admin2Name || feature.properties.admin3Name;

      return {
        feature,
        featureId,
        featureName: featureName || 'Unknown',
        pathData: cached.pathData,
        centroid: cached.centroid,
        farmerCount,
      };
    }).filter(Boolean) as Array<{
      feature: GeoJSONFeature;
      featureId: string;
      featureName: string;
      pathData: string;
      centroid: { x: number; y: number; ring: [number, number][]; area: number } | null;
      farmerCount: number;
    }>;
  }, [currentFeatures, getFarmerCount, mapLevel.type, viewBox]);

  // When static labels are enabled, jitter overlapping labels vertically
  const staticLabels = useMemo(() => {
    if (!showStaticLabels) return [];
    const labelWidth = 92;
    const labelHeight = 26;
    const minGap = 8;
    const bounds = { w: 800, h: 600 };

    // Regions with a footprint too small to plausibly hold a label without
    // spilling into their neighbours are skipped in the always-on view; they
    // remain fully available via hover, so no data is hidden, just decluttered.
    const areas = featureShapes.map(f => f.centroid?.area ?? 0).filter(a => a > 0);
    const maxArea = areas.length ? Math.max(...areas) : 0;
    const minLabelArea = Math.max(labelWidth * labelHeight * 0.55, maxArea * 0.05);

    const positions = [
      { dx: 0, dy: -labelHeight / 1.2 }, // above
      { dx: 0, dy: labelHeight / 1.2 },  // below
      { dx: -labelWidth / 1.5, dy: -labelHeight / 2 }, // up-left
      { dx: labelWidth / 1.5, dy: -labelHeight / 2 },  // up-right
      { dx: -labelWidth / 1.5, dy: labelHeight / 2 },  // down-left
      { dx: labelWidth / 1.5, dy: labelHeight / 2 },   // down-right
    ];

    const candidates = featureShapes
      .filter(f => f.farmerCount > 0 && f.centroid && f.centroid.area >= minLabelArea)
      .map(f => ({
        id: f.featureId,
        name: f.featureName,
        count: f.farmerCount,
        x: f.centroid!.x,
        y: f.centroid!.y,
        ring: f.centroid!.ring,
      }))
      // sort by count desc so larger counts place first
      .sort((a, b) => b.count - a.count);

    const placed: Array<{ id: string; name: string; count: number; x: number; y: number }> = [];
    const overlaps = (a: { x: number; y: number }, b: { x: number; y: number }) => {
      return (
        Math.abs(a.x - b.x) < (labelWidth + minGap) / 2 &&
        Math.abs(a.y - b.y) < (labelHeight + minGap) / 2
      );
    };

    candidates.forEach(label => {
      const spots = positions.map(({ dx, dy }) => ({
        x: Math.max(labelWidth / 2, Math.min(bounds.w - labelWidth / 2, label.x + dx)),
        y: Math.max(labelHeight / 2, Math.min(bounds.h - labelHeight / 2, label.y + dy)),
      }));

      // Best case: inside the region's own outline and clear of other labels.
      // If that's not available, avoiding an unreadable overlap matters more
      // than staying strictly inside a tiny region, so a clear-but-slightly-
      // outside spot wins over an inside-but-overlapping one.
      const isClear = (spot: { x: number; y: number }) => !placed.some((p) => overlaps(spot, p));
      const insideAndClear = spots.find((spot) => pointInPolygon(spot, label.ring) && isClear(spot));
      const clearOnly = insideAndClear ?? spots.find(isClear);
      const insideOnly = clearOnly ?? spots.find((spot) => pointInPolygon(spot, label.ring));
      const chosen = insideOnly ?? { x: label.x, y: label.y };

      placed.push({ id: label.id, name: label.name, count: label.count, x: chosen.x, y: chosen.y });
    });

    return placed;
  }, [featureShapes, showStaticLabels]);

  const maxFarmerCount = useMemo(() => {
    if (!featureShapes.length) return 0;
    return Math.max(...featureShapes.map(f => f.farmerCount));
  }, [featureShapes]);

  const totalFeatureCount = useMemo(() => {
    return featureShapes.reduce((sum, f) => sum + f.farmerCount, 0);
  }, [featureShapes]);

  const formatPercentOfTotal = useCallback((count: number) => {
    return totalFeatureCount > 0 ? `${((count / totalFeatureCount) * 100).toFixed(1)}%` : '0.0%';
  }, [totalFeatureCount]);

  // Breakpoints split the non-zero range into four quartile-ish bands so sparse
  // woredas stay visible instead of washing out against the top value.
  const rampBreaks = useMemo(() => {
    if (maxFarmerCount <= 0) return null;
    return [
      Math.max(1, Math.round(maxFarmerCount * 0.08)),
      Math.max(2, Math.round(maxFarmerCount * 0.25)),
      Math.max(3, Math.round(maxFarmerCount * 0.55)),
    ];
  }, [maxFarmerCount]);

  const rampLabels = useMemo(() => buildRampLabels(rampBreaks, formatValue), [rampBreaks, formatValue]);

  const getFeatureColor = (count: number, maxCount: number) => {
    if (isRegistry) {
      if (count <= 0 || !rampBreaks) return REGISTRY_RAMP[0];
      if (count <= rampBreaks[0]) return REGISTRY_RAMP[1];
      if (count <= rampBreaks[1]) return REGISTRY_RAMP[2];
      if (count <= rampBreaks[2]) return REGISTRY_RAMP[3];
      return REGISTRY_RAMP[4];
    }

    if (count <= 0 || maxCount <= 0) return '#e2e8f0'; // slate-200 for 0

    const ratio = Math.max(0, Math.min(1, count / maxCount));
    const lightness = 75 - ratio * 45; // 75% -> 30%
    return `hsl(120, 100%, ${lightness}%)`;
  };

  // Sampling the fill scale at each band's upper bound keeps the key's swatches
  // truthful for both the registry ramp and the continuous default scale.
  const legendColors = [0, ...(rampBreaks ?? [0, 0, 0]), maxFarmerCount].map(count =>
    getFeatureColor(count, maxFarmerCount)
  );

  const isFeatureSelected = useCallback((feature: GeoJSONFeature) => {
    return (
      (mapLevel.type === 'regions' &&
        feature.properties.admin1Pcod === currentFilters.region) ||
      (mapLevel.type === 'zones' &&
        feature.properties.admin2Pcod === currentFilters.zone) ||
      (mapLevel.type === 'woredas' &&
        feature.properties.admin3Pcod === currentFilters.woreda)
    );
  }, [currentFilters.region, currentFilters.woreda, currentFilters.zone, mapLevel.type]);

  const getFeatureStyle = (feature: GeoJSONFeature, count: number) => {
    const isSelected = isFeatureSelected(feature);
    const fillColor = getFeatureColor(count, maxFarmerCount);

    return {
      fill: fillColor,
      stroke: isRegistry && !isSelected ? '#FFFFFF' : 'white',
      strokeWidth: isSelected ? 2 : isRegistry ? 0.35 : 0.5,
      className: 'transition-all duration-200 cursor-pointer hover:brightness-90',
    };
  };

  const handleBack = () => {
    if (mapLevel.type === 'woredas') {
      onFilterChange({
        region: currentFilters.region ?? 'all',
        zone: 'all',
        woreda: 'all',
      });
    } else if (mapLevel.type === 'zones') {
      onFilterChange({
        region: 'all',
        zone: 'all',
        woreda: 'all',
      });
    }
  };

  const handleHome = () => {
    onFilterChange({
      region: 'all',
      zone: 'all',
      woreda: 'all',
    });
  };

  const toolButtonClass = isRegistry
    ? 'flex items-center justify-center w-[29px] h-[29px] rounded-lg border-[#E6EAE8] bg-white text-[#000000] shadow-sm hover:bg-[#F7FAF8]'
    : 'flex items-center justify-center w-8 h-8 bg-background/80 backdrop-blur-sm'

  // Expand is the primary map action, so it gets a filled brand-teal treatment
  // instead of blending into the neutral outline buttons beside it.
  const expandButtonClass = isRegistry
    ? 'flex items-center justify-center w-[29px] h-[29px] rounded-lg border-transparent bg-[#076E7D] text-white shadow-sm hover:bg-[#0A8496]'
    : 'flex items-center justify-center w-8 h-8 rounded-md border-transparent bg-[#076E7D] text-white shadow-sm backdrop-blur-sm hover:bg-[#0A8496]'

  // Callers that own a card title pass it through; the rest fall back to the
  // metric and the level currently on screen.
  const popOutHeading =
    popOutTitle ||
    `${valueLabel.charAt(0).toUpperCase()}${valueLabel.slice(1)} by ${mapLevel.type.replace(/s$/, '')}`

  if (!mounted || loading) {
    return (
      <div
        className={`w-full flex items-center justify-center ${fill ? 'h-full' : ''}`}
        style={fill ? undefined : { height }}
      >
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto mb-4"></div>
          <p className="text-muted-foreground">Loading map data...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div
        className={`w-full flex items-center justify-center ${fill ? 'h-full' : ''}`}
        style={fill ? undefined : { height }}
      >
        <div className="text-center text-destructive">
          <MapPin className="h-8 w-8 mx-auto mb-4" />
          <p>Error loading map: {error}</p>
        </div>
      </div>
    )
  }

  return (
    <div
      className={isRegistry ? (fill ? 'flex h-full min-h-0 flex-col' : '') : 'bg-card rounded-lg'}
      ref={mapContainerRef}
    >
      <div
        className={
          isRegistry
            ? fill
              ? 'relative w-full min-h-0 flex-1 overflow-hidden'
              // Track the 4:3 viewBox so the country fills the card instead of
              // sitting in a wide letterbox when the column is stretched.
              : 'relative w-full overflow-hidden aspect-[4/3] min-h-[360px] max-h-[660px]'
            : 'relative w-full rounded-lg overflow-hidden border border-border/50'
        }
        style={isRegistry ? undefined : { height }}
      >
        <div className={isRegistry ? 'absolute top-3 right-3 z-10 flex items-center gap-2.5' : 'absolute top-0 right-0 z-10 flex items-center gap-3 p-2'}>
          {/* Pop-out. The modal renders a second copy of the map driven by the
              same filters and change handler, so drilling in either stays in
              step; allowPopOut stops that copy offering the control again. */}
          {allowPopOut && (
            <Dialog>
              <DialogTrigger asChild>
                <Button
                  variant="outline"
                  size="icon"
                  className={expandButtonClass}
                  title="Open map in a larger view"
                >
                  <Maximize2 className="h-4 w-4" />
                </Button>
              </DialogTrigger>
              <DialogContent className="flex h-[92vh] w-[96vw] max-w-[96vw] flex-col gap-3 p-4 sm:max-w-[96vw]">
                <DialogHeader className="flex-none pr-8">
                  <DialogTitle>{popOutHeading}</DialogTitle>
                </DialogHeader>
                <div className="relative min-h-0 flex-1 overflow-hidden rounded-lg">
                  <div className="absolute inset-0 flex flex-col">
                    <EthiopiaMap {...props} allowPopOut={false} fill height="80vh" />
                  </div>
                </div>
              </DialogContent>
            </Dialog>
          )}
          <div className={isRegistry ? 'flex gap-1.5' : 'flex gap-2'}>
          {/* List View Button */}
          <Dialog>
            <DialogTrigger asChild>
              <Button
                variant="outline"
                size="icon"
                className={toolButtonClass}
                title="View List"
              >
                <List className="h-4 w-4" />
              </Button>
            </DialogTrigger>
            <DialogContent className="max-h-[80vh] flex flex-col">
              <DialogHeader>
                <div className="flex items-center justify-between">
                  <DialogTitle>
                    {/* Show next drill-down level based on current filter state */}
                    {!currentFilters.region || currentFilters.region === 'all' ? 'Regions' :
                     !currentFilters.zone || currentFilters.zone === 'all' ? 'Zones' :
                     !currentFilters.woreda || currentFilters.woreda === 'all' ? 'Woredas' : 'Kebeles'}
                  </DialogTitle>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      const listItems = mapLevel.type === 'regions' ? currentFeatures : childData;
                      const csv = [
                        ['Name', valueLabel.charAt(0).toUpperCase() + valueLabel.slice(1)],
                        ...listItems.map((item: any) => {
                          const isFeature = item.properties !== undefined;
                          const name = isFeature
                            ? item.properties.admin1Name || item.properties.admin2Name || item.properties.admin3Name
                            : item.name || item.zone || item.woreda || item.kebele || '';
                          const count = isFeature ? getFarmerCount(item) : (item.farmers || 0);
                          return [name, count];
                        })
                      ].map(row => row.join(',')).join('\n');
                      const blob = new Blob([csv], { type: 'text/csv' });
                      const url = URL.createObjectURL(blob);
                      const a = document.createElement('a');
                      a.href = url;
                      a.download = `map-data-${Date.now()}.csv`;
                      a.click();
                      URL.revokeObjectURL(url);
                    }}
                  >
                    <Download className="h-4 w-4 mr-2" />
                    Export CSV
                  </Button>
                </div>
              </DialogHeader>
              <div className="overflow-y-auto flex-1 p-2 space-y-1">
                {(mapLevel.type === 'regions' ? currentFeatures : childData)
                  .sort((a: any, b: any) => {
                    const countA = a.farmers || getFarmerCount(a);
                    const countB = b.farmers || getFarmerCount(b);
                    return countB - countA;
                  })
                  .map((item: any, index: number) => {
                  const isFeature = item.properties !== undefined;
                  const name = isFeature 
                    ? (mapLevel.type === 'regions'
                        ? item.properties.admin1Name
                        : mapLevel.type === 'zones'
                          ? item.properties.admin2Name
                          : item.properties.admin3Name)
                    : (item.name || item.zone || item.woreda || item.kebele);
                  const count = isFeature ? getFarmerCount(item) : (item.farmers || 0);

                  return (
                    <div
                      key={index}
                      className="flex items-center justify-between p-2 rounded text-[17px] hover:bg-muted cursor-default"
                    >
                      <span className="truncate mr-2" title={name}>{name}</span>
                      <span className="font-mono text-[15px] bg-muted px-1.5 py-0.5 rounded">
                        {formatCompactNumber(count)}
                      </span>
                    </div>
                  );
                })}
              </div>
            </DialogContent>
          </Dialog>

          {mapLevel.type !== 'regions' && (
            <Button
              variant="outline"
              size="icon"
              onClick={handleBack}
              className={toolButtonClass}
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
          )}
          <Button
            variant="outline"
            size="icon"
            onClick={handleHome}
            className={toolButtonClass}
          >
            <X className="h-4 w-4" />
          </Button>
          <Button
            variant="outline"
            size="icon"
            onClick={captureMap}
            className={toolButtonClass}
            title="Save Map Snapshot"
          >
            <Camera className="h-4 w-4" />
          </Button>
          <Button
            variant={showStaticLabels ? "default" : "outline"}
            size="icon"
            onClick={() => setShowStaticLabels(!showStaticLabels)}
            className={toolButtonClass}
            title="Toggle labels for areas with farmers"
          >
            <Eye className="h-4 w-4" />
          </Button>
          </div>
        </div>
        
        {legendPosition === 'overlay' && (
          <div
            className="absolute right-3 top-12 z-10 max-w-[48%] rounded-lg border border-[#E6EAE8] bg-white/95 px-2 py-1.5 shadow-sm backdrop-blur-sm"
          >
            <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-[#000000]">
              {valueLabel} per {mapLevel.type.replace(/s$/, '')}
            </div>
            <div className="grid gap-[3px]">
              {legendColors.map((color, index) => (
                <span key={`${color}-${index}`} className="flex items-center gap-1.5 text-[10.5px] font-medium text-[#000000]">
                  <span
                    className="h-2 w-2 flex-none rounded-[2px] border border-black/5"
                    style={{ background: color }}
                  />
                  {rampLabels[index]}
                </span>
              ))}
            </div>
          </div>
        )}

        {featureShapes && featureShapes.length > 0 ? (
          <div className={`h-full transition-opacity duration-500 ${isAnimating ? 'opacity-0' : 'opacity-100'}`}>
          <svg
            width="100%"
            height="100%"
            viewBox="0 0 800 600"
            preserveAspectRatio="xMidYMid meet"
            className="cursor-pointer"
          >
            {featureShapes.map(({ feature, featureId, featureName, pathData, centroid, farmerCount }) => {
              return (
                <g key={featureId}>
                  <path
                    d={pathData}
                    {...getFeatureStyle(feature, farmerCount)}
                    onClick={() => handleFeatureClick(feature)}
                    onMouseEnter={() => {
                      if (centroid) {
                        setHoveredFeatureData({
                          id: featureId,
                          name: featureName || 'Unknown',
                          count: farmerCount,
                          centroid
                        });
                      }
                    }}
                    onMouseLeave={() => setHoveredFeatureData(null)}
                  />
                </g>
              );
            })}

            {/* Static labels for screenshot mode. No backing plate: the text
                carries a white halo (stroke painted under the fill) so it stays
                readable over any shade of the choropleth. */}
            {showStaticLabels && staticLabels.map(label => (
              <g key={`label-${label.id}`} className="pointer-events-none">
                <text
                  x={label.x}
                  y={label.y - 8}
                  textAnchor="middle"
                  stroke="rgba(0,0,0,0.65)"
                  strokeWidth={3}
                  strokeLinejoin="round"
                  paintOrder="stroke"
                  className="fill-white text-[11px] font-bold"
                >
                  {label.name}
                </text>
                <text
                  x={label.x}
                  y={label.y + 8}
                  textAnchor="middle"
                  stroke="rgba(0,0,0,0.65)"
                  strokeWidth={3}
                  strokeLinejoin="round"
                  paintOrder="stroke"
                  className="fill-white text-[10.5px] font-bold"
                >
                  {formatValue(label.count)} ({formatPercentOfTotal(label.count)})
                </text>
              </g>
            ))}

            {/* Tooltip rendered last to be on top. Skipped when a static label is
                already showing for this feature, so the two don't overlap. */}
            {hoveredFeatureData && !(showStaticLabels && hoveredFeatureData.count > 0) && (
              <g className="pointer-events-none" style={{ zIndex: 9999 }}>
                {(() => {
                  return (
                    <>
                      <text
                        x={hoveredFeatureData.centroid.x}
                        y={hoveredFeatureData.centroid.y - 9}
                        textAnchor="middle"
                        stroke="rgba(0,0,0,0.65)"
                        strokeWidth={3.5}
                        strokeLinejoin="round"
                        paintOrder="stroke"
                        className="fill-white text-[13px] font-bold"
                      >
                        {hoveredFeatureData.name}
                      </text>
                      <text
                        x={hoveredFeatureData.centroid.x}
                        y={hoveredFeatureData.centroid.y + 9}
                        textAnchor="middle"
                        stroke="rgba(0,0,0,0.65)"
                        strokeWidth={3.5}
                        strokeLinejoin="round"
                        paintOrder="stroke"
                        className="fill-white text-[12px] font-bold"
                      >
                        {formatValue(hoveredFeatureData.count)} ({formatPercentOfTotal(hoveredFeatureData.count)})
                      </text>
                    </>
                  );
                })()}
              </g>
            )}
          </svg>
          </div>
        ) : (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <MapPin className="h-12 w-12 mx-auto mb-4 text-muted-foreground" />
              <p className="text-muted-foreground">No map data available</p>
            </div>
          </div>
        )}
      </div>

      {legendPosition === 'below' && (
        <div className={fill ? 'flex-none px-3 pb-2 pt-1' : 'px-4 pb-3.5 pt-1'}>
          <div className="mb-1.5 text-[11px] font-medium text-[#000000]">
            {valueLabel.charAt(0).toUpperCase() + valueLabel.slice(1)} per {mapLevel.type.replace(/s$/, '')}
          </div>
          <div className="grid h-[9px] grid-cols-5 overflow-hidden rounded-[3px]">
            {legendColors.map((color, index) => (
              <span key={`${color}-${index}`} style={{ background: color }} />
            ))}
          </div>
          <div className="mt-1 grid grid-cols-5 text-[10.5px] font-medium text-[#000000]">
            {rampLabels.map((label, index) => (
              <span key={`${label}-${index}`} className="text-center">{label}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

/** Turns the three internal ramp breakpoints into the five legend range captions. */
function buildRampLabels(
  breaks: number[] | null,
  format: (value: number) => string
): string[] {
  if (!breaks) return ['0', '—', '—', '—', '—'];
  const [b0, b1, b2] = breaks;
  return [
    '0',
    `1 – ${format(b0)}`,
    `${format(b0 + 1)} – ${format(b1)}`,
    `${format(b1 + 1)} – ${format(b2)}`,
    `${format(b2 + 1)}+`,
  ];
}

// Helper for compact number formatting in the list
function formatCompactNumber(number: number) {
  return Intl.NumberFormat('en-US', {
    notation: "compact",
    maximumFractionDigits: 1
  }).format(number);
}
