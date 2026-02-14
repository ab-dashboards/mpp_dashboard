# Security Policy

## Supported scope
This project is maintained as a private/public dashboard automation toolkit. Security issues should be reported privately.

## Reporting a vulnerability
Please report vulnerabilities by opening a private security advisory or contacting maintainers directly. Avoid public disclosure before a fix is available.

## Secrets management
- Do not hardcode API keys, OAuth tokens, or secrets in source code.
- Use environment variables (local `.env` for development).
- Rotate compromised keys immediately.
- Review commit history if accidental secret exposure occurs and revoke credentials.
