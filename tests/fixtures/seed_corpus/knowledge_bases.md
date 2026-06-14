# Knowledge Base Management in Foundry IQ

A knowledge base (KB) in Foundry IQ is a structured collection of
documents that agents can query through semantic search. Each KB
has a schema, an embedding model, and access control policies.

## Creating a knowledge base

Knowledge bases are created through the Foundry IQ portal or via
the REST API. Each KB belongs to a project and inherits the project's
authentication and networking settings.

```
POST /v1/projects/{project}/kbs
{
  "name": "agent_memory",
  "description": "Shared memory for code review agents",
  "embedding_model": "text-embedding-3-small",
  "chunk_size": 512,
  "chunk_overlap": 64
}
```

## Document operations

Documents are the primary unit of storage. Each document has:
- An ID (auto-generated or user-provided)
- Content (the text to embed and search)
- Metadata (arbitrary JSON for filtering)
- Embedding vector (computed automatically by the KB's model)

### Writing documents

```
POST /v1/projects/{project}/kbs/{kb}/documents
{
  "id": "optional-custom-id",
  "content": "The document text to store",
  "metadata": {
    "type": "atom",
    "agent_id": "search_agent",
    "written_at": "2026-06-14T00:00:00Z"
  }
}
```

### Searching documents

Foundry IQ supports semantic search with optional metadata filters:

```
POST /v1/projects/{project}/kbs/{kb}/search
{
  "query": "How does authentication work?",
  "k": 5,
  "filter": {
    "type": "pattern"
  }
}
```

## Sharing across agents

Multiple agents can share a single KB by connecting with the same
project and KB name. Each agent writes documents with its own
agent_id in the metadata, allowing other agents to discover and
attribute inherited knowledge.

This is the foundation of memoriagrain's cross-agent learning: when
agent B searches the shared KB and finds documents written by
agent A, the inheritance line becomes visible in the response.
