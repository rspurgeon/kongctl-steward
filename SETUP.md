# Setup Instructions

## Prerequisites

- Python 3.9 or higher
- GitHub account with a test repository
- API credentials for Anthropic or OpenAI

## Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/rspurgeon/kongctl-steward
   cd kongctl-steward
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

## Configuration

### Required Environment Variables

- `GITHUB_TOKEN`: GitHub personal access token with `repo` scope
- `GITHUB_REPO`: Target repository (e.g., `owner/repo-name`)
- `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`: LLM provider API key

### Creating a GitHub Token

1. Go to GitHub Settings → Developer settings → Personal access tokens
2. Generate new token (classic)
3. Select scopes: `repo` (full control of private repositories)
4. Copy token to `.env` file

### Creating a Test Repository

1. Create a new GitHub repository (can be private)
2. Add a few test issues with different types:
   - Bug report
   - Feature request
   - Question
   - Duplicate issue
3. Use this as `GITHUB_REPO` in your `.env`

## Running the Agent

### Dry-run Mode (Recommended First)

```bash
python steward.py --dry-run
```

This will:
- Fetch issues from your test repository
- Analyze and classify them
- Log proposed actions (no actual changes)
- Build the knowledge base

### Live Mode

```bash
# Set DRY_RUN=false in .env first
python steward.py
```

## Project Structure

```
kongctl-steward/
├── src/                  # Source code
│   ├── config.py        # Configuration management
│   ├── llm/             # LLM provider plugins
│   ├── github_client/   # GitHub API integration
│   ├── vector_store/    # Vector database
│   ├── analyzer/        # Issue analysis logic
│   └── state/           # State management
├── scripts/             # Utility scripts
├── state/               # Runtime state (git-ignored)
├── logs/                # Log files (git-ignored)
├── chroma_db/           # Vector database (git-ignored)
├── examples/            # Example configurations
├── .env.example         # Environment template
└── steward.py          # Main entry point
```

## Next Steps

1. Verify configuration: `python -c "from src.config import load_config; load_config()"`
2. Run in dry-run mode on test repository
3. Review logs in `logs/steward.log`
4. Adjust confidence thresholds as needed
5. Enable live mode when comfortable
