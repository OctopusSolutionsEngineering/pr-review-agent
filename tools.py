"""GitHub tools with caching."""
import logging
import requests
from github import Github, Auth
from langchain_core.tools import tool

from config import get_settings
from cache import get_cache, make_cache_key

logger = logging.getLogger(__name__)


def _get_github_client() -> Github:
    token = get_settings().github_token
    return Github(auth=Auth.Token(token))


def _cached_call(namespace: str, ttl: int, fn, *args, **kwargs):
    """Wrap a function call with cache lookup."""
    settings = get_settings()
    if not settings.enable_tool_cache:
        return fn(*args, **kwargs)
    
    cache = get_cache()
    key = make_cache_key(namespace, *args, **kwargs)
    cached = cache.get(key)
    if cached is not None:
        logger.info(f"🎯 Cache HIT: {namespace}")
        return cached
    
    logger.info(f"💨 Cache MISS: {namespace}")
    result = fn(*args, **kwargs)
    if isinstance(result, dict) and "error" not in result:
        cache.set(key, result, ttl)
    return result


# ===== Inner implementations =====

def _fetch_pr_metadata(repo: str, pr_number: int) -> dict:
    try:
        pr = _get_github_client().get_repo(repo).get_pull(pr_number)
        return {
            "title": pr.title,
            "description": pr.body or "",
            "author": pr.user.login,
            "base_branch": pr.base.ref,
            "head_branch": pr.head.ref,
            "head_sha": pr.head.sha,
            "state": pr.state,
            "draft": pr.draft,
            "additions": pr.additions,
            "deletions": pr.deletions,
            "changed_files": pr.changed_files,
            "labels": [l.name for l in pr.labels],
            "url": pr.html_url,
        }
    except Exception as e:
        return {"error": f"Failed to get PR metadata: {str(e)}"}


def _fetch_pr_diff(repo: str, pr_number: int, max_chars: int) -> dict:
    try:
        token = get_settings().github_token
        url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3.diff",
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        diff = response.text
        return {
            "diff": diff[:max_chars],
            "truncated": len(diff) > max_chars,
            "total_chars": len(diff),
        }
    except Exception as e:
        return {"error": f"Failed to get diff: {str(e)}"}


def _fetch_pr_files(repo: str, pr_number: int) -> dict:
    try:
        pr = _get_github_client().get_repo(repo).get_pull(pr_number)
        files = []
        for f in pr.get_files():
            files.append({
                "filename": f.filename,
                "status": f.status,
                "additions": f.additions,
                "deletions": f.deletions,
                "patch": (f.patch or "")[:5000],
            })
        return {"files": files, "count": len(files)}
    except Exception as e:
        return {"error": f"Failed to list files: {str(e)}"}


def _fetch_file_content(repo: str, path: str, ref: str) -> dict:
    try:
        content = _get_github_client().get_repo(repo).get_contents(path, ref=ref)
        text = content.decoded_content.decode("utf-8", errors="replace")
        return {
            "path": path,
            "content": text[:10000],
            "truncated": len(text) > 10000,
            "size": content.size,
        }
    except Exception as e:
        return {"error": f"Failed to get file: {str(e)}"}


# ===== Cached tool wrappers =====

@tool
def get_pr_metadata(repo: str, pr_number: int) -> dict:
    """Fetch metadata about a pull request.
    
    Args:
        repo: Repository in 'owner/name' format.
        pr_number: The PR number.
    """
    ttl = get_settings().cache_ttl_pr_metadata
    return _cached_call("pr_metadata", ttl, _fetch_pr_metadata, repo, pr_number)


@tool
def get_pr_diff(repo: str, pr_number: int) -> dict:
    """Fetch the unified diff of a pull request.
    
    Args:
        repo: Repository in 'owner/name' format.
        pr_number: The PR number.
    """
    settings = get_settings()
    return _cached_call(
        "pr_diff", settings.cache_ttl_pr_diff,
        _fetch_pr_diff, repo, pr_number, settings.max_diff_chars,
    )


@tool
def list_changed_files(repo: str, pr_number: int) -> dict:
    """List all files changed in a PR with per-file stats.
    
    Args:
        repo: Repository in 'owner/name' format.
        pr_number: The PR number.
    """
    ttl = get_settings().cache_ttl_pr_files
    return _cached_call("pr_files", ttl, _fetch_pr_files, repo, pr_number)


@tool
def get_file_content(repo: str, path: str, ref: str) -> dict:
    """Get the full content of a file at a specific commit/branch.
    
    Args:
        repo: Repository in 'owner/name' format.
        path: File path within the repo.
        ref: Branch name or commit SHA.
    """
    ttl = get_settings().cache_ttl_file_content
    return _cached_call("file_content", ttl, _fetch_file_content, repo, path, ref)


# ===== Write tools (NOT cached) =====

@tool
def post_review_comment(
    repo: str,
    pr_number: int,
    body: str,
    event: str = "COMMENT",
) -> dict:
    """Post a top-level review on a PR.
    
    Args:
        repo: Repository in 'owner/name' format.
        pr_number: The PR number.
        body: The review body (markdown supported).
        event: One of 'COMMENT', 'APPROVE', or 'REQUEST_CHANGES'.
    """
    if event not in {"COMMENT", "APPROVE", "REQUEST_CHANGES"}:
        return {"error": f"Invalid event: {event}"}
    try:
        pr = _get_github_client().get_repo(repo).get_pull(pr_number)
        review = pr.create_review(body=body, event=event)
        return {
            "success": True,
            "review_id": review.id,
            "event": event,
            "url": review.html_url,
        }
    except Exception as e:
        return {"error": f"Failed to post review: {str(e)}"}


@tool
def post_inline_comment(
    repo: str,
    pr_number: int,
    body: str,
    file_path: str,
    line: int,
) -> dict:
    """Post an inline comment on a specific line of a PR diff.
    
    Args:
        repo: Repository in 'owner/name' format.
        pr_number: The PR number.
        body: The comment text.
        file_path: The file to comment on.
        line: Line number (RIGHT side / new file).
    """
    try:
        pr = _get_github_client().get_repo(repo).get_pull(pr_number)
        commit = pr.get_commits().reversed[0]
        comment = pr.create_review_comment(
            body=body, commit=commit, path=file_path, line=line, side="RIGHT",
        )
        return {"success": True, "comment_id": comment.id, "url": comment.html_url}
    except Exception as e:
        return {"error": f"Failed to post inline comment: {str(e)}"}


REVIEW_TOOLS = [
    get_pr_metadata,
    get_pr_diff,
    list_changed_files,
    get_file_content,
    post_review_comment,
    post_inline_comment,
]

# Read-only tool subset (for dry-run and inter-agent calls)
READ_ONLY_TOOLS = [
    get_pr_metadata,
    get_pr_diff,
    list_changed_files,
    get_file_content,
]
