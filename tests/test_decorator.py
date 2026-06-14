"""Tests for the @remember decorator."""

from __future__ import annotations

from recall.decorator import remember
from recall.store.sqlite import SQLiteStore
from recall.tool import recall_tool_definition


class TestRememberDecorator:
    """Test the @remember decorator."""

    def test_wraps_function(self, store: SQLiteStore) -> None:
        @remember(store=store)
        def my_agent(prompt: str) -> str:
            return f"Answer to: {prompt}"

        result = my_agent(prompt="What is recall?")
        assert "Answer to:" in result

    def test_tool_spec_injected(self, store: SQLiteStore) -> None:
        @remember(store=store)
        def my_agent(prompt: str) -> str:
            return "test answer that is long enough to be stored as atom"

        assert hasattr(my_agent, "_recall_tool")
        tool = my_agent._recall_tool
        assert tool["function"]["name"] == "recall"

    def test_atom_written_after_call(self, store: SQLiteStore) -> None:
        @remember(store=store, agent_id="test_agent")
        def my_agent(prompt: str) -> str:
            return "Authentication uses Azure AD with token-based auth."

        my_agent(prompt="How does authentication work?")

        atoms = list(store.all_atoms())
        assert len(atoms) == 1
        assert atoms[0].prompt == "How does authentication work?"
        assert atoms[0].agent_id == "test_agent"

    def test_short_answer_not_stored(self, store: SQLiteStore) -> None:
        @remember(store=store)
        def my_agent(prompt: str) -> str:
            return "Yes."

        my_agent(prompt="Is it working?")

        atoms = list(store.all_atoms())
        assert len(atoms) == 0  # Answer too short

    def test_preserves_function_metadata(self, store: SQLiteStore) -> None:
        @remember(store=store)
        def documented_agent(prompt: str) -> str:
            """This agent has documentation."""
            return "test answer long enough to be stored as a real atom"

        assert documented_agent.__doc__ == "This agent has documentation."
        assert documented_agent.__name__ == "documented_agent"

    def test_multiple_calls_write_multiple_atoms(self, store: SQLiteStore) -> None:
        @remember(store=store)
        def my_agent(prompt: str) -> str:
            return "A sufficiently long answer about the topic at hand."

        my_agent(prompt="Question one?")
        my_agent(prompt="Question two?")

        atoms = list(store.all_atoms())
        assert len(atoms) == 2


class TestRecallToolDefinition:
    """Test the tool definition spec."""

    def test_tool_spec_shape(self) -> None:
        tool = recall_tool_definition()
        assert tool["type"] == "function"

        func = tool["function"]
        assert func["name"] == "recall"
        assert "parameters" in func

        params = func["parameters"]
        assert "query" in params["properties"]
        assert "grain" in params["properties"]
        assert "max_tokens" in params["properties"]
        assert "query" in params["required"]
