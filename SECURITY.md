# Security Policy

## Scope

This tool downloads content from Coursera courses **your account is enrolled
in** into a local folder, and can optionally upload those files to Gemini
Notebook via the external `nlm` CLI. It reads:

- `~/.coursera-scraper/auth.json` — your Coursera `CAUTH` cookie.
- `~/.coursera-scraper/config.json` — optional defaults.
- `~/.notebooklm-mcp-cli/` — Google session cookies managed by `nlm`.

These files live outside the repository and are git-ignored.

## Reporting a vulnerability

Please report suspected vulnerabilities privately via GitHub's **Report a
vulnerability** (Security → Advisories) rather than a public issue.

## Handling of secrets

- Never commit `auth.json`, `config.json`, `downloads/`, or signed media URLs.
- Media URLs returned by the API are pre-signed and short-lived.
- Credentials are never logged and are only sent to Coursera / Google.

Use this tool only for content you are entitled to access. Do not redistribute
downloaded course material.
