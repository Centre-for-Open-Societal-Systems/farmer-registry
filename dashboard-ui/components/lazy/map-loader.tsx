// components/lazy/map-loader.tsx
"use client"

import dynamic from 'next/dynamic'
import { Card, CardContent } from "@/components/ui/card"

// Lazy load the map component - only loads when needed
export const EthiopiaMapLazy = dynamic(
  () => import('../ethiopia-map').then(mod => ({ default: mod.EthiopiaMap })),
  {
    ssr: false, // Don't render on server
    loading: () => (
      <Card className="border border-border/50 shadow-none">
        <CardContent className="p-6">
          <div className="h-[500px] flex items-center justify-center bg-muted/20 rounded-lg">
            <div className="text-center">
              <div className="animate-pulse mb-2">
                <svg className="w-12 h-12 mx-auto text-muted-foreground/40" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
                </svg>
              </div>
              <p className="text-sm text-muted-foreground">Loading map...</p>
            </div>
          </div>
        </CardContent>
      </Card>
    ),
  }
)
