from huiyang.domain.models import Base


def test_persistence_schema_contains_required_entities_and_task_fields() -> None:
    tables = Base.metadata.tables
    assert {"users", "projects", "tasks", "reminders", "conversation_memories"} <= set(
        tables
    )

    task_columns = set(tables["tasks"].columns.keys())
    assert {
        "id",
        "title",
        "original_instruction",
        "description",
        "assignee_id",
        "creator_id",
        "project_id",
        "visibility",
        "source_chat_id",
        "priority",
        "status",
        "deadline",
        "blocked_reason",
        "blocked_since",
        "created_at",
        "updated_at",
    } <= task_columns


def test_reference_memory_keeps_structured_resolution_data() -> None:
    columns = set(Base.metadata.tables["conversation_memories"].columns.keys())
    assert {
        "chat_id",
        "sender_id",
        "raw_message",
        "action_data",
        "resolved_task_ids",
        "resolved_project_id",
        "result_data",
        "scope",
        "expires_at",
        "created_at",
    } <= columns
