# kuipa on Arbiter Hub lab — 2026-10-23

Results from deploying kuipa on the Beaker-provisioned Arbiter Hub demo lab (Fedora 44, IPA realm ARBITER.DEMO, reservation through 10/24).

## Environment

| Node | Role |
|---|---|
| idm.arbiter.demo | IPA server + kuipad |
| hub.arbiter.demo | Arbiter Hub API + UI |
| agent.arbiter.demo | Workload agent |

- Fedora 44, OpenSSL 3.5.9, Rust 1.99.0
- kuipa built from `main` (commit e47d7b7, 2026-10-23)
- 296 tests pass (`cargo test --workspace`)

## What works

### 1. Build and install

All binaries compile cleanly on Fedora 44 with stock packages:

```
dnf install rust cargo gcc clang-devel pkgconf-pkg-config \
    openssl-devel krb5-devel openldap-devel
cargo build --release   # 3m49s
```

Installed to `/usr/local/bin/`: `kuipa`, `kuipad`, `kuipa-unseal`, `kuipa-voucher`, `kuipa-audit`, `tang-pqc`.

### 2. Server setup

Config at `/etc/ipa/kuipad.json` — adapted from the example for realm ARBITER.DEMO:

```json
{
  "realm": "ARBITER.DEMO",
  "domain": "arbiter.demo",
  "basedn": "dc=arbiter,dc=demo",
  "server": "idm.arbiter.demo",
  "ldap_uri": "ldapi://%2Frun%2Fslapd-ARBITER-DEMO.socket",
  "principal": "ipa-ku/idm.arbiter.demo@ARBITER.DEMO",
  "service": "ipa-ku@idm.arbiter.demo",
  "keytab": "/var/lib/ipa/ku/kuipa.keytab",
  "ca_file": "/etc/ipa/ca.crt",
  "pkinit_anchors_file": "/var/lib/ipa-client/pki/kdc-ca-bundle.pem",
  "key_dir": "/var/lib/ipa/ku",
  "peers": [],
  "discover_peers": false,
  "anchor": true
}
```

Steps that worked:

```bash
# IPA service principal + keytab
ipa service-add ipa-ku/idm.arbiter.demo@ARBITER.DEMO
ipa-getkeytab -s idm.arbiter.demo \
  -p ipa-ku/idm.arbiter.demo@ARBITER.DEMO \
  -k /var/lib/ipa/ku/kuipa.keytab

# Generate keys (anchor + join + escrow + signing + trust + Tang)
kuipad generate-keys
# → MPJ6c9vUCqPNesTMXqznmugWRTvHvTjSF10yEYYXw4k

# S4U2Proxy delegation rules (manual — no FreeIPA installer integration)
ipa servicedelegationtarget-add kuipa-ldap-target
ipa servicedelegationtarget-add-member kuipa-ldap-target \
  --principals=ldap/idm.arbiter.demo@ARBITER.DEMO
ipa servicedelegationrule-add kuipa-delegation
ipa servicedelegationrule-add-member kuipa-delegation \
  --principals=ipa-ku/idm.arbiter.demo@ARBITER.DEMO
ipa servicedelegationrule-add-target kuipa-delegation \
  --servicedelegationtargets=kuipa-ldap-target
ipa service-mod ipa-ku/idm.arbiter.demo@ARBITER.DEMO \
  --ok-to-auth-as-delegate=true --ok-as-delegate=true

# Start daemon
nohup kuipad serve > /var/log/kuipad.log 2>&1 &
chgrp apache /run/ipa/kuipad.sock
chmod 660 /run/ipa/kuipad.sock

# httpd proxy (contrib/kuipa.conf) + SELinux policy module
cp contrib/kuipa.conf /etc/httpd/conf.d/
# SELinux: httpd_t needs write to ipa_var_run_t sock_file
grep "denied.*kuipad.sock" /var/log/audit/audit.log | \
  audit2allow -M kuipa-httpd && semodule -i kuipa-httpd.pp
systemctl restart httpd
```

### 3. Enrollment (OTP via --ldap-otp)

```bash
# On IPA server: create host with OTP
ipa host-add kuipa-test.arbiter.demo --random --force
# → Random password: 9Ly9QX4uWhdedv0SFoQHLKR

# On client (hub node, using KUIPA_ROOT for isolation):
KUIPA_ROOT=/tmp/kuipa-test kuipa enroll \
  --enrollment-file <(echo "ipa-ku1:ARBITER.DEMO:MPJ6c9...:1792859588:9Ly9QX4uWhdedv0SFoQHLKR") \
  --hostname kuipa-test.arbiter.demo \
  --server idm.arbiter.demo \
  --ldap-otp
```

