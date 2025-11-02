import logging
import os
import sys
import traceback
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict

import anthropic
import structlog
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jose import JWTError, jwt
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

from cataloger.container.pool import ContainerPool
from cataloger.context import generate_context_summary, strip_html_tags
from cataloger.storage.s3 import S3Storage
from cataloger.workflow.catalog import CatalogWorkflow

# -------------------------
# Logging configuration
# -------------------------


def configure_logging() -> None:
    log_level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)
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
_services_initialized: bool = False


# -------------------------
# App & instrumentation
# -------------------------


def initialize_services():
    """Initialize all services."""
    global container_pool, s3_storage, catalog_workflow, anthropic_client, _services_initialized

    # Skip if already initialized (guards against multiple calls in same process)
    if _services_initialized:
        log.info("service.already_initialized", skip=True)
        return

    log.info("service.initialize")

    # Initialize LLM client (currently using Anthropic)
    llm_api_key = os.getenv("LLM_API_KEY")
    if not llm_api_key:
        log.error("Missing LLM_API_KEY environment variable")
        sys.exit(1)
    anthropic_client = anthropic.Anthropic(api_key=llm_api_key)

    # Get model name (defaults to claude-haiku-4-5)
    model_name = os.getenv("MODEL_NAME", "claude-haiku-4-5")

    # Initialize S3 storage
    s3_bucket = os.getenv("S3_BUCKET")
    s3_region = os.getenv("S3_REGION", "us-east-1")
    s3_endpoint_url = os.getenv("S3_ENDPOINT_URL")  # For MinIO/LocalStack
    s3_access_key = os.getenv("AWS_ACCESS_KEY_ID")
    s3_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")

    if not s3_bucket:
        log.error("Missing S3_BUCKET environment variable")
        sys.exit(1)

    s3_storage = S3Storage(
        bucket=s3_bucket,
        region=s3_region,
        access_key_id=s3_access_key,
        secret_access_key=s3_secret_key,
        endpoint_url=s3_endpoint_url,
    )

    # Initialize container pool
    container_image = os.getenv("CONTAINER_IMAGE", "cataloger-agent:latest")
    pool_size = int(os.getenv("CONTAINER_POOL_SIZE", "5"))
    container_pool = ContainerPool(image_name=container_image, pool_size=pool_size)

    # Initialize catalog workflow
    catalog_workflow = CatalogWorkflow(
        container_pool=container_pool,
        s3_storage=s3_storage,
        anthropic_client=anthropic_client,
        model_name=model_name,
    )
    _services_initialized = True
    log.info("service.initialized", model=model_name)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("service.startup")

    # Check and log service availability at startup
    all_available, missing = check_service_availability()
    if all_available:
        log.info("service.startup.check", status="all_services_available")
    else:
        log.warning(
            "service.startup.check",
            status="missing_services",
            missing=missing,
            note="API endpoints may return 503 errors",
        )

    try:
        yield
    finally:
        log.info("service.shutdown")
        if container_pool:
            container_pool.cleanup()


# -------------------------
# Error logging middleware
# -------------------------


class ErrorLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log all 5XX responses with detailed error information."""

    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)

            # Log all 5XX responses
            if response.status_code >= 500:
                # Try to read response body for error details
                body = b""
                async for chunk in response.body_iterator:
                    body += chunk

                # Create new response with same content
                response = Response(
                    content=body,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.media_type,
                )

                # Log the error with full context
                log.error(
                    "http.5xx_response",
                    status_code=response.status_code,
                    method=request.method,
                    url=str(request.url),
                    path=request.url.path,
                    query_params=dict(request.query_params),
                    client_host=request.client.host if request.client else None,
                    response_body=body.decode("utf-8", errors="replace")[:1000],  # First 1000 chars
                )

            return response

        except Exception as e:
            # Log unhandled exceptions
            log.error(
                "http.unhandled_exception",
                error=str(e),
                error_type=type(e).__name__,
                method=request.method,
                url=str(request.url),
                path=request.url.path,
                traceback=traceback.format_exc(),
            )
            raise


# Initialize services before creating FastAPI app
initialize_services()

app = FastAPI(title=os.getenv("SERVICE_NAME", "cataloger"), lifespan=lifespan)

# Add error logging middleware
app.add_middleware(ErrorLoggingMiddleware)

# Prometheus: exposes /metrics by default
Instrumentator().instrument(app).expose(app)

# Templates and static files
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


# -------------------------
# Helper Functions
# -------------------------


def check_service_availability():
    """Check which services are available and log if any are missing.

    Returns:
        tuple: (all_available: bool, missing_services: list[str])
    """
    missing = []

    if s3_storage is None:
        missing.append("s3_storage")
    if catalog_workflow is None:
        missing.append("catalog_workflow")
    if anthropic_client is None:
        missing.append("anthropic_client")
    if container_pool is None:
        missing.append("container_pool")

    if missing:
        log.error(
            "service.availability_check_failed",
            missing_services=missing,
            note="Services not initialized - this will cause 503 errors",
        )
        return False, missing

    return True, []


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


class CommentRequest(BaseModel):
    """Request to add a comment to a catalog."""

    prefix: str = Field(..., description="S3 prefix (e.g., 'customer-123/orders')")
    timestamp: str = Field(..., description="Timestamp of catalog to comment on")
    user: str = Field(..., description="Username of commenter")
    comment: str = Field(..., description="Comment text")


class CommentResponse(BaseModel):
    """Response from adding a comment."""

    uri: str
    user: str
    timestamp: str


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
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/database/timelapse", response_class=HTMLResponse, tags=["ui"])
async def database_timelapse(request: Request, prefix: str):
    """View all catalogs for a database prefix over time."""
    if not s3_storage:
        check_service_availability()
        raise HTTPException(status_code=503, detail="S3 storage not initialized")

    # Get all timestamps
    timestamps = s3_storage.list_timestamps(prefix, limit=50)
    if not timestamps:
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "message": f"No catalogs found for prefix: {prefix}"},
        )

    # Get files for each timestamp
    catalog_runs = []
    for ts in timestamps:
        files = s3_storage.list_all_files(prefix, ts)
        catalog_runs.append({
            "timestamp": ts,
            "files": files,
        })

    return templates.TemplateResponse(
        "timelapse.html",
        {"request": request, "prefix": prefix, "catalog_runs": catalog_runs},
    )


@app.get("/api/catalog/view", response_class=HTMLResponse, tags=["api"])
async def view_catalog_file(prefix: str, timestamp: str, filename: str):
    """View a catalog file (HTML or script) directly."""
    if not s3_storage:
        check_service_availability()
        raise HTTPException(status_code=503, detail="S3 storage not initialized")

    try:
        # Try reading as HTML first
        if filename.endswith('.html'):
            content = s3_storage.read_html(prefix, timestamp, filename)
            return HTMLResponse(content=content)
        elif filename.endswith('.py'):
            content = s3_storage.read_script(prefix, timestamp, filename)
            if content is None:
                raise HTTPException(status_code=404, detail=f"Script not found: {filename}")
            # Return Python code as HTML with syntax highlighting
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>{filename}</title>
                <style>
                    body {{
                        font-family: monospace;
                        padding: 2rem;
                        background: #1e1e1e;
                        color: #d4d4d4;
                        margin: 0;
                    }}
                    pre {{
                        background: #1e1e1e;
                        padding: 1rem;
                        border-radius: 4px;
                        overflow-x: auto;
                        white-space: pre-wrap;
                        word-wrap: break-word;
                    }}
                    h1 {{
                        color: #569cd6;
                        border-bottom: 2px solid #569cd6;
                        padding-bottom: 0.5rem;
                    }}
                </style>
            </head>
            <body>
                <h1>📄 {filename}</h1>
                <pre>{content}</pre>
            </body>
            </html>
            """
            return HTMLResponse(content=html_content)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {filename}")
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/catalog/content", tags=["api"])
async def get_catalog_content(
    prefix: str, timestamp: str, filename: str, request: Request
):
    """Fetch catalog HTML content from S3."""
    if not s3_storage:
        check_service_availability()
        raise HTTPException(status_code=503, detail="S3 storage not initialized")

    try:
        content = s3_storage.read_html(prefix, timestamp, filename)
        # Return HTML fragment
        return templates.TemplateResponse(
            "catalog_content_fragment.html",
            {"request": request, "content": content, "filename": filename},
        )
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/catalog/list", tags=["api"])
async def list_catalog_files(prefix: str, timestamp: str, request: Request):
    """List all catalog files for a specific timestamp."""
    if not s3_storage:
        check_service_availability()
        raise HTTPException(status_code=503, detail="S3 storage not initialized")

    catalogs = s3_storage.list_catalogs(prefix, timestamp)

    # Return HTML fragment for htmx
    return templates.TemplateResponse(
        "catalog_list_fragment.html",
        {
            "request": request,
            "prefix": prefix,
            "timestamp": timestamp,
            "catalogs": catalogs,
        },
    )


