from cody.core.runtime import RunEvent, RunEventType, RuntimeStoreBundle


def test_run_events_recursively_redact_secrets_before_storage():
    event = RunEvent(
        RunEventType.TOOL_CALL_STARTED,
        run_id="run_secret",
        payload={
            "args": {
                "api_key": "do-not-store",
                "headers": {"Authorization": "Bearer very-secret-token"},
                "note": "use sk-1234567890abcdef for test",
            }
        },
    )
    stores = RuntimeStoreBundle.in_memory()
    stores.trace_store.append(event)

    payload = stores.trace_store.list_events("run_secret")[0].payload
    assert payload["args"]["api_key"] == "<redacted>"
    assert payload["args"]["headers"]["Authorization"] == "<redacted>"
    assert payload["args"]["note"] == "use <redacted> for test"
