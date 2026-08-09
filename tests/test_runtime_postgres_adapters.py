from cody.core.runtime import (
    PostgresRunStore,
    PostgresWorkflowControlState,
    RunRecord,
    RunStatus,
)


class FakeDatabase:
    def __init__(self):
        self.records = {}

    def upsert(self, kind, key, data, *, run_id=None, status=None):
        self.records[(kind, key)] = {
            "data": data,
            "run_id": run_id,
            "status": status,
        }

    def get(self, kind, key):
        record = self.records.get((kind, key))
        return record["data"] if record else None

    def mutate(self, kind, key, updater, *, run_id=None, status=None):
        updated = updater(self.get(kind, key))
        self.upsert(
            kind, key, updated, run_id=run_id,
            status=status(updated) if status else None,
        )
        return updated

    def list(self, kind, *, run_id=None, status=None, newest_first=False):
        records = [
            record for (record_kind, _), record in self.records.items()
            if record_kind == kind
            and (run_id is None or record["run_id"] == run_id)
            and (status is None or record["status"] == status)
        ]
        if newest_first:
            records.reverse()
        return [record["data"] for record in records]


def test_postgres_run_adapter_preserves_typed_records():
    store = PostgresRunStore(FakeDatabase())
    run = RunRecord(task="ship", run_id="run_pg", status=RunStatus.RUNNING)

    store.save_run(run)

    assert store.get_run("run_pg") == run
    assert store.list_runs(status=RunStatus.RUNNING) == [run]


def test_postgres_control_is_visible_across_store_instances():
    database = FakeDatabase()
    first = PostgresWorkflowControlState(database)
    second = PostgresWorkflowControlState(database)

    first.request_cancel("run_pg", before_node_id="deploy")

    assert second.should_cancel("run_pg", "test") is False
    assert second.should_cancel("run_pg", "deploy") is True
    second.clear_cancel("run_pg")
    assert first.should_cancel("run_pg", "deploy") is False
