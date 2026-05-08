"""High-level review orchestration."""
import logging
from typing import Optional
from agent import get_agent
from prompts import USER_TEMPLATE

logger = logging.getLogger(__name__)


def review_pr(repo: str, pr_number: int, dry_run: bool = False) -> dict:
    """Run the agent to review a PR.
    
    Args:
        repo: 'owner/name' format
        pr_number: PR number
        dry_run: If True, agent is told NOT to post the review
    
    Returns:
        Dict with the agent's output and metadata.
    """
    logger.info(f"Starting review for {repo}#{pr_number} (dry_run={dry_run})")
    
    user_input = USER_TEMPLATE.format(repo=repo, pr_number=pr_number)
    if dry_run:
        user_input += "\n\nIMPORTANT: This is a dry run. Do NOT post anything to GitHub. Just return your review as a string."
    
    agent = get_agent()
    result = agent.invoke({"input": user_input})
    
    return {
        "repo": repo,
        "pr_number": pr_number,
        "review": result["output"],
        "steps_taken": len(result.get("intermediate_steps", [])),
    }
