"""Startup bootstrap, the always-on market clock, and season rollover."""
import logging
import random
import threading
import time
from datetime import timedelta

from sqlalchemy import delete, select

from . import config
from .bots import run_bots
from .db import MARKET_LOCK, Base, SessionLocal, engine
from .market import (
    active_season, advance_ipos, clear_batch, curve_params, expire_stale_orders, next_tick,
    portfolio_values, record_price, trader_count,
)
from .models import (
    Fill, HallOfFame, Holding, Order, Personality, PricePoint, Season, User, utcnow,
)
from .seed import BOTS, ROSTER

log = logging.getLogger("famex.engine")


def bootstrap() -> None:
    Base.metadata.create_all(engine)
    with MARKET_LOCK, SessionLocal() as db:
        now = utcnow()
        if active_season(db) is None and db.scalar(select(Season.id)) is None:
            db.add(Season(number=1, starts_at=now, ends_at=now + timedelta(weeks=config.SEASON_WEEKS),
                          status="active", expected_traders=config.DEFAULT_EXPECTED_TRADERS, traders_at_start=0))
            db.flush()
        if db.scalar(select(Personality.id)) is None:
            names = [(n, c) for c, ns in ROSTER.items() for n in ns]
            k, supply = curve_params(active_season(db).expected_traders, len(names))
            for name, cat in names:
                p = Personality(name=name, category=cat, status="live", p0=config.P0, k=k, supply=supply,
                                sold=0, listed_at=now)
                db.add(p)
                db.flush()
                record_price(db, p, now)
        for meta in BOTS:
            if db.scalar(select(User.id).where(User.username == meta["username"])) is None:
                db.add(User(username=meta["username"], email=meta["email"], bio=meta["bio"], is_bot=True,
                            bot_strategy=meta["strategy"], status="approved", cash_cents=config.SEED_CENTS,
                            created_at=now - timedelta(hours=random.randint(2, 30)), approved_at=now))
        db.commit()


def end_season(db, expected_traders: int, ends_at=None) -> Season:
    """Record the Hall of Fame, reset every balance, recalibrate every curve, start the next season."""
    now = utcnow()
    season = active_season(db)
    number = season.number if season else 0
    values = portfolio_values(db)
    users = {u.id: u for u in db.scalars(select(User).where(User.status == "approved")).all()}
    ranked = sorted(values.items(), key=lambda kv: -kv[1]["net_worth"])
    for rank, (uid, v) in enumerate(ranked[:10], start=1):
        db.add(HallOfFame(season_number=number, user_id=uid, username=users[uid].username,
                          rank=rank, net_worth_cents=v["net_worth"]))
    if season:
        season.status = "ended"
        season.ends_at = now

    for o in db.scalars(select(Order).where(Order.status == "open")).all():
        o.status = "cancelled"
        o.closed_at = now
        o.hold_cents = 0
    db.execute(delete(Holding))
    db.execute(delete(PricePoint))
    db.execute(delete(Fill))

    # Players deferred by admins join now.
    for u in db.scalars(select(User).where(User.status == "deferred")).all():
        u.status = "approved"
        u.approved_at = now
    for u in db.scalars(select(User).where(User.status == "approved")).all():
        u.cash_cents = config.SEED_CENTS

    traders = max(expected_traders, trader_count(db))
    live = db.scalars(select(Personality).where(Personality.status.in_(["live", "ipo"]))).all()
    k, supply = curve_params(traders, len(live))
    for p in live:
        p.k, p.supply, p.sold, p.status, p.listed_at = k, supply, 0, "live", now
        record_price(db, p, now)
    for p in db.scalars(select(Personality).where(Personality.status == "queued")).all():
        p.k, p.supply = curve_params(traders, len(live) + 1)

    new = Season(number=number + 1, starts_at=now,
                 ends_at=ends_at or now + timedelta(weeks=config.SEASON_WEEKS),
                 status="active", expected_traders=expected_traders, traders_at_start=trader_count(db))
    db.add(new)
    db.flush()
    return new


class MarketClock(threading.Thread):
    """Clears a batch on every :00 and :30, then lets the house players decide. Runs forever."""

    def __init__(self):
        super().__init__(daemon=True, name="market-clock")
        self.stop = threading.Event()
        self.last_tick = None
        self.last_summary = {}

    def run(self):
        tick = next_tick()
        last_minute = None
        while not self.stop.is_set():
            now = utcnow()
            if now >= tick:
                try:
                    self._tick(tick)
                except Exception:  # keep the clock alive no matter what
                    log.exception("tick failed")
                tick = next_tick(utcnow())
            minute = now.replace(second=0, microsecond=0)
            if minute != last_minute:
                last_minute = minute
                try:
                    self._housekeeping()
                except Exception:
                    log.exception("housekeeping failed")
            self.stop.wait(0.25)

    def _tick(self, tick):
        with MARKET_LOCK, SessionLocal() as db:
            self.last_summary = clear_batch(db, tick)
            db.commit()
            self.last_tick = tick
            run_bots(db, tick)
            db.commit()

    def _housekeeping(self):
        with MARKET_LOCK, SessionLocal() as db:
            for e in advance_ipos(db):
                log.info(e)
            expire_stale_orders(db)
            db.commit()


clock = MarketClock()
