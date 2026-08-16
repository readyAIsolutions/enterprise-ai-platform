# Compliance Checklist for SaaS Production Hardening

## Regulatory Requirements by Jurisdiction

### GDPR (EU) - General Data Protection Regulation
| Requirement | Implementation | Status |
|-------------|----------------|--------|
| Lawful basis for processing | Consent + Legitimate Interest assessments | ☐ |
| Data Protection Impact Assessment (DPIA) | Per workflow, before launch | ☐ |
| Records of Processing Activities (ROPA) | Automated registry | ☐ |
| Data Subject Access Request (DSAR) portal | Self-service + API | ☐ |
| Right to Erasure (R2E) | Automated cascade delete | ☐ |
| Data Portability | JSON/CSV export | ☐ |
| Consent receipts | Timestamped, versioned | ☐ |
| Legitimate Interest Assessments (LIA) | Documented per purpose | ☐ |
| Vendor DPAs | Fonoster, useSend, Odoo, OpenRouter | ☐ |
| Cross-border transfers | SCCs + adequacy decisions | ☐ |
| Retention policies | Automated deletion schedules | ☐ |
| Breach notification | 72hr workflow | ☐ |
| Data Protection Officer (DPO) | Designated contact | ☐ |

### CCPA/CPRA (California) - Consumer Privacy Rights
| Requirement | Implementation | Status |
|-------------|----------------|--------|
| Consumer rights portal | Know, Delete, Opt-out, Portability | ☐ |
| Opt-out API | Global privacy control (GPC) | ☐ |
| Do Not Sell/Share | Automated suppression | ☐ |
| Data inventory | What/where/why collected | ☐ |
| Third-party contracts | Service provider addendums | ☐ |
| Verification process | Identity proof for requests | ☐ |
| Non-discrimination | Equal service/pricing | ☐ |
| Children's data | Opt-in for <16 | ☐ |

### TCPA (US) - Telephone Consumer Protection Act
| Requirement | Implementation | Status |
|-------------|----------------|--------|
| DNC list scrubbing | FTC + State lists, real-time | ☐ |
| Prior express written consent | Documented, timestamped | ☐ |
| Timezone-aware windows | Per-jurisdiction (8am-9pm local) | ☐ |
| ATDS avoidance | Human-simulated dialing patterns | ☐ |
| Recording announcements | Auto-injected per call | ☐ |
| Call recording retention | Configurable + auto-delete | ☐ |
| STIR/SHAKEN attestation | Carrier integration | ☐ |
| Brand registration | A2P 10DLC, Toll-Free | ☐ |
| Revocation handling | Immediate suppression | ☐ |

### CAN-SPAM (US) - Commercial Email
| Requirement | Implementation | Status |
|-------------|----------------|--------|
| Unsubscribe headers | List-Unsubscribe, List-Unsubscribe-Post | ☐ |
| Physical address | In every email footer | ☐ |
| Opt-out processing | <10 business days | ☐ |
| No misleading headers | Accurate From/Reply-To | ☐ |
| Subject line accuracy | No deceptive subjects | ☐ |
| Identification as ad | Clear commercial marking | ☐ |
| Monitoring affiliates | Vendor compliance | ☐ |

### CASL (Canada) - Anti-Spam Legislation
| Requirement | Implementation | Status |
|-------------|----------------|--------|
| Express consent | Explicit opt-in, documented | ☐ |
| Implied consent expiry | 24 months (purchase), 6 months (inquiry) | ☐ |
| Unsubscribe mechanism | Functional, 10 business days | ☐ |
| Sender identification | Name, address, contact | ☐ |
| Consent records | Timestamp, method, purpose | ☐ |

### ePrivacy/PECR (UK/EU) - Electronic Communications
| Requirement | Implementation | Status |
|-------------|----------------|--------|
| Cookie consent | Granular, prior consent | ☐ |
| Electronic marketing consent | Opt-in for email/SMS | ☐ |
| Traffic data | Minimization, security | ☐ |
| Location data | Explicit consent | ☐ |
| Directory listings | Opt-out | ☐ |

## Industry-Specific (If Applicable)

### HIPAA (Healthcare) - If Processing PHI
| Requirement | Status |
|-------------|--------|
| Business Associate Agreement (BAA) | ☐ |
| Encryption at rest (AES-256) | ☐ |
| Encryption in transit (TLS 1.2+) | ☐ |
| Access controls (unique IDs, emergency access) | ☐ |
| Audit logs (6 years) | ☐ |
| Integrity controls | ☐ |
| Transmission security | ☐ |
| Workforce training | ☐ |
| Incident response | ☐ |

### SOC 2 Type II (Trust Services)
| Principle | Controls |
|-----------|----------|
| Security | Access control, encryption, monitoring |
| Availability | SLA, monitoring, DR, capacity planning |
| Processing Integrity | Validation, error handling, monitoring |
| Confidentiality | Classification, access, disposal |
| Privacy | Consent, collection, use, retention, disclosure |

## Technical Implementation Checklist

### Consent Management Platform (CMP)
- [ ] Granular consent per purpose (marketing, analytics, functional)
- [ ] Consent versioning and history
- [ ] Geolocation-based consent rules
- [ ] GPC (Global Privacy Control) signal detection
- [ ] Consent receipt generation (PDF/JSON)
- [ ] Integration with email/voice providers for suppression

