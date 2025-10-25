export interface ReportMeta {
  generated_at: string
  analysis_period: {
    label: string
    start: string | null
    end: string | null
  }
  total_count: number
}

export interface IssueSummary {
  rank: number
  issue_key: string
  count: number
  previous_count: number
  change_pct: number
  summary?: string
  quotes?: string[]
}

export interface PhaseIssue {
  issue_key: string
  count: number
  previous_count: number
  change_pct: number
  summary?: string
  quotes?: string[]
}

export interface PhaseBreakdownEntry {
  total: number
  issues: PhaseIssue[]
}

export interface TrendCard {
  category: string
  change_pct: number | null
  status: "increase" | "moderate" | "stable"
  emoji: string
}

export interface ReportData {
  meta: ReportMeta
  windows: {
    recent_30d_count: number
    prev_30d_count: number
    recent_90d_count: number
  }
  issues: {
    top_recent_30d: IssueSummary[]
    phase_counts: Record<string, number>
    phase_breakdown: Record<string, PhaseBreakdownEntry>
    trend_cards: TrendCard[]
  }
  samples: {
    recent_quotes: string[]
  }
  recommendations: {
    short_term: string[]
    mid_term: string[]
    long_term: string[]
  }
}
