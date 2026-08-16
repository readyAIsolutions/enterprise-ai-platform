# Compliance Checklist Reference

## Quick Reference: Regulatory Requirements by Feature

| Feature | GDPR | CCPA | TCPA | CAN-SPAM | CASL | ePrivacy |
|---------|------|------|------|----------|------|----------|
| **Consent required** | ✓ Express/Implied | ✓ Opt-out | ✓ Express written | ✓ Opt-out | ✓ Express/Implied | ✓ Opt-in |
| **Consent records** | ✓ Mandatory | ✓ Recommended | ✓ Mandatory | ✓ Recommended | ✓ Mandatory | ✓ Mandatory |
| **Consent expiry** | ✓ Per purpose | ✗ No | ✗ No | ✗ No | ✓ 24mo implied | ✓ Per purpose |
| **Right to access** | ✓ DSAR | ✓ Know | ✗ No | ✗ No | ✓ Access | ✓ Access |
| **Right to delete** | ✓ R2E | ✓ Delete | ✗ No | ✗ No | ✓ Deletion | ✓ Erasure |
| **Right to portability** | ✓ Export | ✓ Portable | ✗ No | ✗ No | ✓ Portable | ✓ Portability |
| **Right to object** | ✓ Objection | ✓ Opt-out | ✓ DNC | ✓ Opt-out | ✓ Opt-out | ✓ Opt-out |
| **Breach notification** | ✓ 72hr | ✓ Undue delay | ✗ No | ✗ No | ✓ ASAP | ✓ 72hr |
| **DPA with vendors** | ✓ Mandatory | ✓ Contract | ✗ No | ✗ No | ✓ Contract | ✓ Contract |
| **Cross-border transfer** | ✓ SCCs/Adequacy | ✗ No | ✗ No | ✗ No | ✓ Adequacy | ✓ Adequacy |

---

## Implementation Priority Matrix

### P0 - Must Have Before Any Launch
- [ ] Consent collection + storage (all channels)
- [ ] Opt-out processing < 10 days (CAN-SPAM) / immediate (TCPA/CCPA)
- [ ] DNC list scrubbing before every call
- [ ] Timezone-aware calling windows
- [ ] Physical address in email footer
- [ ] Unsubscribe link in every email
- [ ] Recording consent announcements on calls
- [ ] Basic audit logging (who/what/when)

### P1 - Must Have Before Enterprise Sales
- [ ] DSAR fulfillment automation
- [ ] R2E cascade deletion
- [ ] Data portability export
- [ ] Vendor DPAs executed
- [ ] Cross-border transfer mechanisms
- [ ] Breach notification workflow
- [ ] Retention policies + automated deletion
- [ ] Encryption at rest (PII columns)
- [ ] mTLS everywhere (service-to-service)

### P2 - Differentiators for Competitive Deals
- [ ] Consent Management Platform (CMP)
- [ ] Global Privacy Control (GPC) support
- [ ] Real-time consent verification API
- [ ] Advanced DPIA/LIA automation
- [ ] Compliance dashboard for customers
- [ ] SOC 2 Type II readiness

---

## Channel-Specific Requirements

### Voice (Fonoster)
| Requirement | Regulation | Implementation |
|-------------|------------|----------------|
| Prior express written consent | TCPA | Consent record with timestamp + proof |
| DNC list scrubbing | TCPA | Pre-call API check against FTC + state lists |
| Timezone windows (8am-9pm local) | TCPA | Contact timezone lookup + window check |
| ATDS avoidance | TCPA | Human click-to-dial, no predictive dialing |
| Recording announcement | TCPA/State | Auto-injected at call start |
| Call recording retention | TCPA/GDPR | Configurable TTL + auto-delete |
| STIR/SHAKEN attestation | FCC | Carrier integration |
| A2P 10DLC registration | FCC | Brand + campaign registration |

### Email (useSend)
| Requirement | Regulation | Implementation |
|-------------|------------|----------------|
| Unsubscribe headers | CAN-SPAM/CASL/GDPR | List-Unsubscribe, List-Unsubscribe-Post |
| Physical address | CAN-SPAM | Template variable in footer |
| Clear opt-out link | CAN-SPAM/CASL/GDPR | One-click unsubscribe |
| Opt-out honored <10 days | CAN-SPAM | Automated suppression sync |
| Identify as ad | CAN-SPAM | Subject line/body disclosure |
| Sender identification | CASL/GDPR | From name + address + contact |
| Consent records | GDPR/CASL | Linked to contact record |

