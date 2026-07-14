import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from graph.nodes import _stamp_events, _task_status_event
from models import TodoItem
from services.rag_engine import RAGEngine


class FakeCollection:
    def __init__(self, documents=None):
        self.documents = ["doc-a", "doc-b"] if documents is None else documents
        self.last_query_kwargs = None

    def count(self):
        return len(self.documents)

    def query(self, **kwargs):
        self.last_query_kwargs = kwargs
        return {"documents": [self.documents]}


class PipelineHelperTests(unittest.TestCase):
    def test_stamp_events_adds_run_id_without_mutating_original(self):
        events = [{"type": "status", "message": "ok"}]

        stamped = _stamp_events(events, "run-123")

        self.assertEqual(stamped[0]["run_id"], "run-123")
        self.assertNotIn("run_id", events[0])

    def test_stamp_events_preserves_existing_run_id(self):
        events = [{"type": "status", "run_id": "existing"}]

        stamped = _stamp_events(events, "new")

        self.assertEqual(stamped[0]["run_id"], "existing")

    def test_task_status_event_has_common_fields(self):
        task = TodoItem(id=7, title="T", intent="I", query="Q")

        event = _task_status_event(task, "completed", summary="done")

        self.assertEqual(event["type"], "task_status")
        self.assertEqual(event["task_id"], 7)
        self.assertEqual(event["status"], "completed")
        self.assertEqual(event["summary"], "done")


class RAGEngineQueryTests(unittest.TestCase):
    def make_engine(self, documents=None):
        engine = object.__new__(RAGEngine)
        engine._collection = FakeCollection(documents)
        return engine

    def test_query_filters_by_run_and_task(self):
        engine = self.make_engine()

        result = engine.query("question", top_k=5, task_id=3, run_id="run-1")

        self.assertEqual(result, "doc-a\n\n---\n\ndoc-b")
        self.assertEqual(
            engine._collection.last_query_kwargs["where"],
            {"$and": [{"task_id": 3}, {"run_id": "run-1"}]},
        )

    def test_query_filters_by_run_only(self):
        engine = self.make_engine()

        engine.query("question", run_id="run-1")

        self.assertEqual(
            engine._collection.last_query_kwargs["where"],
            {"run_id": "run-1"},
        )

    def test_query_returns_empty_when_collection_empty(self):
        engine = self.make_engine([])

        result = engine.query("question", task_id=1, run_id="run-1")

        self.assertEqual(result, "")
        self.assertIsNone(engine._collection.last_query_kwargs)


if __name__ == "__main__":
    unittest.main()
