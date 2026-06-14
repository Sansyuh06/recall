# Authentication in Foundry IQ

Foundry IQ uses a token-based authentication system built on top of
Azure Active Directory. Every API call requires a valid bearer token
obtained through the DefaultAzureCredential chain.

## How authentication works

When an agent connects to a Foundry IQ knowledge base, it first
obtains an access token from Azure AD using the project's managed
identity or the developer's personal credentials. The token is then
passed in the Authorization header of every HTTP request.

The credential chain tries these sources in order:
1. Environment variables (AZURE_CLIENT_ID, AZURE_TENANT_ID, AZURE_CLIENT_SECRET)
2. Managed Identity (when running in Azure)
3. Azure CLI credentials (az login)
4. Visual Studio Code credentials
5. Azure PowerShell credentials

## Token refresh

Tokens expire after 60 minutes. The DefaultAzureCredential automatically
handles refresh. If a request fails with 401, the credential will attempt
to obtain a new token before retrying.

## Required permissions

The service principal or managed identity needs the following role
assignments on the Foundry IQ resource:
- Foundry IQ Reader: for search and retrieval operations
- Foundry IQ Contributor: for write and delete operations
- Foundry IQ Admin: for knowledge base creation and schema changes

## Security considerations

Never store access tokens in source code or version control. Use
managed identities in production. For local development, use
`az login` or set environment variables in a `.env` file (excluded
from git via .gitignore).

The memoriagrain library respects the principle of least privilege: read-only
operations use only the Reader role, and write operations are explicitly
gated behind the Contributor role check.
