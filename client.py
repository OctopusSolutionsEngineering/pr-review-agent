"""Client for the PR Review Agent API."""
import os
import sys
import argparse
import requests


class PRReviewClient:
    def __init__(self, base_url: str, timeout: int = 300):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
    
    def health(self) -> dict:
        r = self.session.get(f"{self.base_url}/health", timeout=5)
        r.raise_for_status()
        return r.json()
    
    def review(self, repo: str, pr_number: int, dry_run: bool = False) -> dict:
        r = self.session.post(
            f"{self.base_url}/review",
            json={"repo": repo, "pr_number": pr_number, "dry_run": dry_run},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()


def main():
    parser = argparse.ArgumentParser(description="PR Review Agent client")
    parser.add_argument("repo", help="owner/name")
    parser.add_argument("pr_number", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--url",
        default=os.getenv("PR_REVIEW_URL", "http://localhost:8000"),
    )
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()
    
    client = PRReviewClient(args.url, args.timeout)
    
    try:
        client.health()
    except requests.exceptions.ConnectionError:
        print(f"❌ Could not connect to {args.url}")
        sys.exit(1)
    
    print(f"🔍 Reviewing {args.repo}#{args.pr_number} (dry_run={args.dry_run})...")
    try:
        result = client.review(args.repo, args.pr_number, args.dry_run)
        print(f"\n🤖 Review:\n{result['review']}")
        print(f"\n📊 Steps taken: {result['steps_taken']}")
    except requests.exceptions.HTTPError as e:
        print(f"❌ HTTP error: {e}\n   {e.response.text}")
        sys.exit(1)


if __name__ == "__main__":
    main()
