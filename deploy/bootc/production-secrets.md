# Production secrets for the Arbiter Server bootc image

Demo images generate their own DB and local-admin passwords at firstboot. A
production deployment must supply them, sealed, before firstboot runs.

## What firstboot expects

| Path | Meaning |
|---|---|
| `/etc/arbiter/secrets/db_password.cred` | sealed Postgres password for the `arbiter` role |
| `/etc/arbiter/secrets/local_admin_password.cred` | sealed local-admin password (break-glass) |
| `/etc/arbiter/server.env` | must contain `ARBITER_DEPLOYMENT_MODE=production` (the default) |

`ARBITER_DEPLOYMENT_MODE` defaults to `production`. In that mode firstboot:

- refuses the demo IPA password (`Secret123!`) and exits 1
- decrypts `*.cred` into `/etc/arbiter/secrets/<name>` (mode 0600, dir 0700)
- exits 1 if a sealed credential is missing — it never generates one silently
- disables the local admin account unless `ARBITER_ALLOW_LOCAL_ADMIN=true`

There is no `/run/secrets` file for the API to read until firstboot has run; the
podman secrets (`arbiter-hub-db-password`, `arbiter-hub-admin-password`) are
created from the decrypted files.

## Sealing

Run `seal-secrets.sh` as root after the image is deployed and before
`arbiter-server-firstboot.service` starts:

```bash
install -m 0700 -d /etc/arbiter/secrets
./seal-secrets.sh
```

The script generates random values unless plaintext files already exist, seals
each with `systemd-creds encrypt --name=<name> --with-key=host+tpm2`, verifies
the round-trip, and deletes the plaintext. Existing `.cred` files are never
overwritten.

Remote unlock note: `--with-key=host+tpm2` binds the ciphertext to this machine's
TPM. If the disk is moved to another host, decryption fails — that is intended.
On hosts without a usable TPM use `--with-key=host` (machine-id bound, weaker)
and record the deviation. Never use `--with-key=auto-initrd` for these secrets;
firstboot runs after the initrd.

## What this protects against

| Threat | Demo | Production |
|---|---|---|
| Unprivileged local user reads secrets | no (0600 files, podman secrets) | no |
| Jenkins/build-log reader sees secrets | no (nothing printed) | no |
| Stolen disk yields credentials | yes | no (TPM-sealed, never written plaintext) |
| Root on the running host | yes | yes (by design) |

## Rotation

1. Seal new values under new names or remove the old `.cred` first: the script
   skips existing files.
2. `podman secret rm arbiter-hub-db-password arbiter-hub-admin-password`
3. Remove the decrypted plaintext in `/etc/arbiter/secrets/` and the stamp
   `/var/lib/arbiter/.server-firstboot-complete` only if you intend firstboot to
   re-provision. Rotating the DB password also requires `ALTER ROLE arbiter`
   inside Postgres first, otherwise the API locks out.

Rotation is not automated; treat it as a maintenance window.

## Verification

```bash
ls -l /etc/arbiter/secrets            # dir 0700, *.cred 0600
systemd-creds decrypt --name=db_password --with-key=host+tpm2 \
  /etc/arbiter/secrets/db_password.cred - | wc -c   # non-zero
podman secret ls | grep arbiter-hub                # both present after firstboot
systemctl cat arbiter-hub-api | grep -i password   # must print nothing
```
