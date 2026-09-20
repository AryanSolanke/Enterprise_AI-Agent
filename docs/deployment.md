# Deployment guide

## Security baseline

- Terminate TLS at the gateway and set `APP_ENV=production`.
- Use an approved OIDC issuer and store client secrets in the platform secret manager. Do not use development headers in production.
- Replace the local SQLite data volume with approved managed stores and enforce encryption, backups, retention, and residency policies there.
- Set an artifact bucket with private access and short-lived signed download URLs before exposing exports externally.
- Configure an escalation adapter and on-call ownership before enabling Legal or Privacy for users.

## Provider replacement boundaries

`services/retrieval/service.py` owns hybrid search and is the only module that reads chunks. An approved vector/keyword implementation must keep its retrieval-time `AccessController.require` check and metadata/version filters.

`services/domain_agents/service.py` owns answer construction. An LLM adapter must return the validated `AnswerPayload`, cite only chunks it received, and preserve the high-risk review thresholds.
