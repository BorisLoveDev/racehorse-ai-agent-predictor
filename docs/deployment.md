# Deployment Guide — Meridian Server

## Server

- Meridian (46.30.43.46), 2 vCPU, 4GB RAM, Ubuntu 24.04
- SSH: `ssh meridian`
- PaaS: Coolify (http://46.30.43.46:8000)

## Coolify Identifiers

- **Stake app UUID:** `y8k408og84488csc4gss4gws`
- **Project UUID:** `kw84s04sos8084840oks84og`
- **Build pack:** `dockercompose`
- **Git:** `BorisLoveDev/racehorse-ai-agent-predictor`, branch `main`

## Deploy Procedure

```
1. git push origin main
2. mcp__coolify__deploy(tag_or_uuid="y8k408og84488csc4gss4gws")
3. mcp__coolify__deployment(action="get", uuid="<deployment_uuid>")  # check status
4. mcp__coolify__application_logs(uuid="y8k408og84488csc4gss4gws", lines=30)  # verify
```

Build time: ~2 min (no Playwright). Image ~300MB.

## Pre-Deploy Checklist

- [ ] Tests pass: `pytest tests/stake/ -x -q`
- [ ] No other Coolify apps using the same Telegram bot token (check `docker ps | grep bot`)
- [ ] Env vars set in Coolify UI (not .env file): TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, OPENROUTER_API_KEY

## Env Vars (Coolify UI)

Stake bot reads `STAKE_*` env vars. In docker-compose, these reference base vars:
- `STAKE_TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}`
- `STAKE_OPENROUTER_API_KEY=${OPENROUTER_API_KEY}`
- `STAKE_PARSER__MODEL=${STAKE_PARSER_MODEL:-google/gemini-2.0-flash-001}`

Base vars (TELEGRAM_BOT_TOKEN etc.) must have values in Coolify UI. They were empty by default — fixed manually.

## Containers

3 containers: `racehorse-redis`, `racehorse-searxng`, `racehorse-stake`

## SearXNG External Access (clawdbot)

- Endpoint: `http://46.30.43.46:8888/search?q=QUERY&format=json`
- Restricted by iptables to `95.142.41.188`
- Persistence: `/etc/iptables/rules.v4` + systemd service

## Troubleshooting

**Bot not responding:**
1. Check logs: `mcp__coolify__application_logs(uuid="y8k408og84488csc4gss4gws", lines=50)`
2. Check no competing bot: `ssh meridian "docker ps | grep bot"`
3. Check env vars: `ssh meridian "docker exec <container> env | grep STAKE_"`

**Token invalid error:**
Base env vars (TELEGRAM_BOT_TOKEN) are empty in Coolify. Update via:
`mcp__coolify__env_vars(resource="application", action="update", uuid="y8k408og84488csc4gss4gws", ...)`

**SSH fallback:**
```bash
ssh meridian "docker logs $(docker ps --format '{{.Names}}' | grep stake)"
```
