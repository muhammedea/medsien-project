"""SQLite storage: the editable servers and one row per run (see docs/high-level-design.md, "Storage")."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Float, Integer, String, Text, create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

import engine as sim


class Base(DeclarativeBase):
    pass


class ServerRow(Base):
    __tablename__ = "servers"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    cpu_units_per_tick: Mapped[int] = mapped_column(Integer)
    mem_mb: Mapped[int] = mapped_column(Integer)
    rate_limit_per_sec: Mapped[int] = mapped_column(Integer)

    def to_spec(self) -> sim.ServerSpec:
        return sim.ServerSpec(self.id, self.cpu_units_per_tick, self.mem_mb, self.rate_limit_per_sec)


class RunRow(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[str] = mapped_column(String)  # ISO 8601, UTC
    status: Mapped[str] = mapped_column(String)  # pending | completed | failed
    # Effective config.
    execution_mode: Mapped[str] = mapped_column(String)
    placement: Mapped[str] = mapped_column(String)
    max_wait_ticks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_queue_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Where the requests came from: "sample" or "upload" (+ the uploaded file name).
    requests_source: Mapped[str] = mapped_column(String)
    requests_filename: Mapped[str | None] = mapped_column(String, nullable=True)
    # Summary counts for the run list; the full summary is in summary_json.
    total_requests: Mapped[int | None] = mapped_column(Integer, nullable=True)
    finished: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dropped: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_wait_ticks: Mapped[float | None] = mapped_column(Float, nullable=True)
    p95_wait_ticks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_hash: Mapped[str] = mapped_column(String, index=True)
    trace_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    engine_version: Mapped[str] = mapped_column(String)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class MetaRow(Base):
    """Small key/value table for one-time setup flags."""

    __tablename__ = "app_meta"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String)


def make_engine(db_path: Path) -> Engine:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})


def init_db(db_engine: Engine, fixtures_dir: Path) -> sessionmaker[Session]:
    """Create the tables and, on first start only, seed the servers from fixtures/servers.json.

    Seeding is recorded in app_meta, so deleting every server and restarting does not bring
    the fixture servers back.
    """
    Base.metadata.create_all(db_engine)
    factory = sessionmaker(db_engine, expire_on_commit=False)
    with factory() as session:
        if session.get(MetaRow, "servers_seeded") is None:
            if session.scalars(select(ServerRow).limit(1)).first() is None:
                for spec in sim.load_servers(fixtures_dir / "servers.json"):
                    session.add(
                        ServerRow(
                            id=spec.id,
                            cpu_units_per_tick=spec.cpu_units_per_tick,
                            mem_mb=spec.mem_mb,
                            rate_limit_per_sec=spec.rate_limit_per_sec,
                        )
                    )
            session.add(MetaRow(key="servers_seeded", value="1"))
            session.commit()
    return factory
