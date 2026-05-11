"""FastAPI service for triggering PR reviews."""
import hmac
import hashlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Header, BackgroundTasks
from pydantic import BaseModel, Field

from reviewer import review_pr, ReviewError
from cache import get_cache
from config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger(__name__)
    logger.info(f"Starting pr-review-agent (model={settings.openai_model})")
    logger.info(f"Cache backend: {settings.cache_backend}")
    logger.info(f"Allowed repos: {settings.allowed_repos_set or 'ALL'}")
    
    get_cache()
    from agent import get_agent
    get_agent()
    logger.info("Agent ready ✓")
    yield
    logger.info("Shutting down")


app = FastAPI(
    title="PR Review Agent",
    version="1.2.0",
    description="AI agent that reviews GitHub pull requests.",
    lifespan=lifespan,
)
logger = logging.getLogger(__name__)


class ReviewRequest(BaseModel):
    repo: str = Field(..., examples=["octocat/hello-world"])
    pr_number: int = Field(..., gt=0)
    dry_run: bool = False


@app.get("/")
def root():
    return {"service": "pr-review-agent", "status": "ok"}


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/ready")
def ready():
    try:
        settings = get_settings()
        return {
            "status": "ready",
            "model": settings.openai_model,
            "cache_backend": settings.cache_backend,
            "allowed_repos": list(settings.allowed_repos_set) or "all",
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.post("/review")
def trigger_review(payload: ReviewRequest):
    """Trigger a PR review synchronously."""
    try:
        return review_pr(payload.repo, payload.pr_number, payload.dry_run)
    except ReviewError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.exception("Review failed")
        raise HTTPException(status_code=500, detail=str(e))


def verify_github_signature(payload_body: bytes, signature_header: str) -> bool:
    secret = get_settings().github_webhook_secret.encode()
    if not secret or not signature_header:
        return False
    expected = "sha256=" + hmac.new(secret, payload_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)


@app.post("/webhook")
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_github_event: str = Header(default=""),
    x_hub_signature_256: str = Header(default=""),
):
    body = await request.body()
    
    if not verify_github_signature(body, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    if x_github_event != "pull_request":
        return {"status": "ignored", "reason": f"event '{x_github_event}'"}
    
    payload = await request.json()
    action = payload.get("action")
    
    if action not in {"opened", "synchronize", "reopened", "labeled"}:
        return {"status": "ignored", "reason": f"action '{action}'"}
    
    pr = payload["pull_request"]
    repo = payload["repository"]["full_name"]
    pr_number = pr["number"]
    
    if pr.get("draft"):
        return {"status": "ignored", "reason": "draft PR"}
    
    # Check label requirement
    settings = get_settings()
    if settings.require_label:
        labels = {l["name"] for l in pr.get("labels", [])}
        if settings.require_label not in labels:
            return {"status": "ignored", "reason": f"missing label '{settings.require_label}'"}
    
    logger.info(f"Webhook → review {repo}#{pr_number}")
    background_tasks.add_task(review_pr, repo, pr_number, False)
    return {"status": "queued", "repo": repo, "pr_number": pr_number}


# ===== Cache management =====

@app.get("/cache/stats")
def cache_stats():
    return get_cache().stats()


@app.post("/cache/clear")
def cache_clear():
    get_cache().clear()
    return {"status": "cleared"}