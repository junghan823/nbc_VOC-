import { ReportData } from "@/types/report"

const DEFAULT_API_BASE = "http://localhost:8000"

function getApiBaseUrl() {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? DEFAULT_API_BASE
}

export async function fetchReport(): Promise<ReportData> {
  const baseUrl = getApiBaseUrl()
  const url = new URL("/report", baseUrl)

  const res = await fetch(url.toString(), {
    cache: "no-store",
    next: { revalidate: 0 },
  })

  if (!res.ok) {
    throw new Error(
      `Failed to load report: ${res.status} ${res.statusText}`
    )
  }

  const data = (await res.json()) as ReportData
  return data
}
