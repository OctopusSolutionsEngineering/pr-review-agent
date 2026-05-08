"""Tools the agent uses to interact with GitHub."""
import os
from typing import Optional
from github import Github, Auth
from langchain_core.tools import tool
from unidiff import PatchSet


def _get_github_client() -> Github:
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise ValueError("GITHUB_TOKEN environment variable not set")
    return Github(auth=Auth.Token(token))


@tool
def get_pr_metadata(repo: str, pr_number: int) -> dict:
    """Fetch metadata about a pull request.
    
    Args:
        repo: Repository in 'owner/name' format (e.g., 'octocat/hello-world').
        pr_number: The PR number.
    
    Returns:
        Dict with title, description, author, base/head branches, and stats.
    """
    try:
        gh = _get_github_client()
        pr = gh.get_repo(repo).get_pull(pr_number)
        return {
            "title": pr.title,
            "description": pr.body or "",
            "author": pr.user.login,
            "base_branch": pr.base.ref,
            "head_branch": pr.head.ref,
            "state": pr.state,
            "additions": pr.additions,
            "deletions": pr.deletions,
            "changed_files": pr.changed_files,
            "url": pr.html_url,
        }
    except Exception as e:
        return {"error": f"Failed to get PR metadata: {str(e)}"}


@tool
def get_pr_diff(repo: str, pr_number: int, max_chars: int = 30000) -> dict:
    """Fetch the unified diff of a pull request.
    
    Args:
        repo: Repository in 'owner/name' format.
        pr_number: The PR number.
        max_chars: Maximum characters to return (truncates large diffs).
    
    Returns:
        Dict with the diff text and a truncation flag.
    """
    try:
        import requests
        token = os.getenv("GITHUB_TOKEN")
        url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3.diff",
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        diff = response.text
        truncated = len(diff) > max_chars
        return {
            "diff": diff[:max_chars],
            "truncated": truncated,
            "total_chars": len(diff),
        }
    except Exception as e:
        return {"error": f"Failed to get diff: {str(e)}"}


@tool
def list_changed_files(repo: str, pr_number: int) -> dict:
    """List all files changed in a PR with per-file stats.
    
    Args:
        repo: Repository in 'owner/name' format.
        pr_number: The PR number.
    
    Returns:
        List of files with filename, status, additions, deletions, and patch.
    """
    try:
        gh = _get_github_client()
        pr = gh.get_repo(repo).get_pull(pr_number)
        files = []
        for f in pr.get_files():
            files.append({
                "filename": f.filename,
                "status": f.status,  # added, modified, removed, renamed
                "additions": f.additions,
                "deletions": f.deletions,
                "patch": (f.patch or "")[:5000],  # truncate huge patches
            })
        return {"files": files, "count": len(files)}
    except Exception as e:
        return {"error": f"Failed to list files: {str(e)}"}


@tool
def get_file_content(repo: str, path: str, ref: str) -> dict:
    """Get the full content of a file at a specific commit/branch.
    
    Useful for understanding context beyond the diff.
    
    Args:
        repo: Repository in 'owner/name' format.
        path: File path within the repo.
        ref: Branch name or commit SHA.
    
    Returns:
        Dict with the file content (truncated if very large).
    """
    try:
        gh = _get_github_client()
        content = gh.get_repo(repo).get_contents(path, ref=ref)
        text = content.decoded_content.decode("utf-8", errors="replace")
        return {
            "path": path,
            "content": text[:10000],
            "truncated": len(text) > 10000,
            "size": content.size,
        }
    except Exception as e:
        return {"error": f"Failed to get file: {str(e)}"}


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
    
    Returns:
        Dict confirming the post.
    """
    if event not in {"COMMENT", "APPROVE", "REQUEST_CHANGES"}:
        return {"error": f"Invalid event: {event}"}
    try:
        gh = _get_github_client()
        pr = gh.get_repo(repo).get_pull(pr_number)
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
        body: The comment text (markdown supported).
        file_path: The file to comment on.
        line: The line number in the diff (RIGHT side / new file).
    
    Returns:
        Dict confirming the post.
    """
    try:
        gh = _get_github_client()
        pr = gh.get_repo(repo).get_pull(pr_number)
        commit = pr.get_commits().reversed[0]  # latest commit
        comment = pr.create_review_comment(
            body=body,
            commit=commit,
            path=file_path,
            line=line,
            side="RIGHT",
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
