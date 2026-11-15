export type Company = { ticker: string; name: string; sector: string; exchange: string; research_demo: boolean }
export type Contact = { id: number; name: string; expertise: string[]; synthetic: boolean; ticker?: string; role?: string; reason?: string; provenance: string; degree?: number | null; score?: number; reasons?: string[]; suggested_question?: string; connection_path?: { from: string; to: string; relationship: string }[]; education?: { institution: string; qualification: string; start_year: number; end_year: number }[]; roles?: { company: string; role: string; start_year: number; end_year: number | null }[] }
export type Citation = { source_url?: string; url: string; page?: number | null; quote?: string | null }
export type Insight = { id: number; ticker: string; company: string; title: string; category: string; published_at: string | null; published_date: string; publication_precision: string; summary: string; summary_method: string; why_it_may_matter: string; priority_reason: string; citation: Citation; network: Contact[]; materiality: string; mode: string }
export type Digest = { archive_coverage?: { stored_filings: number; companies_with_filings?: number; portfolio_companies?: number; by_company?: { ticker: string; stored_filings: number }[]; earliest_publication_date: string | null; latest_publication_date: string | null; exhaustive: boolean }; source_checks?: { url: string; last_checked_at: string | null; expires_at: string | null; last_error: string | null; overdue: boolean }[]; mode: string; label: string; important: Insight[]; routine: Insight[]; total_available: number; truncated: boolean; coverage: string; start: string; end_exclusive: string; refresh_status: { ticker: string; status: string; completed_at: string | null }[] }
export type Rule = { id: number; name: string; kind: string; ticker: string | null; threshold: string | null; direction: string; lookback: number; categories: string[]; enabled: boolean }
export type Alert = { id: number; ticker: string; kind: string; observed_date: string; observed_at: string | null; triggered_at: string; mode: string; evidence: { triggering_value: string; threshold: string | string[]; comparison: string; calculation?: string; close?: string; volume?: number; previous_close?: string; previous_trading_date?: string; average_volume?: string; lookback_observations?: number; baseline_volumes?: { date: string; volume: number }[]; sources: { url: string; retrieved_at?: string; sha256?: string; raw_published?: string }[]; network?: Contact[]; corporate_action_limit?: string } }
export type Passage = { chunk_id: number; document_id: number; title: string; kind: string; page: number; text: string; url: string; period_end: string | null }
export type Metric = { metric: string; source_label: string; value: string; unit: string; period_end: string; citation: Citation; qoq: { change_percent: string | null; previous_value?: string; previous_period_end?: string } | null; yoy: { change_percent: string | null; previous_value?: string; previous_period_end?: string } | null }
export type ResearchResult = { id: number; ticker: string; workflow: string; question: string; status: string; message: string; evidence: Passage[]; evidence_period_end: string | null; answer: { claims: { text: string; citations: Citation[] }[] } | null; financials: { metrics: Metric[]; limitation?: string }; limitations: string[]; network: Contact[]; cache_hit: boolean; model_error: { message: string } | null }
export type Position = Company & { price: { close: string; currency: string; volume: number; trading_date: string; change_percent: string | null; previous_trading_date: string | null; provider: string; source_url: string; fetched_at: string } | null; source_state: string; source_note: string; primary_document_count: number }
export type Overview = { items: Position[]; summary: { companies: number; sectors: number; price_coverage: number; primary_source_coverage: number; latest_trade_date: string | null; oldest_trade_date: string | null }; replay_window: { start: string; end_exclusive: string } | null; generated_at: string; ownership: string }
export type SourceDocument = { id: number; title: string; kind: string; page_count: number; extraction_status: string; published_date: string | null; period_end: string | null; date_basis: string; provenance: { source_url: string; fetched_at: string; sha256: string } }
export type Health = { access_mode?: 'local' | 'reviewer'; ephemeral_storage?: boolean; bootstrap?: {status: string; completed_jobs: number; failed_jobs: number}; status: string; providers: { llm: { configured: boolean; model: string | null }; market: unknown; filings: unknown; fundamentals: unknown } }
const base = (import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8001/api/v1').replace(/\/$/, '')
let reviewerToken = ''
export function setReviewerToken(token: string) { reviewerToken = token }
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController()
  const external = init?.signal
  const onAbort = () => controller.abort()
  if (external?.aborted) controller.abort()
  external?.addEventListener('abort', onAbort, { once: true })
  let timedOut = false
  const timeout = setTimeout(() => { timedOut = true; controller.abort() }, 60000)
  try {
    const headers = new Headers(init?.headers)
    if (reviewerToken) headers.set('Authorization', 'Bearer ' + reviewerToken)
    const response = await fetch(`${base}${path}`, { ...init, headers, signal: controller.signal })
    if (!response.ok) {
      let message = `Request failed (${response.status}). Please try again.`
      try {
        const body = await response.json()
        if (typeof body.detail === 'string') message = body.detail
        else if (Array.isArray(body.detail)) message = body.detail.map((d: { msg?: string }) => d.msg ?? 'Invalid input').join('. ')
      } catch { /* use HTTP error */ }
      throw new Error(message)
    }
    return await response.json() as T
  } catch (error) {
    if (timedOut) throw new Error('The request took too long. Please retry; an earlier saved result may still be available.')
    if (error instanceof TypeError) throw new Error('Cannot reach FINN. Check that the backend is running, then retry.')
    throw error
  } finally {
    clearTimeout(timeout)
    external?.removeEventListener('abort', onAbort)
  }
}
export function jsonBody(body: unknown, method = 'POST'): RequestInit { return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } }
export function localToday(): string { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}` }