### CRM (Odoo 19)
| Requirement | Regulation | Implementation |
|-------------|------------|----------------|
| Data minimization | GDPR | Only collect necessary fields |
| Purpose limitation | GDPR | Field-level purpose tags |
| Retention schedules | GDPR | Automated archival/deletion |
| Access controls | GDPR/SOC2 | Role-based + row-level security |
| Audit trail | GDPR/SOC2 | Immutable field history |
| Data portability | GDPR | Export all contact data |
| Right to erasure | GDPR | Cascade delete workflow |

---

## Consent Record Schema (Database)

```sql
CREATE TABLE consent_records (
    id UUID PRIMARY KEY,
    contact_id UUID REFERENCES contacts(id),
    channel VARCHAR(20), -- email, voice, sms, webhook
    consent_type VARCHAR(30), -- express, implied, legitimate_interest
    jurisdiction CHAR(2), -- US, CA, DE, FR, etc.
    granted_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ, -- NULL = perpetual (express)
    revoked_at TIMESTAMPTZ,
    proof JSONB, -- {ip, user_agent, form_url, version, checkbox_text}
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_consent_contact_channel ON consent_records(contact_id, channel);
CREATE INDEX idx_consent_jurisdiction ON consent_records(jurisdiction);
CREATE INDEX idx_consent_expires ON consent_records(expires_at) WHERE expires_at IS NOT NULL;
```

## Suppression Schema

```sql
CREATE TABLE suppressions (
    id UUID PRIMARY KEY,
    contact_id UUID REFERENCES contacts(id),
    channel VARCHAR(20),
    reason VARCHAR(50), -- opt_out, dnc_scrub, bounce, complaint, manual
    source VARCHAR(50), -- internal, vendor, list
    timestamp TIMESTAMPTZ NOT NULL,
    metadata JSONB,
    UNIQUE(contact_id, channel, reason)
);
```

## Opt-Out Registry Schema

```sql
CREATE TABLE opt_out_registry (
    contact_id UUID REFERENCES contacts(id),
    channel VARCHAR(20),
    opted_out_at TIMESTAMPTZ NOT NULL,
    method VARCHAR(50), -- unsubscribe_link, reply_stop, api, manual
    PRIMARY KEY (contact_id, channel)
);
```

## DNC List Management

```sql
CREATE TABLE dnc_lists (
    id UUID PRIMARY KEY,
    jurisdiction CHAR(2) NOT NULL,
    list_name VARCHAR(100),
    source_url VARCHAR(500),
    last_updated TIMESTAMPTZ NOT NULL,
    entry_count INTEGER DEFAULT 0,
    checksum VARCHAR(64) -- for integrity verification
);

CREATE TABLE dnc_entries (
    dnc_list_id UUID REFERENCES dnc_lists(id),
    identifier VARCHAR(100) NOT NULL, -- phone or email
    identifier_type VARCHAR(20), -- phone, email
    added_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (dnc_list_id, identifier)
);
```

---

## Audit Log Schema (Immutable)

```sql
CREATE TABLE audit_log (
    id BIGSERIAL PRIMARY KEY, -- sequential for ordering
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    correlation_id UUID, -- links related events
    actor_type VARCHAR(30), -- user, system, api, cron
    actor_id VARCHAR(100),
    action VARCHAR(100), -- consent.granted, opt_out.recorded, dnc.scrubbed, dsar.fulfilled
    resource_type VARCHAR(50), -- contact, consent, suppression, campaign
    resource_id VARCHAR(100),
    jurisdiction CHAR(2),
    details JSONB,
    prev_hash CHAR(64), -- SHA256 of previous row for tamper evidence
    row_hash CHAR(64) -- SHA256 of this row
);

CREATE INDEX idx_audit_timestamp ON audit_log(timestamp);
CREATE INDEX idx_audit_correlation ON audit_log(correlation_id);
CREATE INDEX idx_audit_resource ON audit_log(resource_type, resource_id);
```

