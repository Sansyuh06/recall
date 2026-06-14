"""memoriagrain -- Memory the AI agent can call as a tool.

Multi-grain, provenance-tracked, self-healing.
Backed by Microsoft Foundry IQ with SQLite fallback.
"""

from memoriagrain.decorator import remember
from memoriagrain.tool import handle_recall_call, recall_tool_definition

__version__ = "0.1.0"
__all__ = ["handle_recall_call", "recall_tool_definition", "remember"]
