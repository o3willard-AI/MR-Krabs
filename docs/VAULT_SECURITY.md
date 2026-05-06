# 🔐 MR-Krabs Vault Security Guide

**Version:** 1.0  
**Status:** Production-Ready (Phase 5.0)  
**Classification:** Internal - Security Critical

---

## 🎯 Overview

The **Encrypted Vault** is MR-Krabs' security-critical component responsible for storing and protecting LLM provider API keys (OpenAI, Anthropic, OpenRouter, etc.). This guide covers the architecture, security features, and operational procedures.

### Why This Matters

LLM provider API keys represent the **highest financial risk** in MR-Krabs:
- Compromised keys can lead to **unlimited budget drain**
- Keys allow access to expensive token consumption ($10-$100+ per million tokens)
- Malicious actors can use leaked keys before they're detected
- Recovery requires provider-side key revocation (time-sensitive)

The vault mitigates these risks through:
1. **Encryption at rest** - Keys never stored in plaintext
2. **Audit logging** - All access tracked for forensic analysis
3. **Rate limiting** - Prevents abuse even if keys leak
4. **Secure logging** - Keys stripped from all logs automatically

---

## 🏗️ Architecture

### Security Zones

```
┌─────────────────────────────────────────────────────────────┐
│                    SECURITY ZONES                          │
├─────────────────────────────────────────────────────────────┤
│                                                           │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Zone 1: External (Untrusted)                      │   │
│  │   - HTTP endpoints                                  │   │
│  │   - Client requests                                 │   │
│  │   - NO ACCESS to vault                              │   │
│  └─────────────────────────────────────────────────────┘   │
│                           │                                │
│                           ▼ (authentication required)      │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Zone 2: Application Layer (Semi-Trust)            │   │
│  │   - User sessions                                   │   │
│  │   - Cost tracking                                   │   │
│  │   - Access to vault via LLMProviderService         │   │
│  └─────────────────────────────────────────────────────┘   │
│                           │                                │
│                           ▼ (internal only)                │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Zone 3: Vault Layer (High Security)               │   │
│  │   - EncryptedVault                                  │   │
│   - Master key management                              │   │
│   │   - Key decryption/encryption                      │   │
│   └─────────────────────────────────────────────────────┘   │
│                           │                                │
│                           ▼ (encrypted storage)            │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Zone 4: Storage (Encrypted at Rest)               │   │
│  │   - Encrypted vault file (.enc)                     │   │
│  │   - Master key in OS environment/keyring            │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                           │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow (Secure)

```
External Request          Authentication          Vault Access
      │                        │                        │
      ▼                        ▼                        ▼
┌──────────┐           ┌──────────────┐        ┌─────────────┐
│ Client   │  ──────►  │  API Server  │  ──►  │  LLMService │
│ (Agent)  │           │   (Auth)     │        │             │
└──────────┘           └──────────────┘        └──────┬──────┘
                                                      │
                                                      ▼
                                           ┌─────────────────┐
                                           │ Encrypted Vault │
                                           │  (Decryption)   │
                                           └────────┬────────┘
                                                    │
                                                    ▼
                                          ┌────────────────┐
                                          │ Decrypted Key  │
                                          │  (In RAM only) │
                                          └────────────────┘
```

**Key Principle:** API keys are **never exposed to clients**, only used internally by LLMProviderService.

---

## 🔧 Core Components

### 1. EncryptedVault (`src/core/vault.py`)

The main vault implementation using Fernet symmetric encryption.

```python
from src.core.vault import Vault, EncryptedVault

# Production: encrypted file with master key from environment
vault = Vault.create(
    backend="encrypted",
    vault_path="/etc/mrkrabs/vault.enc",
    master_key=os.environ["VAULT_MASTER_KEY"]  # Never in code!
)

# Add provider keys (admin operation only)
vault.add_provider_key("openai", "sk-actual-api-key")

