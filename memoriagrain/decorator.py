"""@remember decorator for memoriagrain.

Wraps any function that calls an LLM agent. Before the call, injects
the memoriagrain tool into the model's tool list. After the call, writes
the (prompt, answer) pair as a new atom.

Usage:
    @remember(backend="sqlite:///.memoriagrain.db")
    def my_agent(prompt: str) -> str:
        ...

The decorator inspects the wrapped function's signature to find the
prompt argument, auto-detects the tool injection strategy, and handles
atom persistence transparently.
"""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from memoriagrain.embeddings import embed, embedding_to_bytes
from memoriagrain.store.base import Atom, Store
from memoriagrain.store.sqlite import SQLiteStore
from memoriagrain.tool import recall_tool_definition


def _resolve_store(backend: str | None, store: Store | None) -> Store:
    """Resolve the storage backend from configuration.

    Args:
        backend: A connection string like 'sqlite:///path/to/db'.
        store: An explicit Store instance (takes precedence).

    Returns:
        A concrete Store implementation.
    """
    if store is not None:
        return store

    if backend is None:
        backend = "sqlite:///.memoriagrain/memoriagrain.db"

    if backend.startswith("sqlite://"):
        db_path = backend.replace("sqlite:///", "").replace("sqlite://", "")
        if not db_path:
            db_path = ".memoriagrain/memoriagrain.db"
        return SQLiteStore(db_path)

    if backend.startswith("foundry_iq:"):
        from memoriagrain.store.foundry_iq import FoundryIQStore

        kb_name = backend.split(":", 1)[1]
        return FoundryIQStore(kb_name=kb_name)

    # Default to SQLite
    return SQLiteStore(backend)


def remember(
    _func: Callable[..., Any] | None = None,
    backend: str | None = None,
    scope: str = "user",
    memory_budget: int = 500,
    store: Store | None = None,
    agent_id: str = "default",
    prompt_param: str = "prompt",
) -> Callable[..., Any]:
    """Decorator that wraps an agent function with memoriagrain memory.

    Injects the memoriagrain() tool into the agent's tool list and writes
    (prompt, answer) pairs as atoms after each call.

    Supports both ``@remember`` and ``@remember(backend=...)`` syntax.

    Args:
        _func: Internal sentinel — do not pass explicitly.
        backend: Connection string for the storage backend.
            'sqlite:///path' for SQLite, 'foundry_iq:kb_name' for Foundry IQ.
        scope: Memory scope -- 'user', 'agent', or 'global'.
        memory_budget: Maximum tokens of memory to inject per call.
        store: Explicit Store instance (overrides backend).
        agent_id: Agent identifier for cross-agent inheritance.
        prompt_param: Name of the prompt parameter in the wrapped function.

    Returns:
        A decorator that wraps the agent function.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        resolved_store = _resolve_store(backend, store)

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Extract the prompt from the function call
            prompt = _extract_prompt(func, args, kwargs, prompt_param)

            # Attach the tool definition and store to the function's namespace
            # so the agent can use it during execution
            wrapper._recall_store = resolved_store  # type: ignore[attr-defined]
            wrapper._recall_tool = recall_tool_definition()  # type: ignore[attr-defined]
            wrapper._recall_budget = memory_budget  # type: ignore[attr-defined]

            # Call the wrapped function
            result = func(*args, **kwargs)

            # Write the interaction as an atom
            answer = str(result) if result is not None else ""
            if prompt and answer and len(answer) >= 10:
                _write_atom(resolved_store, prompt, answer, agent_id)

            return result

        # Expose memoriagrain metadata on the wrapper
        wrapper._recall_store = resolved_store  # type: ignore[attr-defined]
        wrapper._recall_tool = recall_tool_definition()  # type: ignore[attr-defined]
        wrapper._recall_budget = memory_budget  # type: ignore[attr-defined]
        wrapper._recall_agent_id = agent_id  # type: ignore[attr-defined]

        return wrapper

    # Support bare @remember without parentheses
    if _func is not None:
        return decorator(_func)

    return decorator


def _extract_prompt(
    func: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    prompt_param: str,
) -> str:
    """Extract the prompt value from the function's arguments.

    Tries kwargs first, then positional args using inspect.
    """
    # Check kwargs
    if prompt_param in kwargs:
        return str(kwargs[prompt_param])

    # Try to match by position
    try:
        sig = inspect.signature(func)
        params = list(sig.parameters.keys())
        if prompt_param in params:
            idx = params.index(prompt_param)
            if idx < len(args):
                return str(args[idx])
    except (ValueError, TypeError):
        pass

    # Fallback: use first string argument
    for arg in args:
        if isinstance(arg, str) and len(arg) > 5:
            return arg

    return ""


def _write_atom(store: Store, prompt: str, answer: str, agent_id: str) -> None:
    """Write a prompt-answer pair as a new atom."""
    combined = f"{prompt} {answer}"
    vec = embed(combined)
    emb_bytes = embedding_to_bytes(vec)

    atom = Atom(
        prompt=prompt,
        answer=answer,
        embedding=emb_bytes,
        agent_id=agent_id,
        written_at=datetime.now(UTC),
    )
    store.write_atom(atom)
