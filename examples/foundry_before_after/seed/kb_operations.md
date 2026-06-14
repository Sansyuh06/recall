# Knowledge Base Operations

A knowledge base (KB) stores documents with semantic search capability.

## Creating a KB

POST to /v1/projects/{project}/kbs with name, embedding model, and
chunk configuration. Each KB belongs to a project.

## Writing Documents

POST to /v1/projects/{project}/kbs/{kb}/documents with content and
metadata. The embedding vector is computed automatically by the
configured model.

## Searching

POST to /v1/projects/{project}/kbs/{kb}/search with a query string
and optional filters. Returns ranked results with relevance scores.

## Best Practices

- Use metadata filters to scope searches by document type
- Set appropriate chunk sizes (512 tokens recommended)
- Monitor KB size and clean up stale documents regularly
- Share KBs across agents for knowledge reuse
