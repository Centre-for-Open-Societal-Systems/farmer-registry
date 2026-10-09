import { useEffect, useState } from "react"
import { AlertCircle, CheckCircle2, Loader2, Wifi } from "lucide-react"
import { connectorApiTargetLabel } from "../lib/api-target"

type Status = "checking" | "ok" | "error"

export default function ApiConnectionBar() {
  const target = connectorApiTargetLabel()
  const [status, setStatus] = useState<Status>("checking")
  const [detail, setDetail] = useState("")

  const check = async () => {
    setStatus("checking")
    setDetail("")
    try {
      const res = await fetch("/health", { signal: AbortSignal.timeout(12_000) })
      if (!res.ok) {
        setStatus("error")
        setDetail(`${res.status} ${res.statusText}`)
        return
      }
      const body = (await res.json()) as { status?: string }
      if (body.status === "ok") {
        setStatus("ok")
      } else {
        setStatus("error")
        setDetail(JSON.stringify(body))
      }
    } catch (e) {
      setStatus("error")
      const msg = e instanceof Error ? e.message : String(e)
      setDetail(msg === "Failed to fetch" ? "unreachable" : msg)
    }
  }

  useEffect(() => {
    void check()
    const id = window.setInterval(() => void check(), 30_000)
    return () => window.clearInterval(id)
  }, [])

  return (
    <div
      className={`flex flex-wrap items-center gap-2 px-4 py-2 text-sm border-b ${
        status === "ok"
          ? "bg-emerald-50 border-emerald-200 text-emerald-900"
          : status === "checking"
            ? "bg-amber-50 border-amber-200 text-amber-900"
            : "bg-red-50 border-red-200 text-red-900"
      }`}
    >
      {status === "checking" ? (
        <Loader2 className="w-4 h-4 animate-spin shrink-0" />
      ) : status === "ok" ? (
        <CheckCircle2 className="w-4 h-4 shrink-0" />
      ) : (
        <AlertCircle className="w-4 h-4 shrink-0" />
      )}
      <Wifi className="w-4 h-4 shrink-0 opacity-70" />
      <span className="font-medium">API:</span>
      <code className="text-xs bg-white/60 px-1.5 py-0.5 rounded">{target}</code>
      {status === "ok" && <span className="text-emerald-800">connected</span>}
      {status === "error" && (
        <span>
          not reachable
          {detail ? ` (${detail})` : ""}
          {" — "}
          connect <strong>UD</strong> or <strong>EDRMC</strong> WireGuard, then{" "}
          <code className="text-xs">npm run dev</code>
        </span>
      )}
      <button
        type="button"
        onClick={() => void check()}
        className="ml-auto text-xs underline hover:no-underline"
      >
        Retry
      </button>
    </div>
  )
}
