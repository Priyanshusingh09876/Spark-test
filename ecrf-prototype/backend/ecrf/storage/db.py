from contextlib import contextmanager

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from ecrf.config import config
from ecrf.storage.models import Base, ECRFVersion, Protocol

_engine = create_engine(
    config.database_url,
    connect_args={"check_same_thread": False} if config.database_url.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(_engine)


@contextmanager
def session() -> Session:
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def get_session():
    """FastAPI dependency."""
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def latest_version(s: Session, protocol_id: int) -> ECRFVersion | None:
    return s.scalars(
        select(ECRFVersion)
        .where(ECRFVersion.protocol_id == protocol_id)
        .order_by(ECRFVersion.version.desc())
        .limit(1)
    ).first()


def save_version(s: Session, protocol: Protocol, content: dict, created_by: str,
                 note: str | None = None) -> ECRFVersion:
    """Insert a NEW version row. Never updates an existing one."""
    prev = latest_version(s, protocol.id)
    v = ECRFVersion(
        protocol_id=protocol.id,
        protocol_hash=protocol.text_hash,
        version=(prev.version + 1) if prev else 1,
        content=content,
        created_by=created_by,
        note=note,
    )
    s.add(v)
    s.flush()
    return v
