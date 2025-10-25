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
            FastAPI 서버가 실행 중인지(`uvicorn api.main:app --reload`),
            그리고 `NEXT_PUBLIC_API_BASE_URL` 환경변수가 올바른지 확인해 주세요.
          </CardContent>
        </Card>
      </main>
    )
  }

  const {
    meta,
    windows,
    issues,
    samples,
  } = report

  const generatedAt = new Date(meta.generated_at).toLocaleString("ko-KR", {
    timeZone: "Asia/Seoul",
  })

  return (
    <main className="min-h-screen bg-muted/30">
      <div className="mx-auto flex max-w-6xl flex-col gap-8 px-6 py-10">
        <header className="space-y-2">
          <h1 className="text-3xl font-bold tracking-tight text-foreground">
            LMS VOC 대시보드
          </h1>
          <p className="text-sm text-muted-foreground">
            생성일: {generatedAt} · 분석 기간: {meta.analysis_period.label}
          </p>
          <div className="flex flex-wrap gap-2 text-sm text-muted-foreground">
            <span>전체 VOC 건수: {meta.total_count.toLocaleString()}건</span>
            <Separator orientation="vertical" className="h-4" />
            <span>
              최근 30일: {windows.recent_30d_count.toLocaleString()}건
            </span>
            <Separator orientation="vertical" className="h-4" />
            <span>
              전월 30일: {windows.prev_30d_count.toLocaleString()}건
            </span>
            <Separator orientation="vertical" className="h-4" />
            <span>
              최근 90일: {windows.recent_90d_count.toLocaleString()}건
            </span>
          </div>
        </header>

        <section className="grid gap-4 lg:grid-cols-3">
          {issues.top_recent_30d.map((issue) => (
            <Card key={issue.rank}>
              <CardHeader className="space-y-2">
                <div className="flex items-center justify-between">
                  <Badge variant="outline">#{issue.rank}</Badge>
                  <span className="text-xs text-muted-foreground">
                    전월 대비 {issue.change_pct >= 0 ? "+" : ""}
                    {issue.change_pct.toFixed(1)}%
                  </span>
                </div>
                <CardTitle className="text-base">{issue.issue_key}</CardTitle>
                {issue.summary ? (
                  <CardDescription>{issue.summary}</CardDescription>
                ) : null}
              </CardHeader>
              <CardContent className="space-y-2 text-sm text-muted-foreground">
                <p>
                  이번 달 {issue.count}건 · 전월 {issue.previous_count}건
                </p>
                {issue.quotes && issue.quotes.length > 0 ? (
                  <ul className="space-y-1 text-xs">
                    {issue.quotes.map((quote) => (
                      <li key={quote} className="rounded-md bg-muted p-2">
                        {quote}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </CardContent>
            </Card>
          ))}
        </section>

        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-semibold">학습 단계별 주요 불편</h2>
            <p className="text-sm text-muted-foreground">
              총 {Object.values(issues.phase_counts).reduce((acc, cur) => acc + cur, 0)}건
            </p>
          </div>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">단계별 집계</CardTitle>
              <CardDescription>
                최근 30일 기준 각 단계별 VOC 건수와 주요 이슈 Top3입니다.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>단계</TableHead>
                    <TableHead>건수 (30일)</TableHead>
                    <TableHead>상위 이슈</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {Object.entries(issues.phase_breakdown).map(
                    ([phase, detail]) => (
                      <TableRow key={phase}>
                        <TableCell className="font-medium">{phase}</TableCell>
                        <TableCell>{detail.total}</TableCell>
                        <TableCell>
                          <div className="flex flex-col gap-2">
                            {detail.issues.slice(0, 3).map((item) => (
                              <div key={item.issue_key}>
                                <p className="text-sm font-medium">
                                  {item.issue_key}
                                </p>
                                <p className="text-xs text-muted-foreground">
                                  {item.count}건 · 전월 대비{" "}
                                  {item.change_pct >= 0 ? "+" : ""}
                                  {item.change_pct.toFixed(1)}%
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

        <section className="space-y-4">
          <h2 className="text-xl font-semibold">대표 발화</h2>
          <div className="grid gap-3 md:grid-cols-2">
            {samples.recent_quotes.length === 0 ? (
              <Card>
                <CardContent className="p-4 text-sm text-muted-foreground">
                  대표 발화가 없습니다.
                </CardContent>
              </Card>
            ) : (
              samples.recent_quotes.map((quote, index) => (
                <Card key={`${quote}-${index}`}>
                  <CardContent className="space-y-2 p-4 text-sm">
                    <p className="leading-relaxed">“{quote}”</p>
                  </CardContent>
                </Card>
              ))
            )}
          </div>
        </section>
      </div>
    </main>
  )
}
