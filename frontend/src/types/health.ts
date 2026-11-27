export type ConnectionStatus = 'up' | 'down'

export interface DependencyCheck {
  status: ConnectionStatus
  latency_ms: number
}

export interface HealthResponse {
  status: 'ready' | 'not_ready'
  checks: {
    postgresql: DependencyCheck
    redis: DependencyCheck
  }
}
