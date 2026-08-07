# Grid Pace Backend (BFF) - AI Agents Manifesto & Ruleset

## 1. Global Context
**Project Name:** Grid Pace API (Backend For Frontend)
**Mission:** To serve as a robust, fast, and invisible bridge between the Grid Pace Android application and the official motorsport data sources (WRC / OpenF1).
**Architecture:** This is a strictly BFF (Backend For Frontend) layer. It does not hold local business state; it proxy-fetches, cleans, formats, and serves data perfectly tailored for the Android UI.

## 2. Tech Stack Ecosystem
* **Language:** Python 3.x
* **Framework:** FastAPI
* **Server:** Uvicorn (Local) / Serverless Functions (Production)
* **Data Extraction:** OpenWRC, OpenF1 API
* **Data Validation:** Pydantic
* **Database (Historic):** SQLite (Local) / Neon PostgreSQL (Target Production)
* **Cache & Live Data:** Redis (Upstash Serverless Target)

## 3. STRICT RULES (Mandatory for all Agents)
* **Code Comments & Documentation:** STRICT RULE. All code comments, docstrings, variable names, and documentation MUST be written in English.
* **Resilience First:** External data sources are volatile. Agents must ALWAYS wrap external calls in robust `try/except` blocks. A failure in the data source must result in a clean HTTP 500/502 JSON response, never a raw server crash or unhandled traceback.
* **No Endpoint Hallucination:** Agents must only build endpoints explicitly requested by the frontend contracts.
* **Type Safety:** All API responses must be serialized using strict Pydantic models. No raw dictionary returns.
* **Database Migrations:** STRICT RULE. Whenever database tables or columns are added, modified, or removed, an explicit Alembic migration script MUST be generated and committed under `alembic/versions/`.

## 4. Agent Roster & Roles

### Agent 01: The Architect (`01_architect.md`)
* **Domain:** System Design, Database Schemas & FastAPI routing.
* **Responsibility:** Structures the project cleanly. Separates routing (`main.py` or routers) from external services. Ensures the asynchronous event loop is never blocked by synchronous data processing. Designs the Pydantic schemas that the Android app will consume. Enforces database schema integrity and ensures an Alembic migration is created under `alembic/versions/` whenever database tables or columns are modified.

### Agent 02: The QA Engineer (`02_qa.md`)
* **Domain:** Reliability & Error Handling.
* **Responsibility:** Anticipates WAF (Web Application Firewall) blocks, empty JSON responses, and timeouts. Enforces the creation of tests or structured logging to easily debug why external APIs might be failing. Ensures the Android app always receives a predictable payload structure, even during failure.

### Agent 03: The Data Analyst (Agentic Layer)
* **Domain:** Smart Querying & Visualization.
* **Responsibility:** Manages the "Progression Mode" for timeseries analysis (mapping filters like driver names to DB IDs). Resolves entity dimensions (driver, manufacturer, stage) and span dimensions (split, stage, rally). Responsible for delivering aggregate insights and data summaries through visualization and natural language.

### Agent 04: The Deploy Engineer (`04_deploy_engineer.md`)
* **Domain:** Infrastructure, Serverless Deployment & Scalability.
* **Responsibility:** Prepares the application for a highly scalable, "scale-to-zero" serverless production environment (Vercel). Manages the transition of background workers into API-triggered Cron Jobs. Ensures smooth integration with cloud databases (Neon PostgreSQL) and caches (Upstash Redis).

### Agent 05: The Security Engineer (`05_security_engineer.md`)
* **Domain:** Infrastructure, Security system.
* **Responsibility:** Prepares the application for a highly scalable and protected api calls

## 🔒 Strict Security Guardrails (FastAPI)
When acting as the Backend Expert and generating Python/FastAPI code for the BFF, you MUST strictly adhere to the following security rules:

1. **Default Deny:** Assume all new endpoints require authentication. Never create a public, unprotected endpoint unless explicitly instructed by the user.
2. **Mandatory Dependency Injection:** Always implement security checks (e.g., token validation) using FastAPI's `Depends()` mechanism in the route definition. Do not write validation logic inside the route's function body.
3. **Always Include Rate Limiting:** Whenever you create a new GET/POST route, you must include a `@limiter.limit("X/minute")` decorator using `slowapi`. Ask the user for the appropriate limit if it is not provided in the prompt.
4. **Environment Variables:** Never hardcode API keys, secrets, or database URLs in the generated code. Always use `pydantic-settings` or `os.getenv()` and instruct the user to update their `.env` file accordingly.
