import pytest
from uuid import NAMESPACE_URL, uuid5

from huiyang.team.model import apply_action, empty_board, project_status


def ident(value):
    return str(uuid5(NAMESPACE_URL, value))


def run(board, kind, actor="a", members=None, **fields):
    if "id" in fields:
        fields["id"] = ident(fields["id"])
    if fields.get("parent"):
        fields["parent"] = {**fields["parent"], "id": ident(fields["parent"]["id"])}
    return apply_action(board, {"type": kind, **fields}, actor, members or {"a", "b"})


def tree():
    b = run(empty_board(), "createProject", id="p", name="Project")
    b = run(b, "createTask", id="a", title="API", parent={"kind": "project", "id": "p"})
    return run(b, "createTask", actor="b", id="b", title="Page", parent={"kind": "task", "id": "a"})


def test_only_author_edits_but_every_member_moves_and_owner_deletes_descendants():
    b = tree()
    with pytest.raises(PermissionError):
        run(b, "status", actor="b", id="a", status="completed")
    moved = run(b, "move", actor="b", id="a", parent=None)
    assert moved["projects"] == []
    assert len(moved["tasks"]) == 2
    assert moved["tasks"][1]["parent"] == {"kind": "task", "id": ident("a")}
    assert run(b, "delete", id="a")["tasks"] == []
    assert len(b["tasks"]) == 2


def test_departed_author_tasks_are_shared_and_changes_survive_return():
    b = run(tree(), "editTask", actor="b", members={"b"}, id="a", title="Updated", description="Latest")
    b = run(b, "status", actor="b", members={"b"}, id="a", status="completed")
    assert b["tasks"][0]["owner"] == "a"
    assert b["tasks"][0]["title"] == "Updated"
    assert run(b, "status", id="a", status="pending")["tasks"][0]["description"] == "Latest"
    with pytest.raises(PermissionError):
        run(b, "status", actor="a", members={"b"}, id="a", status="completed")


def test_cycles_foreign_targets_and_unknown_fields_are_rejected():
    for parent in ({"kind": "task", "id": "b"}, {"kind": "project", "id": "other"}):
        with pytest.raises(ValueError):
            run(tree(), "move", id="a", parent=parent)
    with pytest.raises(ValueError):
        run(tree(), "createTask", id="x", title="x", parent=None, owner="b")


def test_project_cleanup_rename_and_completion_match_demo():
    b = run(empty_board(), "createProject", id="p", name="Empty")
    assert project_status(b, ident("p")) == "pending"
    with pytest.raises(PermissionError):
        run(b, "rename", id="p", name="No task")
    b = tree()
    b = run(b, "status", id="a", status="completed")
    b = run(b, "status", actor="b", id="b", status="discarded")
    assert project_status(b, ident("p")) == "completed"
    b = run(b, "status", id="a", status="pending")
    assert project_status(b, ident("p")) == "pending"
    assert run(b, "rename", actor="b", id="p", name="Renamed")["projects"][0]["name"] == "Renamed"


@pytest.mark.parametrize("bad_id", ["__proto__", "_staging", "constructor", "toString", "bad id"])
def test_unsafe_graph_identifiers_are_rejected(bad_id):
    with pytest.raises(ValueError):
        apply_action(empty_board(), {"type":"createTask","id":bad_id,"title":"x","parent":None}, "a", {"a"})
