# MAHALO3 — Demo Scenarios

## Setup (All Personas)

1. Start all services (see README.md)
2. Register 3 users at http://localhost:3000/register:
   - `pm@demo.io` / `demo123` / Alice Product / Product Manager
   - `dev@demo.io` / `demo123` / Marcus Chen / Developer
   - `exec@demo.io` / `demo123` / Sarah Executive / Executive
3. For each user, go to Connections and add all 3 integrations:
   - Jira: `http://localhost:5001` / token: `mock-jira-token-12345`
   - Confluence: `http://localhost:5002` / token: `mock-confluence-token-12345`
   - GitHub: `http://localhost:5003` / token: `mock-github-token-12345`

---

## Scenario 1: Product Manager Sprint Planning

**Login as**: pm@demo.io (Product Manager)

### Dashboard View
- Sprint Board shows current sprint stories (PAY-105 to PAY-108)
- Velocity chart shows Sprint 23 velocity: 34 points
- Project status bars show completion across all 5 projects

### Chat Interactions

**Ask**: "What is the status of the payment gateway?"
**Expected**: Agent queries Jira (sprint board, velocity) AND GitHub (open PRs), shows correlated data

**Ask**: "What should we plan for next sprint?"
**Expected**: Agent shows velocity data and suggests stories based on backlog priorities

**Ask**: "What are our PCI compliance requirements?"
**Expected**: Agent searches Confluence, finds PCI DSS compliance doc

**Ask**: "Create a story for implementing PayPal integration"
**Expected**: Agent proposes the action → Click Approve → Story PAY-111 created

---

## Scenario 2: Executive Overview

**Login as**: exec@demo.io (Executive)

### Dashboard View
- Portfolio health shows all 5 projects with green/yellow/red indicators
- Key metrics: stories completed, open PRs, total commits
- Velocity comparison across projects

### Chat Interactions

**Ask**: "Give me the overview of all projects"
**Expected**: Agent queries Jira for all projects, shows high-level status of each

**Ask**: "What are the risks and blockers?"
**Expected**: Agent identifies critical-priority stories that are not done

**Ask**: "How is the authentication service doing?"
**Expected**: Agent shows AUTH project board, sprint info, and related PRs

---

## Scenario 3: Developer Workflow

**Login as**: dev@demo.io (Developer)

### Dashboard View
- My Stories widget shows assigned stories (filtered by developer)
- My PRs widget shows open pull requests
- Recent Commits shows latest activity

### Chat Interactions

**Ask**: "What stories are assigned to me?"
**Expected**: Agent searches Jira for stories assigned to the developer

**Ask**: "Show me the open PRs for the payment service"
**Expected**: Agent queries GitHub for payment-service PRs

**Ask**: "What's the architecture of the payment service?"
**Expected**: Agent searches Confluence for payment service technical design

**Ask**: "Create a branch for story PAY-109"
**Expected**: Agent proposes creating branch `feature/PAY-109-crypto-payments` → Approve → Branch created

---

## Key Demo Points

1. **Multi-system correlation**: One question triggers queries to multiple systems
2. **Propose & Confirm**: Write actions always ask for approval first
3. **Role-specific dashboards**: Each persona sees relevant widgets
4. **Persona-aware responses**: Agent frames responses differently per role
5. **Systems queried badges**: Shows which systems were consulted
6. **Live mock data**: Rich e-commerce scenario with realistic stories, docs, PRs
