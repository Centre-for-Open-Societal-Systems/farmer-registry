import { cn } from "@/lib/utils"

function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="skeleton"
      className={cn(
        "bg-muted/60 dark:bg-muted/30 animate-pulse rounded-md",
        className
      )}
      {...props}
    />
  )
}

export function ChartSkeleton({ height = "300px" }: { height?: string }) {
  return (
    <div className="animate-pulse space-y-3" style={{ height }}>
      <div className="h-4 bg-muted/60 dark:bg-muted/30 rounded w-1/3"></div>
      <div className="space-y-2">
        <div className="h-8 bg-muted/60 dark:bg-muted/30 rounded"></div>
        <div className="h-8 bg-muted/60 dark:bg-muted/30 rounded w-5/6"></div>
        <div className="h-8 bg-muted/60 dark:bg-muted/30 rounded w-4/6"></div>
        <div className="h-8 bg-muted/60 dark:bg-muted/30 rounded w-3/6"></div>
      </div>
    </div>
  );
}

export function KPISkeleton() {
  return (
    <div className="animate-pulse px-4 py-3">
      <div className="h-4 bg-muted/60 dark:bg-muted/30 rounded w-24 mb-2"></div>
      <div className="h-6 bg-muted/60 dark:bg-muted/30 rounded w-16 mb-1"></div>
      <div className="h-3 bg-muted/60 dark:bg-muted/30 rounded w-20"></div>
    </div>
  );
}

export { Skeleton }
