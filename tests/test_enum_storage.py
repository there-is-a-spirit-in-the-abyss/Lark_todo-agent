from huiyang.domain.models import Base


def test_task_enums_persist_product_values_not_python_member_names() -> None:
    task_table = Base.metadata.tables["tasks"]

    assert task_table.c.status.type.enums == [
        "待办",
        "进行中",
        "阻塞",
        "已完成",
        "已取消",
    ]
    assert task_table.c.visibility.type.enums == ["personal", "team"]
