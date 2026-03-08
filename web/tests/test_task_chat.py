"""Tests for task chat WebSocket endpoint."""


def test_task_chat_ws_task_not_found(test_client, project_store):
    """WS /ws/chat/task/:id sends error and closes for nonexistent task"""
    with test_client.websocket_connect("/ws/chat/task/nonexistent") as ws:
        data = ws.receive_json()
        assert data["type"] == "error"
        assert "not found" in data["message"].lower()


def test_task_chat_ws_ping_pong(test_client, project_store, session_store):
    """WS /ws/chat/task/:id responds to ping with pong"""
    p = project_store.create_project(name="Test", workdir="/tmp")
    t = project_store.create_task(project_id=p.id, name="Chat Task", branch_name="feat-chat")
    # Give the task a session
    s = session_store.create_session(title="Task session", workdir="/tmp")
    project_store.set_task_session_id(t.id, s.id)

    with test_client.websocket_connect(f"/ws/chat/task/{t.id}") as ws:
        ws.send_json({"type": "ping"})
        data = ws.receive_json()
        assert data["type"] == "pong"