### Data Subject Rights Automation
- [ ] DSAR intake form (web + API)
- [ ] Identity verification (email/phone/SMS)
- [ ] Data discovery across all stores (PostgreSQL, Redis, Odoo, Fonoster, useSend)
- [ ] Automated compilation (JSON/CSV/PDF)
- [ ] Secure delivery (encrypted link, expiry)
- [ ] R2E workflow with cascade delete
- [ ] Portability export (all user data)
- [ ] Rectification API
- [ ] Restriction of processing flag
- [ ] Objection handling (marketing, profiling)

### Data Protection by Design
- [ ] Data minimization (collect only what's needed)
- [ ] Purpose limitation (enforced at schema level)
- [ ] Storage limitation (TTL on all PII tables)
- [ ] Pseudonymization (hash emails/phones in analytics)
- [ ] Encryption at rest (PostgreSQL TDE, Redis encryption)
- [ ] Encryption in transit (mTLS everywhere)
- [ ] Key management (Vault, rotation, HSM)
- [ ] Privacy-enhancing tech (differential privacy for analytics)

### Vendor Risk Management
- [ ] Vendor inventory with data processing scope
- [ ] DPA executed with all subprocessors
- [ ] Security assessments (SOC2, ISO27001)
- [ ] Subprocessor notification process
- [ ] International transfer mechanisms (SCCs, adequacy)
- [ ] Vendor monitoring (continuous)
- [ ] Offboarding procedures (data return/destruction)

### Incident Response
- [ ] Breach detection (SIEM alerts)
- [ ] 72-hour GDPR notification workflow
- [ ] CCPA "without undue delay" workflow
- [ ] Regulatory contact database
- [ ] Customer notification templates
- [ ] Forensic readiness (log retention, chain of custody)
- [ ] Post-incident review process

### Audit & Documentation
- [ ] ROPA (automated, updated)
- [ ] DPIA register
- [ ] LIA register
- [ ] Consent receipt archive
- [ ] Deletion logs (immutable)
- [ ] Access logs (who accessed what PII)
- [ ] Training records
- [ ] Policy documents (privacy, retention, breach)

## Compliance Testing

### Automated Tests (CI/CD)
```python
# test_compliance.py
def test_dnc_scrub_before_call():
    """Every outbound call must check DNC list"""
    
def test_opt_out_propagation():
    """Email opt-out must suppress within 10 days"""
    
def test_consent_check_before_email():
    """No marketing email without valid consent"""
    
def test_timezone_enforcement():
    """Calls only within 8am-9pm local time"""
    
def test_recording_announcement():
    """Auto-injected on every call"""
    
def test_retention_deletion():
    """PII deleted after retention period"""
    
def test_dsar_fulfillment():
    """DSAR returns all data within 30 days"""
    
def test_encryption_at_rest():
    """All PII columns encrypted"""
    
def test_mtls_enforcement():
    """All service-to-service uses mTLS"""
```

### Penetration Testing
- [ ] Annual external pen test
- [ ] Quarterly internal vuln scan
- [ ] Pre-release DAST for new features
- [ ] Dependency scanning (SCA) on every PR
- [ ] Container scanning on every build

### Compliance Monitoring
- [ ] Consent rate dashboard
- [ ] Opt-out rate by channel
- [ ] DNC scrub hit rate
- [ ] DSAR SLA compliance
- [ ] Breach detection time
- [ ] Vendor compliance status

## Quick Reference: Consent Requirements by Channel

| Channel | Consent Type | Opt-out Method | Retention |
|---------|--------------|----------------|-----------|
| Outbound calls (US) | Prior express written (TCPA) | DNC list, verbal revoke | 24 months |
| Outbound calls (EU/UK) | Opt-in (ePrivacy) | Unsubscribe link | 24 months |
| Marketing email (US) | Opt-out (CAN-SPAM) | Unsubscribe link/footer | Until opt-out |
| Marketing email (EU/UK) | Opt-in (GDPR/ePrivacy) | Unsubscribe link | Until opt-out |
| Marketing email (CA) | Express/Implied (CASL) | Unsubscribe link | 24m/6m expiry |
| Transactional email | Legitimate interest | N/A | Per retention policy |
| SMS (US) | Prior express written | STOP reply | 24 months |
| SMS (EU/UK) | Opt-in | STOP reply | 24 months |

## Key Definitions

- **PII**: Personally Identifiable Information (name, email, phone, IP, etc.)
- **PHI**: Protected Health Information (HIPAA)
- **DNC**: Do Not Call list (FTC + state)
- **DSAR**: Data Subject Access Request
- **R2E**: Right to Erasure (Right to be Forgotten)
- **DPIA**: Data Protection Impact Assessment
- **LIA**: Legitimate Interest Assessment
- **ROPA**: Records of Processing Activities
- **DPA**: Data Processing Addendum
- **SCC**: Standard Contractual Clauses
- **ATDS**: Automatic Telephone Dialing System
- **STIR/SHAKEN**: Caller ID authentication framework
- **A2P 10DLC**: Application-to-Person 10-Digit Long Code
- **GPC**: Global Privacy Control (browser signal)

## Resources

- GDPR: https://gdpr.eu/
- CCPA: https://oag.ca.gov/privacy/ccpa
- TCPA: https://www.fcc.gov/consumers/guides/telephone-consumer-protection-act
- CAN-SPAM: https://www.ftc.gov/legal-library/browse/statutes/can-spam-act
- CASL: https://crtc.gc.ca/eng/info_sht/casl.htm
- ePrivacy: https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32002L0058
- STIR/SHAKEN: https://www.fcc.gov/call-authentication
- A2P 10DLC: https://www.tcrregister.com/