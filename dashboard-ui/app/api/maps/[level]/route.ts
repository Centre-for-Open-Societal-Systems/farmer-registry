import { NextResponse } from 'next/server'
import fs from 'fs/promises'
import path from 'path'
import { brotliDecompressSync } from 'zlib'
import { feature } from 'topojson-client'
import type { Topology } from 'topojson-specification'

const LEVEL_FILE: Record<string, string> = {
  regions: 'regions.topojson.br',
  zones: 'zones.topojson.br',
  woredas: 'woredas.topojson.br',
}

export async function GET(
  _req: Request,
  context: { params: Promise<{ level: string }> }
) {
  const { level } = await context.params
  try {
    const fileName = LEVEL_FILE[level]
    if (!fileName) {
      return NextResponse.json({ error: 'Not found' }, { status: 404 })
    }

    const filePath = path.join(process.cwd(), 'public', 'maps', fileName)
    const buf = await fs.readFile(filePath)
    const topo = JSON.parse(brotliDecompressSync(buf).toString('utf8')) as Topology
    const key = topo && topo.objects ? Object.keys(topo.objects)[0] : null
    if (!key) {
      return NextResponse.json({ error: 'Invalid topo' }, { status: 500 })
    }
    // @ts-ignore
    const geojson = feature(topo as any, (topo as any).objects[key])
    return NextResponse.json(geojson)
  } catch (err) {
    console.error('[Maps API] failed to load', level, err)
    return NextResponse.json({ error: 'Failed to load map' }, { status: 500 })
  }
}
