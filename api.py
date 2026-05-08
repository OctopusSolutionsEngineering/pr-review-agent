"""FastAPI service for triggering PR reviews."""
import os
import hmac
import hashlib
import logging
from fastapi import FastAPI, HTTPException, Request, Header, BackgroundTasks
from pydantic import BaseModel, Field

from reviewer import review_pr

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="PR Review Agent", version="1.0.0")


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


@app.post("/review")
def trigger_review(payload: ReviewRequest):
    """Manually trigger a PR review."""
    try:
        result = review_pr(payload.repo, payload.pr_number, payload.dry_run)
        return result
    except Exception as e:
        logger.exception("Review failed")
        raise HTTPException(status_code=500, detail=str(e))


def verify_github_signature(payload_body: bytes, signature_header: str) -> bool:
    """Verify GitHub webhook signature (HMAC-SHA256)."""
    secret = os.getenv("GITHUB_WEBHOOK_SECRET", "").encode()
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
    """Receive GitHub webhook events for PRs."""
    body = await request.body()
    
    if not verify_github_signature(body, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    if x_github_event != "pull_request":
        return {"status": "ignored", "reason": f"event '{x_github_event}' not handled"}
    
    payload = await request.json()
    action = payload.get("action")
    
    # Trigger review on opened or new commits
    if action not in {"opened", "synchronize", "reopened"}:
        return {"status": "ignored", "reason": f"action '{action}' not handled"}
    
    repo = payload["repository"]["full_name"]
    pr_number = payload["pull_request"]["number"]
    
    # Skip draft PRs
    if payload["pull_request"].get("draft"):
        return {"status": "ignored", "reason": "draft PR"}
    
    logger.info(f"Webhook triggered review for {repo}#{pr_number}")
    
    # Run review in background so webhook returns quickly
    background_tasks.add_task(review_pr, repo, pr_number, False)
    
    return {"status": "queued", "repo": repo, "pr_number": pr_number}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
