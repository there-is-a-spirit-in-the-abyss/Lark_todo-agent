from datetime import UTC, datetime
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from huiyang.domain.models import Task, TaskVisibility
from huiyang.domain.persistence import User, Reminder
from huiyang.team.tables import TeamSpace


def test_team_migration_preserves_personal_records_and_starts_empty(tmp_path, monkeypatch):
    path=tmp_path/"migration.sqlite"
    monkeypatch.setenv("DATABASE_URL","sqlite+aiosqlite:///"+str(path))
    config=Config("alembic.ini")
    command.upgrade(config,"a471b85c2190")
    engine=create_engine("sqlite:///"+str(path))
    uid,tid,rid=uuid4(),uuid4(),uuid4()
    with Session(engine) as s:
        s.add(User(id=uid,feishu_user_id="personal",display_name="本人"))
        s.flush()
        s.add(Task(id=tid,title="私人安排",original_instruction="保留",assignee_id=uid,
                   creator_id=uid,visibility=TaskVisibility.PERSONAL))
        s.flush()
        s.add(Reminder(id=rid,task_id=tid,scheduled_for=datetime(2030,1,1,tzinfo=UTC),
                       kind="custom",destination="private"))
        s.commit()
        before=[s.execute(select(table.__table__)).all() for table in (User,Task,Reminder)]
    command.upgrade(config,"head")
    command.check(config)
    with Session(engine) as s:
        after=[s.execute(select(table.__table__)).all() for table in (User,Task,Reminder)]
        assert before==after
        assert s.scalar(select(TeamSpace)) is None
    engine.dispose()
