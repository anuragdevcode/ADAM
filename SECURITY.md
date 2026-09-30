# Security Policy — ADAM (Autonomous Document Acquisition & Management)

## 1. Supported Versions

ADAM is actively developed. Only the current release on the `main` branch receives security updates.

| Version | Supported          |
| ------- | ------------------ |
| `main`  | :white_check_mark: |
| < 0.2.0 | :x:                |

---

## 2. Reporting a Vulnerability

We take the security and integrity of ADAM seriously, especially given its intended use in public sector and government document governance.

If you believe you have found a security vulnerability:

1. **Do not open a public issue or discussion.**
2. Send an email to **security@anuragdevcode.com** (or to the repository maintainer) with:
   - Description of the vulnerability and its potential impact.
   - Exact steps to reproduce, proof of concept, or HTTP request traces.
   - Software versions, operating system, and deployment configuration (`docker-compose`, standalone, etc.).
3. You will receive an acknowledgment within **48 hours**.
4. We will coordinate a remediation and disclosure timeline (target resolution within 14 days for high/critical vulnerabilities).

---

## 3. Security Boundaries & Architecture Guarantees

### Sovereign & Air-Gapped Operation
- **Zero External Egress by Default**: All models (LLMs, OCR, vector embeddings, and speech processing) operate on local, air-gapped infrastructure.
- **Hosted Cloud Voice Opt-In**: Cloud STT/TTS services (e.g. Groq, Gemini) are strictly disabled by default. Outbound voice egress requires explicit affirmative opt-in via `ADAM_ALLOW_HOSTED_VOICE=true`.
- **SSRF Guard**: The web client and ingestion layer resolve DNS, check every redirect hop, and deny private/loopback/reserved IPv4 and IPv6 networks.

### Access Control & Clearance Ceilings
- **Default-Deny Role Enforcement**: Non-public routes require specific roles (`ADMIN`, `OFFICER`, `OPERATOR`, `AUDITOR`). Anonymous or unauthenticated requests are rejected with `403 Forbidden`.
- **Retrieval-Layer ACL Filter**: Security clearance classification (`PUBLIC`, `INTERNAL`, `RESTRICTED`, `CONFIDENTIAL`) is applied inside the database query before candidates are scored or retrieved.
- **Upload Clearance Ceiling**: Users cannot ingest or upload documents classified higher than their own active clearance level.
- **Agent Tools Isolation**: Database queries and source comparison tools apply `AclEnforcer` checks to prevent leaking metadata or titles of restricted records.

### Sandboxing & Code Execution
- **Subprocess Isolation**: Python code execution runs in an isolated spawned child subprocess with strict `RLIMIT_AS` memory ceilings and timeout bounds.
- **No In-Process Fallback**: If the sandbox subprocess fails or is terminated, ADAM fails closed with a sandbox error. It never executes unverified user code within the main API thread.
- **Environment Scrubbing**: Child worker processes receive a scrubbed environment stripped of all API keys, database credentials, and signing secrets.
- **AST Whitelisting**: Python AST inspection blocks dunder attribute traversal, `eval`, `exec`, and format-string attribute access escapes.

### Production Secrets
- **Zero Insecure Defaults in Production**: When `ADAM_ENV=production`, the application refuses to start if `SIGNING_SECRET` or database passwords match known development placeholders.

---

## 4. Responsible Disclosure Guidelines

When conducting security research against ADAM:
- Avoid actions that cause disruption of service, denial of service, or destruction of test data.
- Please test vulnerabilities against local standalone deployments (`docker-compose.prod.yml` or native tests) rather than production systems.
