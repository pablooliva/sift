# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability, please **do not** open a public
GitHub issue. Instead, contact the maintainer directly via GitHub's private
security reporting feature (Security → Report a vulnerability) or by email
if listed on the profile.

We will acknowledge receipt within 48 hours and aim to resolve confirmed
vulnerabilities within 30 days.

---

## Security Posture

### Zero Authentication by Default

**sift is designed for home-network or single-user deployments.**

By default, all services bind to `0.0.0.0` with **no authentication**:

| Service | Port | Auth |
|---------|------|------|
| txtai API | 8300 | None |
| Streamlit frontend | 8501 | None |
| Qdrant | 6333 | None |
| PostgreSQL | 5432 | Password (default: `postgres`) |
| Neo4j | 7474 / 7687 | Password (set via `NEO4J_PASSWORD`) |

This is intentional for the primary use case: a personal knowledge base on a
home server, accessed only from devices on the same local network.

**Do not expose these ports to the public internet without additional
security controls.**

### Securing for Broader Deployments

If you need to deploy sift beyond a trusted local network:

**Option 1 — Bind to localhost only**

Edit `docker-compose.yml` to publish ports only on `127.0.0.1`:

```yaml
ports:
  - "127.0.0.1:8300:8000"  # txtai API — localhost only
  - "127.0.0.1:8501:8501"  # Streamlit — localhost only
```

**Option 2 — Reverse proxy with authentication**

Place a reverse proxy (nginx, Caddy, Traefik) in front of the services.
Caddy example with HTTP basic auth:

```caddyfile
sift.example.com {
    basicauth {
        user $2a$14$...   # bcrypt hash
    }
    reverse_proxy localhost:8501
}
```

**Option 3 — Firewall rules**

Restrict port access at the OS or router level to specific source IPs.

### HTTPS

sift does not provide TLS by default. All traffic between the browser and the
Streamlit frontend, and between the frontend and txtai API, is unencrypted HTTP.

For any deployment accessible over a network you do not fully control, place a
TLS-terminating reverse proxy (nginx with Let's Encrypt, Caddy) in front of
the services.

### PostgreSQL Credentials

The default PostgreSQL credentials (`postgres`/`postgres`) are suitable for
local development only. For any networked deployment:

1. Set strong values in `.env`:
   ```
   POSTGRES_USER=myuser
   POSTGRES_PASSWORD=a-strong-random-password
   POSTGRES_DB=sift
   ```
2. Never commit `.env` to version control (it is gitignored by default).

### API Keys

The following API keys are stored in `.env` (gitignored):

- `TOGETHERAI_API_KEY` — Together AI for RAG queries
- `FIRECRAWL_API_KEY` — Firecrawl for web scraping (optional)

GitHub automatically scans public repositories for known API key patterns and
will alert you if a key is accidentally committed. This is a secondary safety
net — the primary protection is keeping `.env` gitignored.

### Network Architecture

The recommended deployment keeps all services on a private network segment.
The Streamlit frontend is the only intended public-facing endpoint:

```
[Browser] → [Streamlit :8501] → [txtai API :8300 — private]
                              → [Qdrant :6333 — private]
                              → [PostgreSQL :5432 — private]
                              → [Neo4j :7687 — private]
```

---

## Dependency Security

GitHub CodeQL and Trivy scans run automatically on push to `main` and weekly.
Known vulnerabilities in dependencies will appear in the Security tab.
