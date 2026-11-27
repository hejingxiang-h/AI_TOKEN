from typing import Literal

from pydantic import BaseModel


class Liveness(BaseModel):
    status: Literal["alive"] = "alive"


class DependencyCheck(BaseModel):
    status: Literal["up", "down"]
    latency_ms: float


class HealthChecks(BaseModel):
    postgresql: DependencyCheck
    redis: DependencyCheck


class Readiness(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: HealthChecks
