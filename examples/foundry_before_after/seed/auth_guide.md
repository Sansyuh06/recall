# Foundry IQ Authentication Guide

Foundry IQ uses a token-based authentication system built on Azure
Active Directory. Every API call requires a bearer token.

## Getting Started

Install the Azure Identity library:

```
pip install azure-identity
```

Configure credentials using one of these methods:
1. Managed Identity (recommended for production)
2. Azure CLI: run `az login`
3. Environment variables: AZURE_CLIENT_ID, AZURE_TENANT_ID, AZURE_CLIENT_SECRET

## Token Management

Tokens expire after 60 minutes. The DefaultAzureCredential class handles
automatic refresh. If a 401 response is received, credentials are
re-acquired transparently.

## Required Permissions

- **Reader**: Search and retrieve documents
- **Contributor**: Write and delete documents
- **Admin**: Create and manage knowledge bases