---

## Vendor DPA Checklist

For each subprocessors (Fonoster, useSend, Odoo, OpenRouter, PostgreSQL, Redis):

- [ ] Data Processing Addendum signed
- [ ] Subprocessor list disclosed
- [ ] International transfer mechanism (SCCs for non-adequate)
- [ ] Security measures documented
- [ ] Breach notification timeline (<24h to you)
- [ ] Right to audit / security questionnaire
- [ ] Data deletion on termination
- [ ] Subprocessor change notification (30 days)
- [ ] GDPR Article 28 compliance confirmation

---

## Breach Notification Decision Tree

```
Breach Detected
      │
      ▼
Is personal data involved?
      │
      ├── No → Log internally, monitor
      │
      └── Yes
           │
           ▼
Is there risk to rights/freedoms?
      │
      ├── Low risk → Document, notify DPO, monitor
      │
      └── High risk
           │
           ▼
      ┌────┴────┐
      ▼         ▼
GDPR 72hr   CCPA "without
to SA       undue delay"
      │         │
      ▼         ▼
Notify   ▼Notify
   Affected   Affected
  data       CA
 subjects    residents
      │         │
      └────┬────┘
           ▼
    Document everything
    (what, when, how, impact, mitigation)
```

---

## Retention Schedule Template

| Data Category | Retention Period | Legal Basis | Deletion Method |
|---------------|------------------|-------------|-----------------|
| Call recordings | 90 days (config) | Legitimate interest / Consent | Automated purge + backup wipe |
| Email content | 365 days | Contract performance | Automated purge |
| Consent records | 7 years after revoke | Legal obligation | Archive then purge |
| Suppression lists | Permanent | Legal obligation | Never delete |
| Audit logs | 7 years | Legal obligation | Immutable archive |
| Campaign analytics | 3 years | Legitimate interest | Aggregate then delete PII |
| CRM contact data | Account lifetime + 7y | Contract/legal | R2E workflow |
| Payment/billing | 7 years | Tax law | Archive |

---

## Testing Compliance in CI/CD

```yaml
# .github/workflows/compliance.yml
jobs:
  compliance:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Run compliance tests
        run: |
          python scripts/test_compliance.py
      
      - name: Check consent record schema
        run: |
          python -c "
          import sqlalchemy as sa
          # Verify all required tables/columns exist
          "
      
      - name: Verify DNC list freshness
        run: |
          python -c "
          # Check DNC lists updated within 30 days
          "
      
      - name: Verify encryption at rest
        run: |
          python -c "
          # Check PII columns use pgcrypto or TDE
          "
      
      - name: Verify mTLS config
        run: |
          python -c "
          # Check all service-to-service uses mTLS
          "
```

---

## Quick Commands

```bash
# Run compliance test suite
python scripts/test_compliance.py

# Verify DNC lists are fresh
python -c "
from datetime import datetime, timedelta
# Check last_updated on all dnc_lists
"

# Generate DSAR report for contact
python -c "
from compliance import generate_dsar_report
generate_dsar_report('contact-uuid')
"

# Execute R2E for contact
python -c "
from compliance import execute_right_to_erasure
execute_right_to_erasure('contact-uuid')
"

# Export contact data (portability)
python -c "
from compliance import export_contact_data
export_contact_data('contact-uuid', format='json')
"

# Check consent validity for campaign
python -c "
from compliance import verify_campaign_consent
verify_campaign_consent(campaign_id='camp-xyz')
"
```

---

## Compliance Dashboard Metrics

Track these in your observability stack:

| Metric | Target | Alert If |
|--------|--------|----------|
| Consent coverage (contacts with valid consent) | > 95% | < 90% |
| Opt-out processing time | < 24 hours | > 48 hours |
| DNC list freshness | < 30 days | > 60 days |
| DSAR fulfillment time | < 30 days | > 25 days |
| R2E completion time | < 7 days | > 5 days |
| Breach detection time | < 1 hour | > 4 hours |
| Vendor DPA status | 100% current | Any expired |
| Cross-border transfer validity | 100% covered | Any uncovered |

---

*Generated as part of saas-production-hardening skill*