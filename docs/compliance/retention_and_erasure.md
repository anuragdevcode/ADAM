# Statutory Retention & Cryptographic Erasure Policy

**Target Entity:** Government of Uttarakhand / Administrative Reforms  
**Classification:** OFFICIAL / STATUTORY COMPLIANCE  
**Version:** 1.0.0 (October 2026)  

---

## 1. Document Lifecycle & Retention Schedules

In accordance with the Uttarakhand Secretariat Manual of Office Procedure and Public Records Rules, records ingested into ADAM adhere to statutory retention schedules:

| Record Category | Controlled Vocabulary | Statutory Retention Period | Disposition Action |
| :--- | :--- | :--- | :--- |
| **Gazette Notifications** | `UK/GAZETTE` | Permanent (`PERMANENT`) | Preserved indefinitely; immutable |
| **Financial Sanctions & GOs** | `UK/FIN` | 35 Years (`LONG_TERM`) | Archived after audit clearance |
| **Administrative Circulars** | `UK/GAD` | 10 Years (`STANDARD`) | Periodic review for supersession |
| **Draft / Review Pages** | Internal Review Queue | 1 Year (`TEMPORARY`) | Auto-purged upon official publication |
| **Session Turns & Queries** | User Chat History | 90 Days (Configurable) | Cryptographic erasure / key rotation |

---

## 2. Cryptographic Erasure (Crypto-Shredding)

When citizen or officer data requires erasure under statutory obligations or right-to-erasure requests:

1. **Session Memory Encryption:** Every conversation turn and summary is encrypted at rest using AES-GCM-256 with key versioning (`MEMORY_ENCRYPTION_KEY`).
2. **Key Rotation & Deletion:** Deleting a user's session cryptographic key renders all associated ciphertext permanently undecryptable across all backup media, completing verifiable cryptographic erasure without requiring physical media destruction.
3. **Database Purge:** The `adam memory purge-expired` CLI command purges expired session records from PostgreSQL and vacuums affected tables:
   ```bash
   adam memory purge-expired
   ```
4. **Audit Immutability:** Audit trail records documenting the erasure action are preserved in the hash chain with actor ID, timestamp, and authorization reference.
