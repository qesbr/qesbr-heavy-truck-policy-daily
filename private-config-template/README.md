# qesbr-heavy-truck-policy-daily-config

Private configuration for the public `qesbr-heavy-truck-policy-daily` workflow.

1. Keep this repository private.
2. Populate `recipients.yaml` with valid recipient addresses.
3. Create a fine-grained token with read-only **Contents** access to this repository only.
4. Store that token as `PRIVATE_CONFIG_TOKEN` in the public repository; set `PRIVATE_CONFIG_REPO` to `qesbr/qesbr-heavy-truck-policy-daily-config`.

Do not store SMTP credentials or API keys here; use GitHub Actions Secrets.
