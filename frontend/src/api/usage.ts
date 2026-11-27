export interface Metrics {
  input_tokens: number | null
  output_tokens: number | null
  cache_tokens: number | null
  total_tokens: number | null
  calls: number
  successes: number
  failures: number
  in_progress: number
  active_users: number
  active_keys: number
  average_response_ms: string | null
  unsettled: number
  unknown_usage: number
  costs: Record<string, string>
  success_rate: string | null
}
export interface Window {
  timezone: string
  start: string
  end: string
  start_at: string
  end_at: string
}
export interface Summary {
  window: Window
  metrics: Metrics
}
export interface Group {
  id: string
  label: string
  metrics: Metrics
}
export interface Breakdown {
  window: Window
  items: Group[]
}
export interface UsageRecord {
  id: string
  model: string
  provider: string
  protocol: string
  started_at: string
  finished_at: string | null
  client_type: string | null
  risk_state: string
  duration_ms: number | null
  status: string
  settlement: string
  currency: string
  normalized_usage: Record<string, number> | null
  platform_cost: string | null
  usage_source: string | null
  price_id: string
  user_id: string
  department_id: string
  project_id: string
  key_id: string
}
export interface UsageDetail extends UsageRecord {
  source_ip: string | null
  raw_usage: Record<string, unknown> | null
  supplier_cost: string | null
  supplier_request_id: string | null
  proxy_call_id: string | null
}
export interface UsagePage {
  window: Window
  items: UsageRecord[]
  total: number
}
