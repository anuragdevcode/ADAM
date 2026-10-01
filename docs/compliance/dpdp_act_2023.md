# Digital Personal Data Protection Act (DPDP Act 2023) Alignment

**Legislation:** Digital Personal Data Protection Act, 2023 (Act No. 22 of 2023)  
**Target Jurisdiction:** Uttarakhand State Public Records & Citizen Intelligence  
**Version:** 1.0.0 (October 2026)  

---

## 1. Statutory Roles & Applicability

Under Section 2 of the DPDP Act 2023:
- **Data Fiduciary:** Department of Information Technology / Administrative Reforms, Government of Uttarakhand.
- **Data Processor:** ADAM Software Platform & State Data Centre infrastructure.
- **Data Principal:** Citizens and departmental officers whose personal data may appear in public orders or query contexts.

---

## 2. Technical Alignment Matrix

| DPDP Section | Legal Requirement | ADAM Technical Implementation |
| :--- | :--- | :--- |
| **Sec. 4(1)** | Lawful Grounds for Processing | Processes exclusively official public gazettes, authorized departmental orders, and state policies uploaded by verified records officers. |
| **Sec. 6** | Purpose Limitation & Consent | Query memory sessions are scoped strictly to the authenticated user's session context; preferences require explicit opt-in (`adam memory set-preference --opt-in`). |
| **Sec. 8(5)** | Reasonable Security Safeguards | Multi-layer defense: PBKDF2/bcrypt authentication, role-based ACL pre-filters, AES-GCM-256 session encryption, AST Python sandbox, and SSRF boundary guards. |
| **Sec. 8(7)** | Personal Data Erasure | Cryptographic shredding and statutory retention purges (`adam memory purge-expired`). |
| **Sec. 8(6)** | Breach Notification Auditability | Cryptographically verifiable SHA-256 hash-chained audit logs (`adam audit verify`) provide tamper-evident records of all document access and retrieval queries. |
| **Sec. 12** | Right to Information & Grievance | Audit trails record every query and citation source with exact document IDs, page numbers, and version SHAs for transparent verification. |

---

## 3. PII Redaction Layer

Prior to model inference and vector embedding, document chunks and user prompts pass through the `SecretRedactor` pipeline:
- **Aadhaar Numbers:** 12-digit patterns masked to `[AADHAAR_REDACTED]`
- **PAN Numbers:** 10-character alphanumeric patterns masked to `[PAN_REDACTED]`
- **Bank Account / IFSC:** Financial coordinates masked in public-tier queries
- **Mobile Numbers:** 10-digit Indian MSISDNs masked to `[PHONE_REDACTED]`
