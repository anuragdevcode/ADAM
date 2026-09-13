# Merge — Final Integration and Verification Plan

## Preconditions

All module acceptance criteria pass; source owners approve pilot collections; security/legal/records owners sign off the applicable controls; model and licence register is complete. No module may substitute inferred metadata for original evidence.

## End-to-end verification sequence

1. Register Treasury/IFMS and one additional approved public collection; verify ownership, permitted URLs, licence/provenance, hashes and refresh plan.
2. Ingest a mixed corpus of born-digital PDFs, Hindi scans, tables, duplicate URLs and a deliberately corrupt file. Confirm quarantine, versioning and page accounting.
3. Review OCR samples. Publish only approved chunks and prove source page/coordinates open from each chunk.
4. Run gold questions covering GO number lookup, procurement rule, Hindi query, date-bound query, amendment/conflict, unknown question and a forbidden/ACL-denied document.
5. Verify every material answer claim has a correct page citation; unknown/high-risk cases abstain or require review; no current-validity claim appears without approved relationship/effective-date evidence.
6. Exercise chat/session expiry, user deletion, microphone consent/transcript correction and screen-reader/keyboard journeys.
7. Run document prompt-injection, ACL, upload/XSS, rate-limit, audit-log and secret-scanning tests.
8. Benchmark the Mac profile (one active model/worker) and representative production deployment. Confirm queue behaviour, p95 targets set by ITDA, restart, backup restore and index/model rollback.

## Release decision table

| Gate | Evidence | Owner |
|---|---|---|
| Source legitimacy | approved registry + immutable originals | records owner |
| Retrieval truthfulness | gold-set and citation report | product/evaluation lead |
| Access safety | RBAC test and security report | security lead |
| Legal/operational fit | use policy, retention and model licence review | authorised legal/governance owner |
| Service readiness | monitoring, restore, capacity/rollback report | operations lead |
| User readiness | officer UAT, accessibility results, training | department lead |

Any critical security issue, ACL leak, evidence-free legal/financial answer, failed restore, unapproved source, or unlicensed model is a **no-go**. Pilot release remains read-only and labelled decision support until formal policy authorises a broader role.
