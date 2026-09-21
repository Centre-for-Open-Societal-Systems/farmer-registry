import { Card, CardContent } from "@/components/ui/card"
import { ChartSkeleton, KPISkeleton, Skeleton } from "@/components/ui/skeleton"

// Lightweight shared skeleton for chart sections; no hooks so it stays cheap in the client bundle.
export function DashboardSectionSkeleton() {
  return (
    <div className="space-y-4">
      
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {[...Array(4)].map((_, idx) => (
          <Card key={idx} className="rounded-xl border border-border/40 bg-card/60 p-4 shadow-sm">
            <KPISkeleton />
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {[...Array(4)].map((_, idx) => (
          <Card key={idx} className="rounded-xl border border-border/40 bg-card/60 p-4 shadow-sm">
            <KPISkeleton />
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        <div className="lg:col-span-2">
          <Card className="h-[360px] rounded-xl border border-border/40 bg-card/60 shadow-sm overflow-hidden">
            <Skeleton className="h-full w-full rounded-none" />
          </Card>
        </div>
        <div className="lg:col-span-3 grid grid-cols-1 md:grid-cols-2 gap-4">
          {[...Array(2)].map((_, idx) => (
            <Card key={idx} className="rounded-xl border border-border/40 bg-card/60 p-8 shadow-sm">
              <ChartSkeleton height="260px" />
            </Card>
          ))}
        </div>
      </div>
    </div>
  )
}
