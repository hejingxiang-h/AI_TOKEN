from fastapi import APIRouter, Request, Response, status

from app.schemas.health import Liveness, Readiness
from app.services.health import HealthService

router = APIRouter(tags=["health"])


@router.get("/health/live", response_model=Liveness)
async def live(response: Response) -> Liveness:
    response.headers["Cache-Control"] = "no-store"
    return Liveness()


@router.get(
    "/health",
    response_model=Readiness,
    responses={503: {"model": Readiness}},
)
@router.get(
    "/health/ready",
    response_model=Readiness,
    responses={503: {"model": Readiness}},
)
async def ready(request: Request, response: Response) -> Readiness:
    service: HealthService = request.app.state.health_service
    result = await service.readiness()
    response.headers["Cache-Control"] = "no-store"
    if result.status == "not_ready":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result
