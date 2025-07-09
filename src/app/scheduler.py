from __future__ import annotations

from collections import defaultdict
from heapq import heappush, heappop
from typing import Dict, List, Set, Tuple
import graphlib

from .models import EmailInternal


class DependencyScheduler:
    """Runtime scheduler that enforces dependency ordering and deadlines.

    * During ``__init__`` we build:
        - ``deps_map``      : email_id -> set(dependency_ids)
        - ``dependents_map``: email_id -> set(child_ids)
      We immediately run ``graphlib.TopologicalSorter`` to detect cycles.

    * A min-heap (``_queue``) keyed by ``deadline_ns`` holds every email
      whose *unmet* dependency set is empty – i.e. ready for processing.

    Public API expected by orchestrator:
        get_ready_batch(count) -> List[EmailInternal]
        mark_done(email_id)    -> None
    """

    def __init__(self, emails: List[EmailInternal]):
        # Mapping structures
        self.deps_map: Dict[str, Set[str]] = {e.email_id: set(e.dependencies) for e in emails}
        self.dependents_map: Dict[str, Set[str]] = defaultdict(set)
        for eid, deps in self.deps_map.items():
            for parent in deps:
                self.dependents_map[parent].add(eid)

        # Validate acyclic graph
        try:
            graphlib.TopologicalSorter(self.deps_map).prepare()
        except graphlib.CycleError as exc:  # pragma: no cover – spec promises acyclic but be safe
            raise ValueError(f"Dependency cycle detected: {exc}") from exc

        # Ready queue initialisation
        self._queue: List[Tuple[int, str]] = []  # (deadline_ns, email_id)
        self._emails: Dict[str, EmailInternal] = {e.email_id: e for e in emails}

        for email in emails:
            if not self.deps_map[email.email_id]:
                heappush(self._queue, (email.deadline_ns, email.email_id))

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------

    def get_ready_batch(self, count: int = 1) -> List[EmailInternal]:
        """Pop up to *count* ready emails ordered by earliest deadline."""
        batch: List[EmailInternal] = []
        while self._queue and len(batch) < count:
            _, eid = heappop(self._queue)
            batch.append(self._emails[eid])
        return batch

    def mark_done(self, email_id: str) -> None:
        """Mark *email_id* as processed and enqueue any dependents now unblocked."""
        for child in self.dependents_map.get(email_id, set()):
            deps = self.deps_map[child]
            deps.discard(email_id)
            if not deps:
                child_email = self._emails[child]
                heappush(self._queue, (child_email.deadline_ns, child))

    # Convenience helpers (optional)
    def has_work(self) -> bool:  # retained for older orchestrator compatibility
        return bool(self._queue)

    # Legacy alias used by main.py
    def has_next(self) -> bool:  # noqa: D401
        return self.has_work()

    def pop_next(self) -> EmailInternal | None:
        batch = self.get_ready_batch(1)
        return batch[0] if batch else None 