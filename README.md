# kongctl-steward

An autonomous GitHub agent that maintains issue quality for the [kongctl](https://github.com/Kong/kongctl) project through intelligent triage, labeling, and contextual enrichment.

## Executive Summary

kongctl-steward reduces maintainer toil by ensuring issues are clear, properly categorized, and enriched with implementation context. The agent runs on a scheduled basis to process new and updated issues, enabling maintainers to focus on prioritization and development rather than repetitive triage tasks.

## Goals & Success Metrics

### Primary Goals

- **Reduce triage toil**: Maintainers spend <10 minutes/day on issue triage
- **Improve issue quality**: 90% of issues have sufficient context for implementation within 24 hours
- **Prevent redundancy**: Duplicate issues identified and linked within 1 day
- **Enrich context**: Implementation-relevant details added to 75% of issues

### Success Metrics

- Time from issue creation to “ready for implementation” state
- Percentage of issues requiring maintainer clarification
- Duplicate detection accuracy
- Maintainer satisfaction (qualitative)

### Explicit Non-Goals

- Code modification or PR creation
- Closing issues automatically
- Removing labels or undoing user actions
- Assigning issues to specific people
- Providing support responses to users
- Acting as a chatbot or conversational assistant
- Real-time/immediate response to issues (scheduled execution is sufficient)

## Functional Requirements

### Core Capabilities (MVP)

#### Issue Classification & Labeling

- Add appropriate labels based on issue content
- Never remove existing labels (preserve user actions)
- Categories: `bug`, `feature`, `documentation`, `question`, `configuration`
- Only act with >80% confidence

#### Duplicate Detection

- Identify potential duplicates with >85% confidence
- Add comment linking to related issues
- Add `potential-duplicate` label for maintainer review
- Cross-reference historical issues via semantic search
- Full context of previous comments prevents re-mentioning known duplicates

#### Context Enrichment

- Add code location references (files, functions)
- Reference relevant documentation sections
- Link to related features or past decisions
- Identify relevant library/dependency context
- Agent self-awareness ensures only new, valuable information is added

#### Information Gathering

- Request clarification when critical information is missing
- Use turn-based conversation to gather details
- Stop requesting after 2 attempts to avoid annoyance
- Track conversation state between scheduled runs
- Full context of previous comments prevents repetitive requests
- Won't re-request clarification if user hasn't responded

### Enhanced Capabilities (Phase 2)

- Cross-reference Kong Gateway issues mentioning kongctl
- Identify implementation patterns from similar resolved issues
- Suggest implementation approach (as optional guidance)
- Learn from issue resolutions to improve future suggestions

### Prohibited Actions

- Closing issues
- Removing or modifying user-provided content
- Making promises or commitments about fixes
- Providing specific timeline estimates
- Engaging in extended conversation beyond clarification
- Removing or changing existing labels

## Technical Architecture

### High-Level Components

```
Scheduler (cron/GitHub Actions)
    ↓
Agent Script Execution
    ↓
Issue Fetcher → Decision Engine → Action Executor
                      ↓              ↓
                 Vector DB      LLM Provider
                 (Knowledge)    (Reasoning)
                      ↓              ↓
                 State File    GitHub API
                 (Tracking)     (Actions)
```

### Key Technical Decisions

**Decided:**

- **Scheduled execution** (polling) every 4 hours via cron/scheduler
- **Stateless processing** with state file for tracking processed issues
- **Vector database** for knowledge persistence and semantic search
- **Separate concerns**: retrieval (vector DB) vs reasoning (LLM)
- **Agent self-awareness**: LLM receives context of its previous comments to prevent repetition
- **Event-driven processing NOT required** due to relaxed SLA requirements

**Flexible Implementation Choices:**

- Execution platform (GitHub Actions preferred for zero infrastructure)
- Specific LLM provider (Claude/GPT-4/open source)
- Vector database choice (Chroma for simplicity, Pinecone for scale)
- Programming language (Python likely but not mandated)
- Webhook support can be added later if requirements change

### Execution Strategies

#### Option 1: GitHub Actions (Recommended for MVP)

```yaml
# Free, zero infrastructure, simple
schedule:
  - cron: '0 */4 * * *'  # Every 4 hours
```

- **Cost**: $0
- **Complexity**: Minimal
- **Limitations**: 6-hour max runtime, runs in public Actions tab

#### Option 2: Fly.io Machines

```toml
# Scales to zero, more control
auto_stop_machines = true
auto_start_machines = false
```

- **Cost**: ~$1-2/month
- **Benefits**: Private execution, persistent storage
- **Complexity**: Moderate

#### Option 3: AWS Lambda + EventBridge

- **Cost**: ~$0.10/month
- **Benefits**: Serverless, highly scalable
- **Complexity**: Higher (AWS knowledge required)

## Knowledge Requirements

### Essential Knowledge Domains

#### Project Knowledge

- KongCTL codebase structure and patterns
- Current implementation status and roadmap
- Historical issues and resolutions (all issues in vector DB)
- Coding conventions and standards
- Common issue patterns and their resolutions

#### Kong Ecosystem

- Kong Konnect API documentation
- Kong Gateway concepts and terminology
- Common configuration patterns
- Authentication and authorization models
- Plugin architecture and patterns

#### Technical Context

- Go language patterns and idioms
- Key libraries (Kong/go-kong, cobra, viper)
- CLI design patterns
- Common error patterns and solutions
- GitHub API usage patterns

### Knowledge Maintenance

- **Initial load**: All existing issues, code documentation, Kong docs
- **Continuous learning**: New issues and resolutions added each run
- **Periodic refresh**: Documentation updates monthly
- **State tracking**: Processed issue IDs stored to prevent reprocessing
- **Vector DB growth**: No pruning initially (revisit at 10k documents)

## Operational Constraints

### Resource Boundaries

- **Budget**: Optimize for <$50/month total (likely <$10/month achievable)
- **Scale**: Support up to 10 issues/day
- **Response time**: Within 8 hours acceptable (4-hour schedule provides this)
- **Availability**: Best effort, no formal SLA
- **Runtime**: Each execution should complete within 30 minutes

### Safety & Control

- **Manual kill switch**: Stop scheduled runs or terminate process
- **Confidence thresholds**: Only act when >80% confident
- **Daily action limits**: Max 20 automated actions/day
- **Audit logging**: All decisions and actions logged for review
- **Dry-run mode**: Ability to run without taking actions for testing

### Cost Management

```python
# Example cost controls
MAX_LLM_CALLS_PER_RUN = 50
MAX_COST_PER_RUN = 1.00  # dollars
MAX_MONTHLY_COST = 30.00
```

## Implementation Phases

### Phase 1: Read-Only Observer (Weeks 1-2)

- Set up scheduled execution (GitHub Actions recommended)
- Fetch and analyze issues without taking action
- Log proposed actions to file/stdout for validation
- Build initial knowledge base from historical issues
- **Success criteria**: 80% accurate label suggestions in dry-run

### Phase 2: Conservative Actor (Weeks 3-6)

- Enable label addition (high confidence only)
- Add clarification comments for unclear issues
- Link obvious duplicates
- Implement state tracking to avoid reprocessing
- **Success criteria**: <5% incorrect actions

### Phase 3: Context Enricher (Weeks 7-10)

- Add implementation hints with code references
- Reference specific code locations
- Provide documentation links
- Learn from resolved issues
- **Success criteria**: Maintainer reports reduced investigation time

### Phase 4: Knowledge Builder (Ongoing)

- Continuously learn from resolved issues
- Identify patterns in resolutions
- Improve suggestion quality over time
- Optimize token usage and costs
- **Success criteria**: Increasing accuracy metrics

## State Management

### Tracking Processed Issues

```python
# Simple state management for polling approach
{
  "last_run": "2024-01-15T10:00:00Z",
  "processed_issues": [1234, 1235, 1236],
  "conversation_state": {
    "issue_1234": {
      "awaiting_response": true,
      "attempts": 1,
      "last_comment": "2024-01-15T09:00:00Z"
    }
  }
}
```

### Preventing Duplicate Processing

- Check state file for previously processed issue IDs
- Only process issues created/updated since last run
- Maintain conversation state for multi-turn interactions
- Rotate processed issue list to prevent unbounded growth
- Fetch and provide agent's previous comments to LLM for context
- Prevent repetitive comments through LLM-powered decision making

## Monitoring & Evaluation

### Key Metrics

- Actions taken per run
- Issues processed per run
- Confidence distribution of decisions
- User response rate to clarification requests
- False positive rate (incorrect labels/duplicates)
- Cost per run (LLM tokens + API calls)
- Execution time per run

### Review Cadence

- **Daily**: Check execution logs for errors
- **Weekly**: Review agent actions and accuracy
- **Monthly**: Assess value and adjust thresholds
- **Quarterly**: Evaluate expansion opportunities

### Logging Strategy

```python
# Structured logging for analysis
{
  "run_id": "2024-01-15-1000",
  "issues_processed": 5,
  "actions_taken": [
    {"issue": 1234, "action": "add_label", "label": "bug", "confidence": 0.92},
    {"issue": 1235, "action": "request_info", "confidence": 0.85}
  ],
  "costs": {"llm_tokens": 5000, "estimated_cost": 0.05},
  "duration_seconds": 45
}
```

## Future Evolution Opportunities

**Potential Expansions** (not committed):

- Add webhook support for faster response times
- Monitor merged PRs to auto-resolve related issues
- File issues for technical debt or deprecations
- Expand to other Kong repositories
- Generate implementation sketches or templates
- Create weekly summary reports for maintainers

**Sunset Conditions**:

- GitHub native features obviate the need
- Maintenance burden exceeds value
- Issue volume drops below threshold (< 1 issue/week)
- Team prefers manual triage
- Costs exceed budget significantly

## Open Questions for Implementation

1. **Embedding model selection**: Balance cost vs quality (ada-002 vs text-embedding-3-small)
1. **Duplicate threshold**: What similarity score constitutes “duplicate” (0.85? 0.90?)
1. **Comment frequency**: How often to re-engage on stale issues needing info
1. **Label taxonomy**: Finalize exact label set to use
1. **Confidence calibration**: Determine thresholds through testing
1. **State storage**: Local file vs Redis vs database
1. **Vector DB deployment**: Embedded (Chroma) vs managed (Pinecone)

## Implementation Notes

The implementor should focus on:

1. **Incremental value**: Each phase should provide standalone value
1. **Observability**: Make agent decisions transparent and auditable
1. **Reversibility**: All actions should be manually reversible
1. **Cost control**: Implement spending limits and alerts from day one
1. **Graceful degradation**: Agent should fail quietly, not disruptively
1. **Simple infrastructure**: Prefer zero-infrastructure solutions initially

## Example Agent Actions

### Example 1: Clear Bug Report

```yaml
Issue: "kongctl login fails with 401 error"
Agent Actions:
  - Add labels: [bug, authentication]
  - Add comment: "Related code: /cmd/login.go:performLogin(). 
                 This may be related to issue #23 which addressed token refresh.
                 The error suggests an authentication token issue - possibly expired 
                 or malformed credentials."
```

### Example 2: Vague Feature Request

```yaml
Issue: "Make it work better"
Agent Actions:
  - Add label: [needs-information]
  - Add comment: "Could you provide more details about what specific 
                 functionality you'd like to see improved? For example:
                 - Which commands are you using?
                 - What behavior did you expect?
                 - What actually happened?"
```

### Example 3: Duplicate Issue

```yaml
Issue: "Can't login to Konnect"
Agent Actions:
  - Add label: [potential-duplicate]
  - Add comment: "This appears related to issue #45 which reports similar 
                 authentication problems. That issue includes a workaround
                 and is being tracked for the next release."
```

### Example 4: Implementation Guidance

```yaml
Issue: "Add --output json flag to all commands"
Agent Actions:
  - Add labels: [feature, enhancement]
  - Add comment: "Implementation context:
                 - Output formatting is handled in /internal/output/formatter.go
                 - Commands use cobra framework - flags are defined in each cmd/*.go file
                 - Existing pattern in 'get' command at /cmd/get.go:L45
                 - Would need to modify all command files to add persistent flag"
```

## Getting Started

### Prerequisites

- GitHub token with repo/issue permissions
- LLM API credentials (Anthropic/OpenAI)
- Python 3.9+ (or chosen runtime)
- Optional: Vector database instance

### Quick Start (GitHub Actions)

```bash
# Fork/clone the repository
git clone https://github.com/rspurgeon/kongctl-steward
cd kongctl-steward

# Add secrets to your GitHub repo:
# - ANTHROPIC_API_KEY
# - GH_TOKEN (if not using GITHUB_TOKEN)

# Create workflow file
mkdir -p .github/workflows
cp examples/steward-workflow.yml .github/workflows/

# The agent will run automatically on schedule
```

### Quick Start (Local Development)

```bash
# Clone and setup
git clone https://github.com/rspurgeon/kongctl-steward
cd kongctl-steward

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys

# Initialize knowledge base
python scripts/init_knowledge.py

# Run the agent
python steward.py --dry-run  # Test mode first
python steward.py             # Live mode
```

### Configuration

```python
# config.py example
SCHEDULE_HOURS = 4  # Run every 4 hours
CONFIDENCE_THRESHOLD = 0.80
MAX_ISSUES_PER_RUN = 20
MAX_LLM_COST_PER_RUN = 1.00
DRY_RUN = False  # Set True for testing
```

## License

[TBD - Suggest Apache 2.0 or MIT to match Kong’s licensing]

## Contributing

This project is currently in early development. Contribution guidelines will be established once the core functionality is implemented.

## Acknowledgments

Built to support the [Kong/kongctl](https://github.com/Kong/kongctl) project and the Kong community.