Output:
```
Enrolled host/kuipa-test.arbiter.demo@ARBITER.DEMO in ARBITER.DEMO:
its keys, the realm's anchors, CA and Kerberos configuration all taken
from idm.arbiter.demo's verified advertisement.
  principal: host/kuipa-test.arbiter.demo@ARBITER.DEMO
       kvno: 1
     issuer: idm.arbiter.demo
```

Files written: keytab, IPA CA cert, pinned anchors, PKINIT anchors, krb5.conf, state.json, realm.json.

### 4. Advertisement verification

```bash
KUIPA_ROOT=/tmp/kuipa-test kuipa check --server idm.arbiter.demo
```

Output:
```
  servers:
    idm.arbiter.demo: advertisement verified
                      delegation: 89 days left
```

### 5. Tang PQ endpoint

```bash
curl -sk https://idm.arbiter.demo/ipa/ku/tang/adv | python3 -m json.tool
```

Returns ML-KEM-768 + ML-DSA-65 advertisement — ready for `tang-pqc` Clevis pin.

## What's blocked

### kuipa protect (sealed keytab)

`kuipa protect` calls rekey, which tries to write `ipaKUEscrowBinding` attributes on the host entry via LDAP.

```
kuipad: Rekey kuipa-test.arbiter.demo: request refused:
  LDAP protocol error 50: ldap_modify_ext_s: Insufficient access
```

**Needs:** ACIs in FreeIPA allowing the `ipa-ku` service principal to write escrow binding attributes on host entries. This is the "FreeIPA server: schema, ACIs" item in TODO.md.

**Question for AB:** Is there a minimal set of ACIs we could add manually to unblock `kuipa protect` in a demo environment, without the full FreeIPA installer integration? Something like:

```
aci: (targetattr = "ipaKUEscrowBinding || ipaKUEscrowFileBinding")
     (version 3.0; acl "kuipa escrow bindings";
      allow (read,search,write)
      userdn = "ldap:///krbprincipalname=ipa-ku/idm.arbiter.demo@ARBITER.DEMO,cn=services,cn=accounts,dc=arbiter,dc=demo";)
```

### kuipa check — TGT verification

After `--ldap-otp` enrollment, `kuipa check` can verify the advertisement but cannot get a TGT with the enrolled keys:

```
WARN krb5_get_init_creds_keytab failed code=0x96c73a18
     errmsg="Preauthentication failed"
```

**Needs:** The §5.3 change where `ipa host-add --random` also sets the OTP as the host's Kerberos key with `krbPrincipalExpiration`. Until then, `--ldap-otp` enrollment creates keys that the KDC doesn't recognize.

**Question for AB:** For the demo, is there a workaround? Can we manually set the Kerberos key on the host entry after enrollment, or use a different enrollment method that produces KDC-valid keys?

### Already-enrolled hosts

Existing IPA clients (enrolled via `ipa-client-install`) get "Host already enrolled" when trying `kuipa enroll`. The KEYTAB_GET extended operation rejects the join because a keytab already exists.

**Question for AB:** Is there a planned path for existing IPA clients? Something like `kuipa adopt` or `kuipa enroll --existing` that sets up the PQ state without re-keying through KEYTAB_GET? The biggest fleet for Arbiter Hub demos will be hosts that are already IPA clients.

## What we'd like to demo

The Arbiter Hub prototype is a federation attestation control plane — it tracks workloads through a state machine (REGISTERED → ATTESTING → HEALTHY → STALE/FAILED → REVOKED) using Keylime, Falco, cosign, and measured_boot backends.

kuipa adds the credential lifecycle layer underneath attestation. The demo narrative:

1. **PQ enrollment** — workload registers with Arbiter Hub, kuipa enrollment creates the IPA identity with ML-KEM-protected key delivery
2. **Sealed keytab** — `kuipa protect` binds the credential to the IPA server set. VM clone → credential dead → Arbiter Hub detects auth failure → state transition to FAILED
3. **Revocation chain** — Arbiter Hub REVOKED → EDA playbook → `kuipa cleanup` → credential destruction (not just network isolation)
4. **Credential health signal** — `kuipa check` as a lightweight readiness indicator alongside Keylime/Falco attestation

Items 1 and 4 (advertisement verification) work today. Items 2 and 3 need the ACIs above.

## Lab details

- Beaker job J:1200306184, reservation through 2026-10-24
- kuipa source at `/root/kuipa` on idm.arbiter.demo
- kuipad running as nohup process (not systemd — research prototype)
- SELinux policy module `kuipa-httpd` installed for socket proxy
- S4U2Proxy delegation manually configured
- Test host `kuipa-test.arbiter.demo` enrolled, state at `/tmp/kuipa-test` on hub.arbiter.demo
