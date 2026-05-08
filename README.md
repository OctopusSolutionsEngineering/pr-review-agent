# PR Review Agent 🤖

An AI agent that automatically reviews GitHub pull requests using LLMs.

## Features

- 🔍 Fetches PR metadata, diffs, and file contents
- 🧠 Uses GPT-4o for intelligent code analysis
- 💬 Posts structured review comments back to GitHub
- 🪝 Webhook integration for automatic reviews on PR events
- 🔒 HMAC signature verification for webhook security

## Setup

### 1. Get a GitHub Token

Create a [Personal Access Token](https://github.com/settings/tokens) with `repo` scope.
For production, use a [GitHub App](https://docs.github.com/en/apps) instead.

### 2. Configure Environment

```bash
cp .env.example .env
# Add your OPENAI_API_KEY and GITHUB_TOKEN
```

### 3. Run Locally

```bash
pip install -r requirements.txt
uvicorn api:app --reload
```

### 4. Or Run with Docker

```bash
docker build -t pr-review-agent .
docker run -p 8000:8000 --env-file .env pr-review-agent
```

## Usage

### Manual Trigger

```bash
curl -X POST http://localhost:8000/review \
  -H "Content-Type: application/json" \
  -d '{"repo": "octocat/hello-world", "pr_number": 42}'
```

### Dry Run (No Posting)

```bash
curl -X POST http://localhost:8000/review \
  -H "Content-Type: application/json" \
  -d '{"repo": "octocat/hello-world", "pr_number": 42, "dry_run": true}'
```

### GitHub Webhook

1. Deploy to a public URL (Render, Fly.io, ngrok for testing)
2. In your repo: **Settings → Webhooks → Add webhook**
   - Payload URL: `https://your-domain.com/webhook`
   - Content type: `application/json`
   - Secret: same as `GITHUB_WEBHOOK_SECRET`
   - Events: **Pull requests**
3. PRs will now get reviewed automatically on `opened`/`synchronize`/`reopened`

## How It Works

```
GitHub PR event
      ↓
   Webhook → /webhook (verifies HMAC signature)
      ↓
  Background task → reviewer.review_pr()
      ↓
   LangChain Agent (GPT-4o)
      ↓
   Tools: get_pr_metadata, get_pr_diff, list_changed_files,
          get_file_content, post_review_comment, post_inline_comment
      ↓
   Review posted on GitHub ✅
```
