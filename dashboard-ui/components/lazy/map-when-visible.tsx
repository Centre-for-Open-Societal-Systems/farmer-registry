"use client"

import { useEffect, useRef, useState } from "react"
import { EthiopiaMapLazy } from "./map-loader"
import { Skeleton } from "@/components/ui/skeleton"

type MapWhenVisibleProps = React.ComponentProps<typeof EthiopiaMapLazy> & {
  minHeight?: string
  className?: string
}

// Renders the map only once the container intersects the viewport.
export function MapWhenVisible({ minHeight = "600px", className = "", ...props }: MapWhenVisibleProps) {
  const [visible, setVisible] = useState(false)
  const ref = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!ref.current || visible) return

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some(entry => entry.isIntersecting)) {
          setVisible(true)
          observer.disconnect()
        }
      },
      { rootMargin: "200px 0px" }
    )

    observer.observe(ref.current)
    return () => observer.disconnect()
  }, [visible])

  return (
    <div ref={ref} className={className} style={{ minHeight }}>
      {visible ? (
        <EthiopiaMapLazy {...props} />
      ) : (
        <Skeleton className="h-full w-full rounded-lg" />
      )}
    </div>
  )
}
