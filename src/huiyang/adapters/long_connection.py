"""Official SDK receiver process. Commit inbox before acknowledging an event."""
import json
import logging

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from huiyang.config import Settings
from huiyang.domain.models import Base  # register metadata
from huiyang.domain.platform import FeishuInbox


def sync_url(url):
    parsed = make_url(url)
    driver = "postgresql+psycopg" if parsed.drivername.startswith("postgresql") else "sqlite"
    return parsed.set(drivername=driver)


def persist_event(engine, payload):
    header = payload.get("header") or {}
    if header.get("event_type") != "im.message.receive_v1":
        return
    event_id = header.get("event_id")
    if not event_id:
        raise ValueError("Missing event ID")
    with Session(engine) as session:
        if session.get(FeishuInbox, event_id) is not None:
            return
        session.add(FeishuInbox(event_id=event_id, payload=payload))
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            if session.get(FeishuInbox, event_id) is None:
                raise


def run():
    # This process owns the SDK event loop, separate from FastAPI's async loop.
    import lark_oapi as lark
    settings = Settings()
    settings.validate_feishu()
    engine = create_engine(sync_url(settings.database_url), pool_pre_ping=True,
                           connect_args={"connect_timeout": 2})
    def receive(event):
        persist_event(engine, json.loads(lark.JSON.marshal(event)))
    handler = lark.EventDispatcherHandler.builder("", "").register_p2_im_message_receive_v1(receive).build()
    client = lark.ws.Client(
        settings.feishu_app_id, settings.feishu_app_secret,
        event_handler=handler, log_level=lark.LogLevel.WARNING,
    )
    try:
        client.start()
    finally:
        engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    run()