# Retrieve key for use (rate-limited, audited)
api_key = vault.get_provider_key("openai")
```

**Features:**
- Fernet symmetric encryption (AES-128-CBC with HMAC)
- Atomic file writes (prevents corruption)
- Thread-safe operations (reentrant lock)
- Automatic audit logging on all access
- Rate limiting per provider

---

### 2. MemoryVault (Development Only)

In-memory vault for testing without encryption overhead.

```python
from src.core.vault import Vault, MemoryVault

# Development/testing only - keys NOT encrypted
vault = Vault.create(backend="memory")

⚠️ WARNING: Never use in production! Keys exist in RAM unprotected.
```

**Use Cases:**
- Unit testing
- Local development (with test keys)
- CI/CD pipeline validation

---

### 3. SecurityLogger (`src/core/vault.py`)

Automatic log sanitization to prevent key leakage.

```python
from src.core.vault import SecurityLogger

logger = SecurityLogger(base_logger)

# Safe: Keys automatically stripped
logger.info("Loaded config", config={"api_key": "sk-secret"})
# Output: "Loaded config" with {"api_key": "***REDACTED***"}
```

**Detection Patterns:**
- Dictionary keys containing: `key`, `secret`, `token`, `password`
- String values matching API key patterns (e.g., `sk-`, long alphanumeric)
- Recursive sanitization of nested structures

---

### 4. AuditLogger (`src/core/vault.py`)

Immutable audit trail for all vault access.

```python
from src.core.vault import AuditLogger

audit_logger = AuditLogger("/var/log/mrkrabs/audit.log")

# Logs every vault operation
audit_logger.log_access(
    action="get_key",
    provider="openai",
    success=True
)

# Output (JSON line):
# {"timestamp":"2026-05-06T14:32:15.123Z","event_type":"vault_access","action":"get_key","provider":"openai","success":true}
```

**Audit Trail Contents:**
- Timestamp (UTC)
- Action performed (`get_key`, `add_key`, `remove_key`)
- Provider name
- Success/failure status
- Caller context (file, function, line)

---

### 5. RateLimiter (`src/core/vault.py`)

Prevents abuse even if keys are somehow leaked.

```python
from src.core.vault import RateLimiter

limiter = RateLimiter()

# Default limits:
# - 10 requests per second per provider
# - $50/hour budget cap per provider

if limiter.check_request_limit("openai"):
    # Proceed with request
else:
    raise RateLimitExceeded("Too many requests")
```

**Limits (Configurable):**
- `requests_per_second`: 10 (prevents DoS)
- `tokens_per_minute`: 100,000 (~$1-5/hour)
- `spend_per_hour`: $50.00 (hard budget cap)

---

## 🚀 Setup & Configuration

### Step 1: Initialize the Vault

```bash
cd /home/sblanken/working/code/MR-Krabs

# Run the setup script
./scripts/setup-vault.sh init
```

**What Happens:**
1. Creates vault directory (`/etc/mrkrabs/vault.enc`)
2. Generates random master key (Fernet key)
3. Saves master key to `~/.mrkrabs/master.key`
4. Sets restrictive permissions (0600)

**Output Example:**
```
✓ Vault initialized successfully!

🔴 CRITICAL SECURITY NOTICE 🔴

Master key saved to: /home/sblanken/.mrkrabs/master.key

IMPORTANT:
  1. NEVER commit the master key to version control
  2. Back it up securely (password manager, encrypted storage)
  3. If lost, the vault CANNOT be recovered

Next steps:
  ./scripts/setup-vault.sh add-key openai <your-openai-api-key>
```

---

### Step 2: Add Provider Keys

```bash
# Add OpenAI key
./scripts/setup-vault.sh add-key openai sk-your-actual-api-key

# Add Anthropic key
./scripts/setup-vault.sh add-key anthropic your-anthropic-key

