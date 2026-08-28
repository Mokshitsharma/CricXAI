# CricXAI Documentation

This directory holds the planning and design documents for CricXAI, a
prescriptive cricket strategy platform. Read them in roughly this order.

| Doc | Purpose | Audience |
| --- | --- | --- |
| [PRD.md](PRD.md) | Product requirements — what we are building and why | Everyone |
| [TRD.md](TRD.md) | Technical requirements — how the system must behave | Engineers |
| [ARCHITECTURE.md](ARCHITECTURE.md) | System shape, components, technology choices, ADRs | Engineers |
| [DESIGN.md](DESIGN.md) | Product / UX / visual design language and key screens | Design + frontend |
| [UI_WORKFLOW.md](UI_WORKFLOW.md) | Screen-by-screen flows, states, components | Design + frontend |
| [APP_FLOW.md](APP_FLOW.md) | End-to-end runtime flows and sequence diagrams | Engineers |
| [BACKEND_SCHEMA.md](BACKEND_SCHEMA.md) | Relational schema, tables, indexes, CSV → DB mapping | Backend + data |
| [RULES.md](RULES.md) | Engineering rules and conventions (leakage, parsing, testing) | Engineers |
| [PHASES.md](PHASES.md) | Delivery roadmap, phase gates, exit criteria | Everyone |
| [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) | Concrete task breakdown by sprint | Engineers |
| [MEMORY.md](MEMORY.md) | Living project memory: state, decisions, gotchas, glossary | Everyone / AI agents |

## One-paragraph summary

CricXAI ingests ESPNcricinfo ball-by-ball commentary, parses it into
structured deliveries, and engineers leakage-free features describing the
match situation and each batsman's historical vulnerability. On top of that
data it trains models that, given a live match situation and a batsman,
recommend the delivery (length + line), predict dismissal probability and
type, suggest a field, and explain the recommendation with SHAP. The
recommendation engine is exposed as a FastAPI service and a web console, with
a tiered subscription / metered-API monetization layer.

## Current status (2026-08-28)

Pillar 1 (data collection + feature engineering) is implemented and tested
offline. Everything downstream — models, API, SHAP, UI, billing — is
specified in these docs but not yet built. See [PHASES.md](PHASES.md).
