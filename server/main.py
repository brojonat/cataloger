import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict

import anthropic
import structlog
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jose import JWTError, jwt
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, Field

from cataloger.container.pool import ContainerPool
from cataloger.storage.s3 import S3Storage
from cataloger.workflow.catalog import CatalogWorkflow

# -------------------------
# Logging configuration
# -------------------------


def configure_logging() -> None:
    log_level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(structlog, log_level_name, structlog.INFO)
    json_logs = os.getenv("LOG_JSON", "false").lower() == "true"
    service_name = os.getenv("SERVICE_NAME", "cataloger")

    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    if json_logs:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Bind common fields
    structlog.contextvars.bind_contextvars(service=service_name)


configure_logging()
log = structlog.get_logger()

# -------------------------
# Auth configuration
# -------------------------
JWT_SECRET = os.getenv("AUTH_SECRET", "change-me")
JWT_ALG = os.getenv("JWT_ALG", "HS256")
security = HTTPBearer(auto_error=True)


def require_claims(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> Dict:
    token = credentials.credentials
    try:
        claims = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return claims


# -------------------------
# Global state
# -------------------------
container_pool: ContainerPool | None = None
s3_storage: S3Storage | None = None
catalog_workflow: CatalogWorkflow | None = None
anthropic_client: anthropic.Anthropic | None = None


# -------------------------
# App & instrumentation
# -------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    global container_pool, s3_storage, catalog_workflow, anthropic_client

    log.info("service.startup")

    # Initialize Anthropic client
    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
    if not anthropic_api_key:
        log.error("Missing ANTHROPIC_API_KEY environment variable")
        sys.exit(1)
    anthropic_client = anthropic.Anthropic(api_key=anthropic_api_key)

    # Initialize S3 storage
    s3_bucket = os.getenv("S3_BUCKET")
    s3_region = os.getenv("S3_REGION", "us-east-1")
    if not s3_bucket:
        log.error("Missing S3_BUCKET environment variable")
        sys.exit(1)
    s3_storage = S3Storage(bucket=s3_bucket, region=s3_region)

    # Initialize container pool
    container_image = os.getenv("CONTAINER_IMAGE", "cataloger-agent:latest")
    pool_size = int(os.getenv("CONTAINER_POOL_SIZE", "5"))
    container_pool = ContainerPool(image_name=container_image, pool_size=pool_size)

    # Initialize catalog workflow
    catalog_workflow = CatalogWorkflow(
        container_pool=container_pool,
        s3_storage=s3_storage,
        anthropic_client=anthropic_client,
    )

    try:
        yield
    finally:
        log.info("service.shutdown")
        if container_pool:
            container_pool.cleanup()


app = FastAPI(title=os.getenv("SERVICE_NAME", "cataloger"), lifespan=lifespan)

# Prometheus: exposes /metrics by default
Instrumentator().instrument(app).expose(app)

# Templates and static files
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


# -------------------------
# Request/Response Models
# -------------------------


class CatalogRequest(BaseModel):
    """Request to generate a database catalog."""

    db_connection_string: str = Field(
        ..., description="Readonly database connection string"
    )
    tables: list[str] = Field(..., description="List of table names to catalog")
    s3_prefix: str = Field(
        ..., description="S3 prefix for storing results (e.g., 'customer-123/orders')"
    )


class CatalogResponse(BaseModel):
    """Response from catalog generation."""

    timestamp: str
    catalog_uri: str
    summary_uri: str
    s3_prefix: str


# -------------------------
# Endpoints
# -------------------------


@app.get("/healthz", tags=["health"])
def healthz():
    return {"status": "ok"}


@app.get("/whoami", tags=["auth"])
def whoami(claims: Dict = Depends(require_claims)):
    return {"claims": claims}


@app.get("/", response_class=HTMLResponse, tags=["ui"])
async def root(request: Request):
    """Home page with navigation."""
    return templates.TemplateResponse(
        "index.html",
        {"request": request}
    )


@app.get("/database/current", response_class=HTMLResponse, tags=["ui"])
async def database_current(request: Request, prefix: str):
    """View the most recent catalog for a database prefix."""
    if not s3_storage:
        raise HTTPException(status_code=503, detail="S3 storage not initialized")

    # Get latest timestamp
    timestamps = s3_storage.list_timestamps(prefix, limit=1)
    if not timestamps:
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "message": f"No catalogs found for prefix: {prefix}"}
        )

    latest_timestamp = timestamps[0]

    # Get all files for this timestamp
    catalogs = s3_storage.list_catalogs(prefix, latest_timestamp)

    return templates.TemplateResponse(
        "current.html",
        {
            "request": request,
            "prefix": prefix,
            "timestamp": latest_timestamp,
            "catalogs": catalogs
        }
    )


@app.get("/database/timelapse", response_class=HTMLResponse, tags=["ui"])
async def database_timelapse(request: Request, prefix: str):
    """View all catalogs for a database prefix over time."""
    if not s3_storage:
        raise HTTPException(status_code=503, detail="S3 storage not initialized")

    # Get all timestamps
    timestamps = s3_storage.list_timestamps(prefix, limit=50)
    if not timestamps:
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "message": f"No catalogs found for prefix: {prefix}"}
        )

    return templates.TemplateResponse(
        "timelapse.html",
        {
            "request": request,
            "prefix": prefix,
            "timestamps": timestamps
        }
    )


@app.get("/api/catalog/content", tags=["api"])
async def get_catalog_content(prefix: str, timestamp: str, filename: str, request: Request):
    """Fetch catalog HTML content from S3."""
    if not s3_storage:
        raise HTTPException(status_code=503, detail="S3 storage not initialized")

    try:
        content = s3_storage.read_html(prefix, timestamp, filename)
        # Return HTML fragment
        return templates.TemplateResponse(
            "catalog_content_fragment.html",
            {
                "request": request,
                "content": content,
                "filename": filename
            }
        )
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/catalog/list", tags=["api"])
async def list_catalog_files(prefix: str, timestamp: str, request: Request):
    """List all catalog files for a specific timestamp."""
    if not s3_storage:
        raise HTTPException(status_code=503, detail="S3 storage not initialized")

    catalogs = s3_storage.list_catalogs(prefix, timestamp)

    # Return HTML fragment for htmx
    return templates.TemplateResponse(
        "catalog_list_fragment.html",
        {
            "request": request,
            "prefix": prefix,
            "timestamp": timestamp,
            "catalogs": catalogs
        }
    )


@app.post("/catalog", tags=["catalog"], response_model=CatalogResponse)
def create_catalog(
    request: CatalogRequest,
    claims: Dict = Depends(require_claims),
):
    """Generate a database catalog.

    This endpoint triggers an asynchronous workflow that:
    1. Spins up a container with Python + ibis
    2. Runs a cataloging agent to explore the database
    3. Generates and stores an HTML catalog in S3
    4. Runs a summary agent to analyze recent catalogs
    5. Generates and stores an HTML summary in S3

    Returns S3 URIs for both HTML reports.
    """
    if not catalog_workflow:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Catalog workflow not initialized",
        )

    log.info(
        "catalog.request",
        user=claims.get("sub"),
        tables=request.tables,
        s3_prefix=request.s3_prefix,
    )

    try:
        result = catalog_workflow.run(
            db_connection_string=request.db_connection_string,
            tables=request.tables,
            s3_prefix=request.s3_prefix,
        )

        log.info("catalog.complete", result=result)
        return CatalogResponse(**result)

    except Exception as e:
        log.error("catalog.error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Catalog generation failed: {str(e)}",
        )


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host=host, port=port, reload=False)