# List configured providers
./scripts/setup-vault.sh list
```

**Output:**
```
Providers configured in vault:
  ✓ openai
  ✓ anthropic
```

---

### Step 3: Configure Environment

Set the master key for application access:

```bash
# Option A: Load from file (recommended)
export MRKRABS_MASTER_KEY_FILE="$HOME/.mrkrabs/master.key"

# Option B: Set directly (for scripts, CI/CD)
export VAULT_MASTER_KEY="base64-encoded-32-byte-key"

# Option C: Custom vault path
export MRKRABS_VAULT_PATH="/custom/path/vault.enc"
```

**Environment Variables:**

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `VAULT_MASTER_KEY` | Master encryption key (base64) | - | Yes (or file) |
| `MRKRABS_MASTER_KEY_FILE` | Path to master key file | `~/.mrkrabs/master.key` | No |
| `MRKRABS_VAULT_PATH` | Path to vault file | `/etc/mrkrabs/vault.enc` | No |

---

### Step 4: Initialize in Application

```python
from src.core.vault import Vault
from src.core.llm_provider import get_llm_provider_service

# The service auto-initializes from environment variables
provider_service = get_llm_provider_service()

# List available providers
providers = provider_service.list_available_providers()
# Output: ['openai', 'anthropic']
```

**No Need to Manually Load Keys:**
The LLMProviderService automatically retrieves keys from the vault when needed. Never pass raw API keys around!

---

## 🔒 Security Best Practices

### ✅ DO:

1. **Store Master Key Securely**
   - Use OS keyring (`keyring` library) for local deployments
   - Use cloud secrets manager (AWS KMS, HashiCorp Vault) for production
   - Back up the key to encrypted storage

2. **Restrict File Permissions**
   ```bash
   chmod 600 /etc/mrkrabs/vault.enc
   chmod 600 ~/.mrkrabs/master.key
   ```

3. **Use Environment Variables**
   - Never hardcode keys in source code
   - Use `.env` files with proper `.gitignore`

4. **Rotate Keys Periodically**
   - Rotate LLM provider keys every 90 days
   - Rotate master key annually (requires re-encryption)

5. **Monitor Audit Logs**
   ```bash
   tail -f /var/log/mrkrabs/audit.log | grep "success.*false"
   # Alert on failed access attempts
   ```

6. **Use Memory Vault Only in Development**
   - Never deploy with `backend="memory"` to production
   - CI/CD pipelines should use test keys only

---

### ❌ DON'T:

1. **Never Commit Vault Files**
   ```bash
   # Add to .gitignore
   *.enc
   master.key
   .env
   ```

2. **Never Log Raw Keys**
   - Always use `SecurityLogger` for vault-related logging
   - Audit logs are the exception (need full details for forensics)

3. **Never Expose Vault to Clients**
   - No HTTP endpoints for vault access
   - Only internal services can access keys

4. **Don't Use Production Keys in Development**
   - Separate vaults for dev/staging/production
   - Different providers if possible (e.g., test vs production accounts)

5. **Don't Ignore Rate Limit Errors**
   - Investigate why limits are being hit
   - Could indicate abuse or misconfiguration

---

## 🔍 Monitoring & Alerting

### Audit Log Analysis

```bash
# Check for failed access attempts
grep "success.*false" /var/log/mrkrabs/audit.log | tail -20

# Check for unusual provider access
grep '"provider":"openai"' /var/log/mrkrabs/audit.log | wc -l

# Find all key additions/removals
grep -E 'add_key|remove_key' /var/log/mrkrabs/audit.log
```

### Alerting Rules (Example)

```python
# Pseudo-code for alerting system
def check_vault_anomalies(audit_logs):
    anomalies = []
    
    # 1. Multiple failed attempts (possible attack)
    if count_failed_accesses() > 10:
        anomalies.append("Potential brute force attack")
    
    # 2. Access from unusual location
    if caller_location != "expected":
        anomalies.append("Access from unexpected source")
    
    # 3. Unusual volume of requests
    if request_rate > threshold:
        anomalies.append("Abnormal request volume")
    
    # 4. Key removal without replacement
    if key_removed and not new_key_added():
        anomalies.append("Key removed - possible security incident")
    
    return anomalies
