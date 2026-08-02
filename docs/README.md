# Enterprise AI Platform — Documentation

## Documents

| Document | Purpose | Audience |
|----------|---------|----------|
| [`BUSINESS_PROPOSAL.md`](BUSINESS_PROPOSAL.md) | Business proposal, competitive analysis, pricing | CTO, VP Engineering, Investors |
| [`PRESENTATION.md`](PRESENTATION.md) | 13-slide presentation deck | Clients, partners, board |
| [`TECHNICAL_REFERENCE.md`](TECHNICAL_REFERENCE.md) | Full API reference, deployment guide, operations | Engineers, DevOps, Architects |
| [`../Enterprise_Validation/VALIDATION_REPORT.md`](../Enterprise_Validation/VALIDATION_REPORT.md) | Math-backed certification report | Auditors, Compliance |
| [`../STATUS_ENTERPRISE.md`](../STATUS_ENTERPRISE.md) | Module-by-module test pass/fail board | Engineering, QA |

## Quick Links

- **Platform root**: `/home/hunter/Desktop/Eni Builder/enterprise/`
- **API Gateway**: `http://localhost:8421`
- **Swarm Dashboard**: `http://localhost:8420`
- **Agent Server**: `http://localhost:9120`
- **Swarm Turbocharger**: `http://localhost:8922/health`
- **Free Model Router**: `http://localhost:8920/health`

## Platform at a Glance

```
28 Components · 3,164 Tests · 100% Pass Rate · 141,683 Lines
20 OS Modules · 8 Foundation Subsystems · 71 API Endpoints
Up to 80 Concurrent AI Agents · 25+ Model Providers
Production-Ready Safety · Self-Healing Infrastructure
```

## Build Commands

```bash
# Run all tests
cd /home/hunter/Desktop/Eni\ Builder
python3 -m pytest enterprise/ -q -p no:anyio

# Start platform
python3 -m uvicorn enterprise.integration.api_gateway:app --host 0.0.0.0 --port 8421

# Docker deployment
docker-compose up -d
```