from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text,
    UniqueConstraint, Index,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), default="")
    password_hash: Mapped[str] = mapped_column(String(255), default="")
    bio: Mapped[str] = mapped_column(String(280), default="")
    avatar: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    avatar_type: Mapped[str] = mapped_column(String(32), default="")
    avatar_version: Mapped[int] = mapped_column(Integer, default=0)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_bot: Mapped[bool] = mapped_column(Boolean, default=False)
    bot_strategy: Mapped[str] = mapped_column(String(32), default="")
    bot_state: Mapped[str] = mapped_column(Text, default="{}")
    # pending -> approved | denied | deferred (approve at next season)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    cash_cents: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Invite(Base):
    """A single-use passphrase an admin hands to one specific person."""
    __tablename__ = "invites"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    note: Mapped[str] = mapped_column(String(120), default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    used_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class SessionToken(Base):
    __tablename__ = "sessions"
    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Season(Base):
    __tablename__ = "seasons"
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[int] = mapped_column(Integer)
    starts_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    ends_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | ended
    expected_traders: Mapped[int] = mapped_column(Integer, default=30)
    traders_at_start: Mapped[int] = mapped_column(Integer, default=0)


class Personality(Base):
    __tablename__ = "personalities"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    category: Mapped[str] = mapped_column(String(40))
    # queued (IPO scheduled, not open yet) | ipo (window open) | live
    status: Mapped[str] = mapped_column(String(16), default="live")
    p0: Mapped[float] = mapped_column(Float, default=10.0)
    k: Mapped[float] = mapped_column(Float)
    supply: Mapped[int] = mapped_column(Integer)
    sold: Mapped[int] = mapped_column(Integer, default=0)
    ipo_opens_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ipo_closes_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    listed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Holding(Base):
    __tablename__ = "holdings"
    __table_args__ = (UniqueConstraint("user_id", "personality_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    personality_id: Mapped[int] = mapped_column(ForeignKey("personalities.id"), index=True)
    shares: Mapped[int] = mapped_column(Integer, default=0)
    locked: Mapped[int] = mapped_column(Integer, default=0)  # tied up in open sell orders
    cost_cents: Mapped[int] = mapped_column(Integer, default=0)  # cost basis of `shares`
    ipo_spent_cents: Mapped[int] = mapped_column(Integer, default=0)


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    personality_id: Mapped[int] = mapped_column(ForeignKey("personalities.id"), index=True)
    side: Mapped[str] = mapped_column(String(4))  # buy | sell
    shares: Mapped[int] = mapped_column(Integer)
    limit_price: Mapped[float] = mapped_column(Float)
    hold_cents: Mapped[int] = mapped_column(Integer, default=0)
    # open | filled | partial | cancelled | expired
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    filled_shares: Mapped[int] = mapped_column(Integer, default=0)
    fill_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Fill(Base):
    __tablename__ = "fills"
    __table_args__ = (Index("ix_fills_pid_ts", "personality_id", "ts"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    personality_id: Mapped[int] = mapped_column(ForeignKey("personalities.id"))
    side: Mapped[str] = mapped_column(String(4))  # buy | sell | ipo
    shares: Mapped[int] = mapped_column(Integer)
    price: Mapped[float] = mapped_column(Float)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class PricePoint(Base):
    __tablename__ = "price_points"
    __table_args__ = (Index("ix_pp_pid_ts", "personality_id", "ts"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    personality_id: Mapped[int] = mapped_column(ForeignKey("personalities.id"))
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    price: Mapped[float] = mapped_column(Float)
    sold: Mapped[int] = mapped_column(Integer)


class Petition(Base):
    __tablename__ = "petitions"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    category: Mapped[str] = mapped_column(String(40))
    pitch: Mapped[str] = mapped_column(String(280), default="")
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    # open | scheduled | rejected
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    personality_id: Mapped[int | None] = mapped_column(ForeignKey("personalities.id"), nullable=True)


class Vote(Base):
    """Each player backs one open petition at a time; switching moves the vote."""
    __tablename__ = "votes"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    petition_id: Mapped[int] = mapped_column(ForeignKey("petitions.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class HallOfFame(Base):
    __tablename__ = "hall_of_fame"
    id: Mapped[int] = mapped_column(primary_key=True)
    season_number: Mapped[int] = mapped_column(Integer)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    username: Mapped[str] = mapped_column(String(32))
    rank: Mapped[int] = mapped_column(Integer)
    net_worth_cents: Mapped[int] = mapped_column(Integer)
