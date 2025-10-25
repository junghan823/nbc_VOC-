import { fetchReport } from "@/lib/api"
import { Badge } from "@/components/ui/badge"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Separator } from "@/components/ui/separator"

export default async function Home() {
  let error: string | null = null
  let report = null

  try {
    report = await fetchReport()
  } catch (err) {
    error =
      err instanceof Error
        ? err.message
        : "리포트 데이터를 불러오는 중 문제가 발생했습니다."
  }

  if (error || !report) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-background px-4">
        <Card className="max-w-xl">
          <CardHeader>
            <CardTitle>VOC 리포트를 불러올 수 없습니다</CardTitle>
            <CardDescription>{error}</CardDescription>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            FastAPI 서버가 실행 중인지(<code>uvicorn api.main:app --reload</code>)
            와 <code>NEXT_PUBLIC_API_BASE_URL</code> 환경 변수를 확인해 주세요.
          </CardContent>
        </Card>
      </main>
    )
  }

  const { meta, windows, issues, samples, recommendations } = report

  const generatedAt = new Date(meta.generated_at).toLocaleString("ko-KR", {
    timeZone: "Asia/Seoul",
  })

  const statCards = [
    {
      label: "전체 VOC",
      value: meta.total_count.toLocaleString(),
      sub: `${meta.analysis_period.label} 기준 누적`,
    },
    {
      label: "최근 30일",
      value: windows.recent_30d_count.toLocaleString(),
      sub: "최근 30일 신규 VOC",
    },
    {
      label: "전월 30일",
      value: windows.prev_30d_count.toLocaleString(),
      sub: "직전 30일 대비 비교 지표",
    },
    {
      label: "최근 90일",
      value: windows.recent_90d_count.toLocaleString(),
      sub: "장기 추이 파악용",
    },
  ]

  return (
    <main className="min-h-screen bg-background">
      {/* Hero */}
      <div className="border-b bg-gradient-to-b from-background via-background/60 to-muted/40">
        <div className="mx-auto flex max-w-6xl flex-col gap-6 px-6 py-10">
          <header className="space-y-3">
            <div className="flex flex-col gap-2">
              <h1 className="text-3xl font-bold tracking-tight text-foreground lg:text-4xl">
                LMS VOC 대시보드
              </h1>
              <p className="text-sm text-muted-foreground">
                생성일: <strong>{generatedAt}</strong> · 분석 기간:{" "}
                {meta.analysis_period.label}
              </p>
            </div>
            <p className="max-w-2xl text-sm text-muted-foreground">
              공지 문의 VOC 데이터를 AI로 분석해 학습 관리 스쿼드가 긴급 이슈와
              반복 패턴을 빠르게 파악할 수 있도록 구성한 대시보드입니다.
              카드와 표를 참고해 우선 대응이 필요한 항목을 확인하세요.
            </p>
          </header>

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {statCards.map((stat) => (
              <Card key={stat.label}>
                <CardHeader className="space-y-1">
                  <CardDescription className="text-xs uppercase tracking-wide text-muted-foreground">
                    {stat.label}
                  </CardDescription>
                  <CardTitle className="text-2xl font-semibold text-foreground">
                    {stat.value}
                  </CardTitle>
                </CardHeader>
                <CardContent className="text-xs text-muted-foreground">
                  {stat.sub}
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </div>

      <div className="mx-auto flex max-w-6xl flex-col gap-10 px-6 py-10">
        {/* Top Issues */}
        <section className="space-y-4">
          <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <h2 className="text-xl font-semibold">이번 달 핵심 이슈 Top 5</h2>
              <p className="text-sm text-muted-foreground">
                전월 대비 변화율이 큰 이슈 순으로 정렬되었습니다.
              </p>
            </div>
            <Badge variant="outline" className="self-start">
              최근 30일 데이터
            </Badge>
          </div>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {issues.top_recent_30d.map((issue) => (
              <Card key={issue.rank} className="h-full">
                <CardHeader className="space-y-2">
                  <div className="flex items-center justify-between">
                    <Badge variant="outline">#{issue.rank}</Badge>
                    <span
                      className="text-xs font-medium text-foreground"
                      aria-label="변화율"
                    >
                      {issue.change_pct >= 0 ? "▲" : "▼"}{" "}
                      {issue.change_pct.toFixed(1)}%
                    </span>
                  </div>
                  <CardTitle className="text-base leading-tight">
                    {issue.issue_key}
                  </CardTitle>
                  {issue.summary ? (
                    <CardDescription>{issue.summary}</CardDescription>
                  ) : null}
                </CardHeader>
                <CardContent className="space-y-3 text-sm text-muted-foreground">
                  <div className="flex items-center justify-between">
                    <span>이번 달</span>
                    <span className="font-medium text-foreground">
                      {issue.count}건
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span>전월 30일</span>
                    <span>{issue.previous_count}건</span>
                  </div>
                  <Separator />
                  {issue.quotes && issue.quotes.length > 0 ? (
                    <ul className="space-y-2 text-xs">
                      {issue.quotes.map((quote) => (
                        <li
                          key={quote}
                          className="rounded-md bg-muted/70 p-2 leading-relaxed text-foreground"
                        >
                          {quote}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-xs italic text-muted-foreground">
                      발화 예시는 아직 없습니다.
                    </p>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        </section>

        {/* Phase breakdown */}
        <section className="space-y-4">
          <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <h2 className="text-xl font-semibold">학습 단계별 주요 불편</h2>
              <p className="text-sm text-muted-foreground">
                각 단계에서 가장 많이 발생한 이슈와 전월 대비 변화율입니다.
              </p>
            </div>
            <Badge variant="outline">
              총{" "}
              {Object.values(issues.phase_counts).reduce(
                (sum, value) => sum + value,
                0
              )}
              건
            </Badge>
          </div>

          <Card>
            <CardContent className="px-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-48">단계</TableHead>
                    <TableHead>건수 (30일)</TableHead>
                    <TableHead>상위 이슈 / 변화율</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {Object.entries(issues.phase_breakdown).map(
                    ([phase, detail]) => (
                      <TableRow key={phase}>
                        <TableCell className="font-medium text-foreground">
                          {phase}
                        </TableCell>
                        <TableCell>{detail.total}</TableCell>
                        <TableCell>
                          <div className="grid gap-3">
                            {detail.issues.slice(0, 3).map((item) => (
                              <div
                                key={item.issue_key}
                                className="rounded-md border border-dashed border-border/70 p-3"
                              >
                                <div className="flex items-center justify-between">
                                  <p className="text-sm font-medium text-foreground">
                                    {item.issue_key}
                                  </p>
                                  <Badge variant="outline">
                                    {item.change_pct >= 0 ? "+" : ""}
                                    {item.change_pct.toFixed(1)}%
                                  </Badge>
                                </div>
                                <p className="text-xs text-muted-foreground">
                                  {item.count}건 · 전월 {item.previous_count}건
                                </p>
                              </div>
                            ))}
                          </div>
                        </TableCell>
                      </TableRow>
                    )
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </section>

        {/* Trend cards */}
        <section className="space-y-4">
          <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <h2 className="text-xl font-semibold">추세 알림</h2>
              <p className="text-sm text-muted-foreground">
                월간 변동률을 확인해 급증하는 이슈를 빠르게 파악하세요.
              </p>
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {issues.trend_cards.map((trend) => (
              <Card key={trend.category}>
                <CardHeader className="space-y-1.5">
                  <CardTitle className="flex items-center gap-2 text-base">
                    <span>{trend.emoji}</span>
                    <span>{trend.category}</span>
                  </CardTitle>
                  <CardDescription>
                    전월 대비{" "}
                    {trend.change_pct === null
                      ? "신규 발생"
                      : `${trend.change_pct >= 0 ? "+" : ""}${trend.change_pct.toFixed(
                          1
                        )}%`}
                  </CardDescription>
                </CardHeader>
              </Card>
            ))}
          </div>
        </section>

        {/* Representative quotes */}
        <section className="space-y-4">
          <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
            <h2 className="text-xl font-semibold">대표 발화</h2>
            <p className="text-sm text-muted-foreground">
              감정 점수가 높은 VOC의 실제 발화를 확인해 주세요.
            </p>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            {samples.recent_quotes.length === 0 ? (
              <Card>
                <CardContent className="p-6 text-sm text-muted-foreground">
                  최근 30일 대표 발화가 없습니다.
                </CardContent>
              </Card>
            ) : (
              samples.recent_quotes.map((quote, index) => (
                <Card key={`${quote}-${index}`}>
                  <CardContent className="space-y-2 p-6 text-sm">
                    <p className="leading-relaxed text-foreground">
                      “{quote}”
                    </p>
                  </CardContent>
                </Card>
              ))
            )}
          </div>
        </section>

        {/* Recommendations */}
        <section className="space-y-4">
          <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
            <h2 className="text-xl font-semibold">권장 조치</h2>
            <p className="text-sm text-muted-foreground">
              대응 우선순위에 따라 실행할 액션 아이디어입니다.
            </p>
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            {[
              { title: "단기 (1주 내)", items: recommendations.short_term },
              { title: "중기 (1개월)", items: recommendations.mid_term },
              { title: "장기 (모니터링)", items: recommendations.long_term },
            ].map((bucket) => (
              <Card key={bucket.title}>
                <CardHeader className="space-y-1">
                  <CardTitle className="text-base">{bucket.title}</CardTitle>
                  <CardDescription>
                    현황 공유 · 담당자 배정 시 참고하세요.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-2 text-sm text-muted-foreground">
                  {bucket.items.length === 0 ? (
                    <p className="italic text-muted-foreground/70">
                      추후 보강 예정
                    </p>
                  ) : (
                    <ul className="space-y-2">
                      {bucket.items.map((item) => (
                        <li
                          key={item}
                          className="rounded-md bg-muted/70 p-2 text-foreground"
                        >
                          {item}
                        </li>
                      ))}
                    </ul>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        </section>
      </div>
    </main>
  )
}
