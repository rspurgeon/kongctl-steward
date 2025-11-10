# kongctl-steward

An autonomous GitHub agent that maintains issue quality for the [kongctl](https://github.com/Kong/kongctl) 
project through intelligent triage, labeling, and contextual enrichment.

## Executive Summary

kongctl-steward reduces maintainer toil by ensuring issues are clear, properly categorized, 
and enriched with implementation context. This enables maintainers to focus on prioritization and 
development rather than repetitive triage tasks.

## Goals & Success Metrics

### Primary Goals
- **Reduce triage toil**: Reduce time spent by maintainers on issue triage
- **Improve issue quality**: Issues have sufficient context for implementation and improve over time
- **Prevent redundancy**: Duplicate issues identified and linked asap
- **Enrich context**: Implementation-relevant details added to majority of issues

### Explicit Non-Goals
- Code modification or PR creation
- Closing issues automatically
- Removing labels or undoing user actions
- Assigning issues to specific people
- Providing support responses to users
- Acting as a chatbot or conversational assistant

## Functional Requirements

### Core Capabilities (MVP)

#### Issue Classification & Labeling
- Add appropriate labels based on issue content
- Never remove existing labels
- Categories: `bug`, `feature`, `documentation`, `question`, `configuration`

#### Duplicate Detection
- Identify potential duplicates with >85% confidence
- Add comment linking to related issues
- Add `potential-duplicate` label for maintainer review

#### Context Enrichment
- Add code location references (files, functions)
- Reference relevant documentation sections
- Link to related features or past decisions

#### Information Gathering
- Request clarification when critical information is missing
- Use turn-based conversation to gather details
- Stop requesting after 2 attempts to avoid annoyance

### Enhanced Capabilities (Phase 2)
- Identify implementation patterns from similar resolved issues
- Suggest implementation approach (as optional guidance)

### Prohibited Actions
- Closing issues
- Removing or modifying user-provided content
- Making promises or commitments about fixes
- Providing specific timeline estimates
- Engaging in extended conversation beyond clarification

## Technical Architecture

### High-Level Components
```
GitHub Webhook → Agent Service → Decision Engine → Action Executor
                       ↓              ↓
                  Vector DB     LLM Provider
                  (Knowledge)   (Reasoning)
```

### Key Technical Decisions

### Key Technical Decisions

**Decided:**
- Scheduled execution (polling) every 4 hours via cron/scheduler
- Stateless processing with state file for tracking processed issues
- Vector database for knowledge persistence  
- Separate concerns: retrieval (vector DB) vs reasoning (LLM)

**Flexible Implementation Choices:**
- Execution platform (GitHub Actions/Fly.io/Lambda)
- Webhook support can be added later if needed
- Specific LLM provider (Claude/GPT-4)
- Vector database choice (Chroma/Qdrant/Pinecone)

## Knowledge Requirements

### Essential Knowledge Domains

#### Project Knowledge
- KongCTL codebase structure and patterns
- Current implementation status and roadmap
- Historical issues and resolutions
- Coding conventions and standards

#### kongctl Ecosystem
- Kong Konnect API documentation
- sdk-konnect-go SDK library
- Kong Gateway concepts and terminology
- Declarative configuration patterns
- Authentication and authorization models

#### Technical Context
- Go language patterns and idioms
- Key libraries (Kong/sdk-konnect-go, cobra, viper)
- CLI design patterns
- Common error patterns and solutions

### Knowledge Maintenance
- Initial load: All existing issues, code documentation, Kong docs
- Continuous learning: New issues and resolutions added automatically
- Periodic refresh: Documentation updates monthly
- No automatic pruning initially (revisit at 10k documents)

## Operational Constraints

### Resource Boundaries
- **Budget**: Flexible but optimize for <$50/month initially
- **Scale**: Support up to 10 issues/day
- **Response time**: Within 8 hours acceptable
- **Availability**: Best effort, no formal SLA

### Safety & Control
- Manual kill switch (process termination)
- Confidence thresholds: Only act when >80% confident
- Daily action limits: Max 20 automated actions/day
- Audit log: All actions logged for review

## Implementation Phases

### Phase 1: Read-Only Observer 
- Analyze issues without taking action
- Log proposed actions for validation
- Build initial knowledge base
- **Success criteria**: 80% accurate label suggestions

### Phase 2: Conservative Actor
- Enable label addition (high confidence only)
- Add clarification comments for unclear issues
- Link obvious duplicates
- **Success criteria**: <5% incorrect actions

### Phase 3: Context Enricher 
- Add implementation hints
- Reference code locations
- Provide documentation links
- **Success criteria**: Maintainer reports reduced investigation time

### Phase 4: Knowledge Builder
- Learn from resolved issues
- Identify patterns in resolutions
- Improve suggestion quality
- **Success criteria**: Increasing accuracy over time

## Monitoring & Evaluation

### Key Metrics
- Actions taken per day
- Confidence distribution of decisions
- User response rate to clarification requests
- False positive rate (incorrect labels/duplicates)

### Review Cadence
- Weekly: Review agent actions and accuracy
- Monthly: Assess value and adjust thresholds
- Quarterly: Evaluate expansion opportunities

## Future Evolution Opportunities

**Potential Expansions** (not committed):
- Monitor merged PRs to auto-resolve related issues
- Use Webhooks for real-time processing
- File issues for technical debt or deprecations
- Expand to other Kong repositories
- Generate implementation sketches or templates

**Sunset Conditions**:
- GitHub native features obviate the need
- Maintenance burden exceeds value
- Issue volume drops below threshold
- Team prefers manual triage

## Open Questions for Implementation

1. **Embedding model selection**: Balance cost vs quality
2. **Duplicate threshold**: What similarity score constitutes "duplicate"?
3. **Comment frequency**: How often to re-engage on stale issues?
4. **Label taxonomy**: Finalize exact label set to use
5. **Confidence calibration**: Determine thresholds through testing

## Implementation Notes

The implementor should focus on:
1. **Incremental value**: Each phase should provide standalone value
2. **Observability**: Make agent decisions transparent and auditable
3. **Reversibility**: All actions should be manually reversible
4. **Cost control**: Implement spending limits and alerts
5. **Graceful degradation**: Agent should fail quietly, not disruptively

## Example Agent Actions

### Example 1: Clear Bug Report
```yaml
Issue: "kongctl login fails with 401 error"
Agent Actions:
  - Add labels: [bug, authentication]
  - Add comment: "Related code: /cmd/login.go:performLogin(). 
                 This may be related to issue #23 which addressed token refresh."
```

### Example 2: Vague Feature Request
```yaml
Issue: "Make it work better"
Agent Actions:
  - Add label: [needs-information]
  - Add comment: "Could you provide more details about what specific 
                 functionality you'd like to see improved?"
```

### Example 3: Duplicate Issue
```yaml
Issue: "Can't login to Konnect"
Agent Actions:
  - Add label: [potential-duplicate]
  - Add comment: "This appears related to issue #45. 
                 See that issue for ongoing discussion and workarounds."
```

## Getting Started

### Prerequisites
- GitHub OAuth App or GitHub App configured
- Vector database instance
- LLM API credentials

### Quick Start
```bash
# Clone the repository
git clone https://github.com/rspurgeon/kongctl-steward
cd kongctl-steward

# Install dependencies (implementation-dependent)
# Configure environment variables
# Initialize knowledge base
```

### Configuration
See `config/` directory for configuration templates and environment variable documentation.

## License

[TBD - Suggest Apache 2.0 or MIT to match Kong's licensing]

## Contributing

This project is currently in early development. Contribution guidelines will be established once the core functionality is implemented.

## Acknowledgments

Built to support the [Kong/kongctl](https://github.com/Kong/kongctl) project and the Kong community.