```

### Recommended Alerts

| Condition | Severity | Action |
|-----------|----------|--------|
| Failed access attempts > 10/min | HIGH | Investigate, possibly block IP |
| Key removed from vault | CRITICAL | Immediate investigation |
| Rate limit exceeded | MEDIUM | Check for abuse or misconfig |
| New provider added | LOW | Log for audit trail |

---

## 🛠️ Operational Procedures

### Rotate Provider API Key

```bash
# 1. Add new key (keep old one temporarily)
./scripts/setup-vault.sh add-key openai sk-new-api-key

# 2. Test that both keys work (optional grace period)
python -c "from src.core.vault import Vault; v = Vault.create(); print(v.get_provider_key('openai'))"

# 3. Remove old key once confirmed working
# (Requires editing vault directly or using admin tool)
```

**Note:** The current implementation replaces the key. For graceful rotation, add support for multiple keys per provider (future enhancement).

---

### Rotate Master Key (Advanced)

⚠️ **CRITICAL OPERATION - Back up everything first!**

```bash
# 1. Create new vault with new master key
VAULT_MASTER_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")

# 2. Export all keys from old vault
python3 << EOF
from src.core.vault import Vault

old_vault = Vault.create(backend="encrypted", master_key=os.environ["OLD_MASTER_KEY"])
providers = old_vault.list_providers()

new_vault = Vault.create(
    backend="encrypted", 
    vault_path="/etc/mrkrabs/vault.new.enc",
    master_key="$VAULT_MASTER_KEY"
)

for provider in providers:
    key = old_vault.get_provider_key(provider)
    new_vault.add_provider_key(provider, key)

print("Keys migrated successfully")
EOF

# 3. Replace old vault with new one (atomic operation)
mv /etc/mrkrabs/vault.new.enc /etc/mrkrabs/vault.enc

# 4. Update environment variables
export VAULT_MASTER_KEY="$VAULT_MASTER_KEY"

# 5. Test the application works
python -c "from src.core.vault import Vault; v = Vault.create(); print(v.list_providers())"

# 6. Securely delete old master key (if no longer needed)
rm ~/.mrkrabs/master.key.old
```

---

### Respond to Key Compromise Incident

**Step 1: Immediate Containment**
```bash
# Remove compromised provider key immediately
python3 << EOF
from src.core.vault import Vault
vault = Vault.create(backend="encrypted")
vault.remove_provider_key("compromised_provider")
EOF

# Block at firewall level if possible
sudo iptables -A OUTPUT -d api.openai.com -j DROP  # Example for OpenAI
```

**Step 2: Revoke with Provider**
- Go to provider dashboard (OpenAI, Anthropic, etc.)
- Revoke the compromised key
- Generate a new replacement key

**Step 3: Add New Key**
```bash
./scripts/setup-vault.sh add-key openai sk-replacement-key
```

**Step 4: Investigate**
```bash
# Check audit logs for unauthorized access
grep "openai" /var/log/mrkrabs/audit.log | grep -v "your-user"

# Review rate limit hits (may indicate abuse)
grep "Rate limit exceeded" /var/log/mrkrabs/application.log
```

**Step 5: Document & Report**
- Create incident report with timeline
- Notify affected stakeholders
- Update security procedures based on findings

---

## 🧪 Testing the Vault

### Run Unit Tests

```bash
cd /home/sblanken/working/code/MR-Krabs

# Run vault-specific tests
pytest tests/test_vault.py -v

