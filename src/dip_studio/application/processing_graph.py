"""Executable non-destructive processing graph.

The document's ``AppliedOperation`` history is intentionally only audit
metadata.  This module provides the separate executable representation needed
for preview/evaluation without changing the document model.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from dip_studio.core.cancellation import CancellationToken, ProgressReporter
from dip_studio.processing.contracts import ProcessingRequest

if TYPE_CHECKING:
    from dip_studio.processing.engine import ProcessingEngine


@dataclass(frozen=True, slots=True)
class OperationNode:
    """One executable processor invocation in a graph."""

    id: str
    request: ProcessingRequest
    enabled: bool = True

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("Operation node id cannot be empty")


@dataclass(frozen=True, slots=True)
class ProcessingGraph:
    """An ordered, immutable chain of executable operation nodes."""

    nodes: tuple[OperationNode, ...] = ()

    def add(self, node: OperationNode) -> ProcessingGraph:
        if any(existing.id == node.id for existing in self.nodes):
            raise ValueError(f"Duplicate operation node id: {node.id}")
        return ProcessingGraph(self.nodes + (node,))

    def remove(self, node_id: str) -> ProcessingGraph:
        return ProcessingGraph(tuple(node for node in self.nodes if node.id != node_id))

    def set_enabled(self, node_id: str, enabled: bool) -> ProcessingGraph:
        found = False
        updated: list[OperationNode] = []
        for node in self.nodes:
            if node.id == node_id:
                found = True
                updated.append(OperationNode(node.id, node.request, enabled))
            else:
                updated.append(node)
        if not found:
            raise KeyError(f"Operation node not found: {node_id}")
        return ProcessingGraph(tuple(updated))

    def evaluate(
        self,
        image: str,
        engine: ProcessingEngine[str, str],
        *,
        cancellation: CancellationToken | None = None,
        progress: ProgressReporter | None = None,
        metadata: dict[str, object] | None = None,
        destructive: bool = False,
    ) -> str:
        """Evaluate enabled nodes in order and return the final buffer id.

        ``destructive`` is accepted for explicit non-destructive-to-destructive
        execution mode parity. The current engine remains buffer-safe by
        returning a new buffer_id for each operation unless the caller uses a
        processor that intentionally mutates the source buffer.
        """
        current = image
        enabled = tuple(node for node in self.nodes if node.enabled)
        for index, node in enumerate(enabled, start=1):
            if cancellation is not None:
                cancellation.throw_if_cancelled()
            if progress is not None:
                progress.report(index - 1, len(enabled), node.request.operation)
            current = engine.run(
                current,
                node.request,
                cancellation=cancellation,
                progress=progress,
                metadata={
                    **(metadata or {}),
                    "graph_node_id": node.id,
                    "graph_node_index": index - 1,
                    "destructive": destructive,
                },
            )
        if progress is not None:
            progress.report(len(enabled), len(enabled), "complete")
        return current
