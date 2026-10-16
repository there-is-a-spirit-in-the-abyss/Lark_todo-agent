from huiyang.i18n import t
from copy import deepcopy
from uuid import UUID


def empty_board():
    return {"version": 1, "projects": [], "tasks": []}


def _text(value, maximum):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise ValueError(t("请输入 1 至 {maximum} 个字符", maximum=maximum))
    return value.strip()


def _find(rows, row_id):
    for row in rows:
        if row["id"] == row_id:
            return row
    raise ValueError(t("任务或项目已不存在，请刷新"))


def project_of(board, task_id):
    tasks = {t["id"]: t for t in board["tasks"]}
    seen = set()
    while True:
        if task_id in seen:
            raise ValueError(t("连接不能形成循环"))
        seen.add(task_id)
        task = tasks.get(task_id)
        if task is None:
            raise ValueError(t("任务已不存在"))
        parent = task["parent"]
        if parent is None:
            return None
        if parent["kind"] == "project":
            _find(board["projects"], parent["id"])
            return parent["id"]
        task_id = parent["id"]


def subtree(board, task_id):
    _find(board["tasks"], task_id)
    children = {}
    for task in board["tasks"]:
        parent = task["parent"]
        if parent and parent["kind"] == "task":
            children.setdefault(parent["id"], []).append(task["id"])
    found, queue = set(), [task_id]
    while queue:
        current = queue.pop()
        if current in found:
            raise ValueError(t("连接不能形成循环"))
        found.add(current)
        queue.extend(children.get(current, []))
    return found


def project_tasks(board, project_id):
    return [t for t in board["tasks"] if project_of(board, t["id"]) == project_id]


def project_status(board, project_id):
    tasks = project_tasks(board, project_id)
    return "completed" if tasks and all(t["status"] != "pending" for t in tasks) else "pending"


def can_manage(task, actor, members):
    return actor in members and (task["owner"] == actor or task["owner"] not in members)


def apply_action(previous, action, actor, members):
    if actor not in members:
        raise PermissionError(t("你已不在此飞书群中"))
    allowed = {
        "createProject": {"type", "id", "name"},
        "createTask": {"type", "id", "title", "parent"},
        "rename": {"type", "id", "name"},
        "status": {"type", "id", "status"},
        "editTask": {"type", "id", "title", "description"},
        "move": {"type", "id", "parent"},
        "delete": {"type", "id"},
    }
    if not isinstance(action, dict) or not isinstance(action.get("type"), str):
        raise ValueError(t("无效操作"))
    kind = action["type"]
    if kind not in allowed or set(action) != allowed[kind]:
        raise ValueError(t("操作字段不正确"))
    board = deepcopy(previous)
    row_id = _text(action["id"], 100)
    try:
        if str(UUID(row_id)) != row_id:
            raise ValueError()
    except ValueError:
        raise ValueError(t("任务和项目必须使用有效 UUID 标识")) from None

    def parent(value):
        if value is None:
            return
        if (not isinstance(value, dict) or set(value) != {"kind", "id"}
                or value["kind"] not in ("project", "task")):
            raise ValueError(t("无效的连接位置"))
        _find(board["projects" if value["kind"] == "project" else "tasks"], value["id"])

    if kind.startswith("create"):
        if any(row["id"] == row_id for row in board["projects"] + board["tasks"]):
            raise ValueError(t("标识重复"))
        if kind == "createProject":
            if len(board["projects"]) >= 200:
                raise ValueError(t("项目数量已达上限"))
            board["projects"].append({"id": row_id, "name": _text(action["name"], 60), "everUsed": False})
        else:
            if len(board["tasks"]) >= 3000:
                raise ValueError(t("任务数量已达上限"))
            parent(action["parent"])
            board["tasks"].append({
                "id": row_id, "title": _text(action["title"], 100), "description": "",
                "owner": actor, "status": "pending", "parent": action["parent"],
            })
    elif kind == "rename":
        p = _find(board["projects"], row_id)
        if not any(can_manage(t, actor, members) for t in project_tasks(board, row_id)):
            raise PermissionError(t("只有项目当前任务负责人可以修改项目名称"))
        p["name"] = _text(action["name"], 60)
    else:
        task = _find(board["tasks"], row_id)
        if kind != "move" and not can_manage(task, actor, members):
            raise PermissionError(t("只有发布者可以维护此任务"))
        if kind == "status":
            if action["status"] not in ("pending", "completed", "discarded"):
                raise ValueError(t("无效的任务状态"))
            task["status"] = action["status"]
        elif kind == "editTask":
            task["title"] = _text(action["title"], 100)
            value = action["description"]
            if not isinstance(value, str) or len(value) > 2000:
                raise ValueError(t("任务备注最多 2000 个字符"))
            task["description"] = value.strip()
        elif kind == "move":
            parent(action["parent"])
            target = action["parent"]
            if target and target["kind"] == "task" and target["id"] in subtree(board, row_id):
                raise ValueError(t("不能接到自身或自己的后代"))
            task["parent"] = deepcopy(target)
        elif kind == "delete":
            removed = subtree(board, row_id)
            board["tasks"] = [t for t in board["tasks"] if t["id"] not in removed]
    for p in board["projects"]:
        if project_tasks(board, p["id"]):
            p["everUsed"] = True
    board["projects"] = [p for p in board["projects"] if not p["everUsed"] or any(
        t["parent"] == {"kind": "project", "id": p["id"]} for t in board["tasks"])]
    return board