# Output example:
# ================= test session starts =================
# collected 47 items
# 
# tests/test_vault.py::TestVaultFactory::test_create_memory_vault PASSED [  2%]
# tests/test_vault.py::TestSecurityLogger::test_sanitize_removes_api_key_from_dict PASSED [  6%]
# ...
# ===================== 47 passed in 0.45s ====================
```

### Integration Test (Manual)

```python
# test_vault_integration.py
from src.core.vault import Vault, generate_master_key

def test_encrypted_vault():
    """Test encrypted vault with temporary master key."""
    # Generate temporary master key
    master_key = generate_master_key()
    
    # Create vault in temp directory
    vault = Vault.create(
        backend="encrypted",
        vault_path="/tmp/test-vault.enc",
        master_key=master_key
    )
    
    # Add provider
    vault.add_provider_key("openai", "sk-test-key-123")
    
    # Retrieve it
    key = vault.get_provider_key("openai")
    assert key == "sk-test-key-123"
    
    print("✓ Encrypted vault integration test passed")

if __name__ == "__main__":
    test_encrypted_vault()
```

---

## 📋 Troubleshooting

### Vault Won't Load: Invalid Master Key

**Error:** `VaultBackendError: Failed to decrypt vault - invalid master key`

**Solution:**
1. Verify the correct master key is loaded
   ```bash
   echo $VAULT_MASTER_KEY  # Should be 44 character base64 string
   ```

2. Check if master key file exists
   ```bash
   ls -la ~/.mrkrabs/master.key
   ```

3. Try loading from environment variable instead
   ```bash
   export VAULT_MASTER_KEY=$(cat ~/.mrkrabs/master.key)
   ```

---

### Permission Denied on Vault File

**Error:** `PermissionError: [Errno 13] Permission denied`

**Solution:**
```bash
# Fix file permissions
chmod 600 /etc/mrkrabs/vault.enc
chown $USER:$USER /etc/mrkrabs/vault.enc

# Or if using system user
sudo chown mrkrabs:mrkrabs /etc/mrkrabs/vault.enc
```

---

### Rate Limit Exceeded in Production

**Error:** `VaultAccessDeniedError: Rate limit exceeded for provider openai`

**Causes:**
- Legitimate high-volume usage hitting limits
- Possible abuse or attack
- Misconfigured application making excessive requests

**Solution:**
1. Check audit logs for unusual patterns
2. Verify application isn't in infinite loop
3. Consider increasing rate limit if legitimate (configure in `RateLimiter`)
4. If attack, block the source at firewall level

---

## 🔮 Future Enhancements

Planned improvements for Phase 5.1+:

1. **Cloud KMS Integration**
   - AWS KMS, Azure Key Vault, Google Cloud KMS
   - Hardware Security Module (HSM) support

2. **Multi-Tenant Isolation**
   - Separate vaults per tenant/organization
   - Cross-tenant access prevention

3. **Automatic Key Rotation**
   - Scheduled rotation with provider APIs
   - Grace period for old keys during transition

4. **Vault Service Isolation**
   - Separate vault service (network-isolated)
   - mTLS between main server and vault

5. **Enhanced Audit Trail**
   - Ship logs to external SIEM system
   - Real-time anomaly detection with ML

---

## 📚 References

### Cryptography Details

- **Fernet**: Symmetric encryption using AES-128-CBC with HMAC for authentication
- **Key Derivation**: PBKDF2HMAC (for password-based master keys, future)
- **File Permissions**: 0600 (owner read/write only)

### Compliance & Standards

- Meets OWASP API Security requirements
- Aligns with NIST guidelines for key management
- Audit trails support SOC 2 Type II compliance

---

## 🆘 Support

**Security Incidents:** Contact security team immediately  
**Operational Issues:** Check troubleshooting section above  
**Feature Requests:** Create GitHub issue with "Vault" label

---

**Document Version:** 1.0  
**Last Updated:** May 6, 2026  
**Review Date:** June 6, 2026 (quarterly security review)
