# API token validation failures

Area: api-security. Synthetic runbook for the fictional AccessGate service.

## Symptoms
Requests return HTTP 401 or 403 after a token, issuer, audience, or permission change. JWT signature validation may fail during signing-key rotation.

## Investigation
- Distinguish authentication failure from an authenticated request lacking permission.
- Compare expected issuer and audience with non-secret token metadata.
- Check token expiry and clock skew without recording raw bearer tokens.
- Inspect signing-key discovery and cache refresh behavior after rotation.

## Review before mitigation
- Never disable authentication or signature validation to restore traffic.
- Ask the identity owner to review the configuration and intended access scope.

## Verification
Confirm that valid callers succeed and invalid or unauthorized callers are still rejected. A successful privileged request alone is insufficient.