@app.get("/api/catalog/recent", response_class=HTMLResponse, tags=["api"])
async def list_recent_catalogs(request: Request, limit: int = 10):
    """List recent catalogs across all prefixes."""
    if not s3_storage:
        check_service_availability()
        raise HTTPException(status_code=503, detail="S3 storage not initialized")

    # Get all prefixes
    prefixes = s3_storage.list_prefixes(limit=50)

    # Get latest timestamp for each prefix
    recent_catalogs = []
    for prefix in prefixes:
        timestamps = s3_storage.list_timestamps(prefix, limit=1)
        if timestamps:
            recent_catalogs.append({
                "prefix": prefix,
                "timestamp": timestamps[0],
            })

    # Sort by timestamp (newest first)
    recent_catalogs.sort(key=lambda x: x["timestamp"], reverse=True)

    # Return HTML fragment for htmx
    return templates.TemplateResponse(
        "recent_catalogs_fragment.html",
        {
            "request": request,
            "catalogs": recent_catalogs[:limit],
        },
    )


@app.get("/catalog/context", response_class=HTMLResponse, tags=["catalog"])
async def get_catalog_context(
    prefix: str, timestamp: str | None = None, strip_tags: bool = False
):
    """Generate context summary HTML from previous catalog state.

    This endpoint bundles together:
    - Previous catalog results (HTML)
    - Previous summary analysis (HTML)
    - Python scripts that were executed
    - User comments/feedback

    Args:
        prefix: S3 prefix (e.g., 'customer-123/orders')
        timestamp: Specific timestamp, or None for latest
        strip_tags: If True, return plain text with HTML tags removed (for token efficiency)

    Returns:
        HTML summary document (or plain text if strip_tags=True)
    """
    if not s3_storage:
        check_service_availability()
        raise HTTPException(status_code=503, detail="S3 storage not initialized")

    try:
        context_html = generate_context_summary(s3_storage, prefix, timestamp)

        if strip_tags:
            # Return plain text for token efficiency
            context_text = strip_html_tags(context_html)
            return HTMLResponse(content=f"<pre>{context_text}</pre>")
        else:
            return HTMLResponse(content=context_html)
    except Exception as e:
        log.error("catalog.context.error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to generate context summary: {str(e)}"
        )


@app.post("/catalog/comment", tags=["catalog"], response_model=CommentResponse)
def add_catalog_comment(
    request: CommentRequest,
    claims: Dict = Depends(require_claims),
):
    """Add a comment to a catalog.

    Comments are stored in S3 alongside the catalog results at:
    s3://{bucket}/{prefix}/{timestamp}/comments/{user}-{date}.txt

    This allows human feedback to be included in future catalog contexts.
    """
    if not s3_storage:
        check_service_availability()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="S3 storage not initialized",
        )

    log.info(
        "catalog.comment",
        user=claims.get("sub"),
        prefix=request.prefix,
        timestamp=request.timestamp,
        comment_user=request.user,
    )

    try:
        uri = s3_storage.write_comment(
            prefix=request.prefix,
            timestamp=request.timestamp,
            user=request.user,
            comment=request.comment,
        )

        log.info("catalog.comment.complete", uri=uri)
        return CommentResponse(
            uri=uri,
            user=request.user,
            timestamp=request.timestamp,
        )

    except Exception as e:
        log.error("catalog.comment.error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add comment: {str(e)}",
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
    # Check if workflow is available
    if catalog_workflow is None:
        # Log detailed service availability info
        check_service_availability()
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
    reload = os.getenv("RELOAD", "false").lower() == "true"

    log.info("launcher.starting", reload=reload)
    uvicorn.run(
        "server.main:app" if reload else app,
        host=host,
        port=port,
        reload=reload,
        reload_dirs=["./server", "./src"] if reload else None,
        log_level="info",
    )
