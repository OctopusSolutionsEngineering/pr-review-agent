"""High-level review orchestration."""
import logging
from agent import get_agent
from prompts import USER_TEMPLATE, DRY_RUN_SUFFIX
from config import get_settings

logger = logging.getLogger(__name__)


class ReviewError(Exception):
    pass


def review_pr(repo: str, pr_number: int, dry_run: bool = False) -> dict:
    """Run the agent to review a PR."""
    settings = get_settings()
    
    # Safety: repo allowlist
    if settings.allowed_repos_set and repo not in settings.allowed_repos_set:
        raise ReviewError(f"Repository '{repo}' is not in the allowlist")
    
    # Force dry-run if configured
    if settings.default_dry_run:
        dry_run = True
    
    logger.info(f"Starting review for {repo}#{pr_number} (dry_run={dry_run})")
    
    user_input = USER_TEMPLATE.format(repo=repo, pr_number=pr_number)
    if dry_run:
        user_input += DRY_RUN_SUFFIX
    
    agent = get_agent(read_only=dry_run)
    result = agent.invoke({"input": user_input})
    
    return {
        "repo": repo,
        "pr_number": pr_number,
        "review": result["output"],
        "steps_taken": len(result.get("intermediate_steps", [])),
        "dry_run": dry_run,
    }
