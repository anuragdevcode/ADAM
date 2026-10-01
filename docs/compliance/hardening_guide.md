# Production Hardening & CIS Benchmark Alignment Guide

**Scope:** Deployment hardening for ADAM containerized services and host nodes  
**Target Entity:** State Data Centre System Administrators  
**Version:** 1.0.0 (October 2026)  

---

## 1. Container & Image Hardening (H6)

1. **Non-Root Execution:** All container services run as an unprivileged service account:
   ```dockerfile
   RUN groupadd --system adam && useradd --system --gid adam --create-home adam
   USER adam
   ```
2. **Minimal Attack Surface:**
   - Production Dockerfile excludes `tests/` directories (`COPY tests ./tests` present only in `development` target).
   - Base image uses Debian slim (`python:3.12-slim`).
   - Package manager caches removed (`rm -rf /var/lib/apt/lists/*`).
3. **Database Port Unpublishing:**
   - Production compose file (`docker-compose.prod.yml`) drops host-mapped ports for PostgreSQL:
     ```yaml
     services:
       postgres:
         ports: !override []
     ```
   - Only `api` and `ui` ingress ports are exposed to reverse proxies.

---

## 2. Environment & Secret Hardening (Phase 0 / S4)

1. **Production Refusal of Default Secrets:**
   In `ADAM_ENV=production`, the application refuses to start if `SIGNING_SECRET`, `POSTGRES_PASSWORD`, or `MEMORY_ENCRYPTION_KEY` match placeholder values:
   ```bash
   # Production refuses to boot with:
   # - "adam-uk-gov-default-auth-secret-key-2026"
   # - "adam_dev_password"
   # - "change-me"
   ```
2. **Key Length & Entropy:**
   - `SIGNING_SECRET`: Minimum 32 random alphanumeric bytes.
   - `MEMORY_ENCRYPTION_KEY`: 256-bit high-entropy secret.

---

## 3. Reverse Proxy & Transport Security (S12)

When deploying behind NGINX, HAProxy, or Envoy in the SDC:

```nginx
# Security Headers
add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-Frame-Options "DENY" always;
add_header Content-Security-Policy "default-src 'self'; script-src 'self'; object-src 'none';" always;

# TLS Configuration
ssl_protocols TLSv1.3 TLSv1.2;
ssl_ciphers ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
ssl_prefer_server_ciphers on;
```

---

## 4. Disaster Recovery & Backup Verification (R6)

Automated backup drills verify integrity and restorability:
```bash
# Verify system readiness and run DR restore drill:
adam backup drill
```
The restore drill creates an isolated database instance, restores the encrypted backup, and confirms table counts, checksums, and vector indexes match the original.
