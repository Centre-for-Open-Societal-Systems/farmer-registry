// Administrative boundaries, GeoJSON (as Master Data serves a country pack's
// boundaries/<level>.geojson) or TopoJSON, for finding which unit a point
// falls in. Only what that needs: lon/lat rings, one bounding box per unit,
// and an even-odd point-in-polygon test.

type Ring = [number, number][];

export type BoundaryUnit = {
    properties: Record<string, unknown>;
    polygons: Ring[][];
    bbox: [number, number, number, number];
};

type Topology = {
    type: 'Topology';
    transform?: { scale: [number, number]; translate: [number, number] };
    arcs: [number, number][][];
    objects: Record<string, { geometries: { type: string; arcs?: unknown; properties?: Record<string, unknown> }[] }>;
};

function decodeArcs(topology: Topology): Ring[] {
    const transform = topology.transform;
    return topology.arcs.map((arc) => {
        let x = 0;
        let y = 0;
        return arc.map(([dx, dy]) => {
            if (!transform) return [dx, dy] as [number, number];
            x += dx;
            y += dy;
            return [x * transform.scale[0] + transform.translate[0], y * transform.scale[1] + transform.translate[1]] as [number, number];
        });
    });
}

function ring(arcs: Ring[], indexes: number[]): Ring {
    const points: Ring = [];
    for (const index of indexes) {
        const arc = index < 0 ? [...arcs[~index]!].reverse() : arcs[index]!;
        // Consecutive arcs share their joining point.
        points.push(...(points.length ? arc.slice(1) : arc));
    }
    return points;
}

type FeatureCollection = {
    type: 'FeatureCollection';
    features: { properties?: Record<string, unknown>; geometry?: { type: string; coordinates: unknown } | null }[];
};

function unit(properties: Record<string, unknown> | undefined, polygons: Ring[][]): BoundaryUnit | null {
    if (!polygons.length) return null;
    const bbox: [number, number, number, number] = [Infinity, Infinity, -Infinity, -Infinity];
    for (const [lon, lat] of polygons.flat(2)) {
        bbox[0] = Math.min(bbox[0], lon);
        bbox[1] = Math.min(bbox[1], lat);
        bbox[2] = Math.max(bbox[2], lon);
        bbox[3] = Math.max(bbox[3], lat);
    }
    return { properties: properties ?? {}, polygons, bbox };
}

/** Every unit of the topology's first object (or the named one). */
export function boundaryUnits(topology: Topology, object?: string): BoundaryUnit[] {
    const arcs = decodeArcs(topology);
    const collection = topology.objects[object ?? Object.keys(topology.objects)[0] ?? ''];
    const units: BoundaryUnit[] = [];
    for (const geometry of collection?.geometries ?? []) {
        const polygons: number[][][] =
            geometry.type === 'Polygon' ? [geometry.arcs as number[][]]
            : geometry.type === 'MultiPolygon' ? (geometry.arcs as number[][][])
            : [];
        const found = unit(geometry.properties, polygons.map((polygon) => polygon.map((indexes) => ring(arcs, indexes))));
        if (found) units.push(found);
    }
    return units;
}

/** Every polygon feature of a GeoJSON FeatureCollection. */
export function featureUnits(collection: FeatureCollection): BoundaryUnit[] {
    const units: BoundaryUnit[] = [];
    for (const feature of collection.features ?? []) {
        const geometry = feature.geometry;
        const polygons =
            geometry?.type === 'Polygon' ? [geometry.coordinates as Ring[]]
            : geometry?.type === 'MultiPolygon' ? (geometry.coordinates as Ring[][])
            : [];
        const found = unit(feature.properties, polygons);
        if (found) units.push(found);
    }
    return units;
}

function inside(lon: number, lat: number, polygon: Ring[]): boolean {
    // Even-odd over the outer ring and its holes.
    let hit = false;
    for (const points of polygon) {
        for (let i = 0, j = points.length - 1; i < points.length; j = i++) {
            const [xi, yi] = points[i]!;
            const [xj, yj] = points[j]!;
            if (yi > lat !== yj > lat && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) hit = !hit;
        }
    }
    return hit;
}

/** The unit containing the point, if any. */
export function unitAt(units: BoundaryUnit[], lat: number, lon: number): BoundaryUnit | null {
    for (const unit of units) {
        const [west, south, east, north] = unit.bbox;
        if (lon < west || lon > east || lat < south || lat > north) continue;
        if (unit.polygons.some((polygon) => inside(lon, lat, polygon))) return unit;
    }
    return null;
}

const cache = new Map<string, Promise<BoundaryUnit[]>>();

/** The units in the GeoJSON or TopoJSON at `url`, fetched once per page. */
export function loadBoundaries(url: string): Promise<BoundaryUnit[]> {
    let units = cache.get(url);
    if (!units) {
        units = fetch(url, { credentials: 'include' })
            .then((response) => {
                if (!response.ok) throw new Error(`${response.status} ${url}`);
                return response.json() as Promise<Topology | FeatureCollection>;
            })
            .then((data) => (data.type === 'Topology' ? boundaryUnits(data) : featureUnits(data)));
        units.catch(() => cache.delete(url));
        cache.set(url, units);
    }
    return units;
}
