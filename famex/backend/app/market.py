"""Market engine: bonding-curve math, order holds, 30-second batch clearing, IPOs, valuation.

Price curve (linear):   price(s) = p0 + k * s,   s = shares currently held by players.
Moving the curve from s to s + d costs exactly d * (p0 + k * (s + d/2)), so a batch
that clears every participant at that average price keeps the money supply balanced.
"""
import math
from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import config
from .models import (
    Fill, Holding, Order, Personality, PricePoint, Season, User, utcnow,
)


class MarketError(Exception):
    pass


# ---------------------------------------------------------------- curve math

def curve_params(traders: int, personalities: int, seed_dollars: float | None = None,
                 p0: float | None = None) -> tuple[float, int]:
    """Slope k and share supply for one Personality.

    k: the money needed to double a price is about 2x the average money per name.
    supply: sized so all the money in the game piled into one name roughly sells it out.
    """
    m = seed_dollars if seed_dollars is not None else config.SEED_CENTS / 100
    p0 = p0 if p0 is not None else config.P0
    n = max(1, traders)
    p = max(1, personalities)
    k = 0.75 * p0 * p0 * p / (n * m)
    supply = 1.6 * n * m / (p0 * math.sqrt(p))
    supply = max(1000, int(round(supply / 100.0)) * 100)
    return k, supply


def price_at(p: Personality, sold: int | None = None) -> float:
    s = p.sold if sold is None else sold
    return p.p0 + p.k * s


def current_price(p: Personality) -> float:
    return p.p0 if p.status in ("ipo", "queued") else price_at(p)


def avg_price(p: Personality, from_sold: int, delta: int) -> float:
    """Average price per share for moving the curve by `delta` shares."""
    return p.p0 + p.k * (from_sold + delta / 2.0)


def estimate(p: Personality, side: str, shares: int) -> float:
    if p.status != "live":
        return p.p0
    if side == "buy":
        shares = min(shares, max(0, p.supply - p.sold))
        return avg_price(p, p.sold, shares)
    return avg_price(p, p.sold, -min(shares, p.sold))


def liquidation_cents(p: Personality, shares: int) -> int:
    """Value of `shares` if sold alone along the curve right now."""
    if shares <= 0:
        return 0
    if p.status != "live":
        return int(round(shares * p.p0 * 100))
    h = min(shares, p.sold)
    return int(round(h * avg_price(p, p.sold, -h) * 100))


def next_tick(now: datetime | None = None) -> datetime:
    now = now or utcnow()
    secs = now.second + now.microsecond / 1e6
    base = now.replace(second=0, microsecond=0)
    add = config.TICK_SECONDS if secs < config.TICK_SECONDS else 2 * config.TICK_SECONDS
    return base + timedelta(seconds=add)


# ------------------------------------------------------------------- context

def active_season(db: Session) -> Season | None:
    return db.scalar(select(Season).where(Season.status == "active").order_by(Season.id.desc()))


def trader_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(User).where(User.status == "approved")) or 0


def calibration_traders(db: Session) -> int:
    season = active_season(db)
    expected = season.expected_traders if season else config.DEFAULT_EXPECTED_TRADERS
    return max(expected, trader_count(db))


def personality_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(Personality)
                     .where(Personality.status.in_(["live", "ipo", "queued"]))) or 0


def get_holding(db: Session, user_id: int, pid: int, create: bool = False) -> Holding | None:
    h = db.scalar(select(Holding).where(Holding.user_id == user_id, Holding.personality_id == pid))
    if h is None and create:
        h = Holding(user_id=user_id, personality_id=pid, shares=0, locked=0, cost_cents=0, ipo_spent_cents=0)
        db.add(h)
        db.flush()
    return h


def record_price(db: Session, p: Personality, ts: datetime | None = None) -> None:
    db.add(PricePoint(personality_id=p.id, ts=ts or utcnow(), price=round(current_price(p), 4), sold=p.sold))


# -------------------------------------------------------------------- orders

def place_order(db: Session, user: User, p: Personality, side: str, shares: int,
                limit_price: float | None = None) -> Order:
    if user.status != "approved":
        raise MarketError("Your account hasn't been approved yet.")
    if side not in ("buy", "sell"):
        raise MarketError("Side must be buy or sell.")
    if p.status == "ipo":
        raise MarketError(f"{p.name} is in its IPO window. Buy at the IPO price instead.")
    if p.status != "live":
        raise MarketError(f"{p.name} isn't trading yet.")
    if not isinstance(shares, int) or shares < 1:
        raise MarketError("Enter a whole number of shares, at least 1.")
    if shares > p.supply:
        raise MarketError(f"{p.name} only has {p.supply:,} shares in total.")

    est = estimate(p, side, shares)
    if limit_price is None:
        mult = 1 + config.DEFAULT_SLIPPAGE if side == "buy" else 1 - config.DEFAULT_SLIPPAGE
        limit_price = est * mult
    limit_price = round(max(0.01, float(limit_price)), 2)

    order = Order(user_id=user.id, personality_id=p.id, side=side, shares=shares,
                  limit_price=limit_price, status="open", created_at=utcnow())
    if side == "buy":
        if p.sold >= p.supply:
            raise MarketError(f"{p.name} is sold out. Wait for someone to sell.")
        hold = int(math.ceil(shares * limit_price * 100))
        if hold > user.cash_cents:
            raise MarketError(
                f"That order needs up to ${hold / 100:,.2f} set aside, and you have ${user.cash_cents / 100:,.2f} available.")
        user.cash_cents -= hold
        order.hold_cents = hold
    else:
        h = get_holding(db, user.id, p.id)
        available = (h.shares - h.locked) if h else 0
        if shares > available:
            raise MarketError(f"You have {available:,} shares of {p.name} available to sell.")
        h.locked += shares
    db.add(order)
    db.flush()
    return order


def _close_order(db: Session, o: Order, status: str, now: datetime) -> None:
    """Release whatever an unfilled order still holds."""
    if o.side in ("buy", "ipo"):
        if o.hold_cents:
            user = db.get(User, o.user_id)
            user.cash_cents += o.hold_cents
            o.hold_cents = 0
    else:
        remaining = o.shares - o.filled_shares
        if remaining > 0:
            h = get_holding(db, o.user_id, o.personality_id)
            if h:
                h.locked = max(0, h.locked - remaining)
    o.status = status
    o.closed_at = now


def cancel_order(db: Session, user: User, order_id: int) -> Order:
    o = db.get(Order, order_id)
    if not o or o.user_id != user.id:
        raise MarketError("Order not found.")
    if o.status != "open":
        raise MarketError("That order already closed.")
    _close_order(db, o, "cancelled", utcnow())
    return o


def expire_stale_orders(db: Session, now: datetime | None = None) -> int:
    now = now or utcnow()
    cutoff = now - timedelta(hours=config.ORDER_EXPIRY_HOURS)
    stale = db.scalars(select(Order).where(Order.status == "open", Order.side.in_(["buy", "sell"]),
                                           Order.created_at < cutoff)).all()
    for o in stale:
        _close_order(db, o, "expired", now)
    return len(stale)


# ------------------------------------------------------------- batch clearing

def clear_batch(db: Session, tick: datetime) -> dict:
    """Clear every open order placed before `tick`. Returns a summary per Personality."""
    orders = db.scalars(select(Order).where(Order.status == "open", Order.side.in_(["buy", "sell"]),
                                            Order.created_at < tick)
                        .order_by(Order.created_at, Order.id)).all()
    by_pid: dict[int, list[Order]] = defaultdict(list)
    for o in orders:
        by_pid[o.personality_id].append(o)

    summary = {}
    for pid, group in by_pid.items():
        p = db.get(Personality, pid)
        if p is None or p.status != "live":
            continue
        result = _clear_personality(db, p, group, tick)
        if result:
            summary[p.name] = result
    return summary


def _clear_personality(db: Session, p: Personality, group: list[Order], tick: datetime) -> dict | None:
    active = list(group)
    while True:
        buys = [o for o in active if o.side == "buy"]
        sells = [o for o in active if o.side == "sell"]
        b = sum(o.shares for o in buys)
        s = sum(o.shares for o in sells)
        if b == 0 and s == 0:
            return None
        remaining = p.supply - p.sold
        net = b - s
        buy_fill_total = b
        if net > remaining:
            net = remaining
            buy_fill_total = remaining + s
        avg = avg_price(p, p.sold, net)
        # Limit orders outside the clearing price sit out this batch and rest for the next one.
        out = [o for o in buys if o.limit_price + 1e-9 < avg] + \
              [o for o in sells if o.limit_price - 1e-9 > avg]
        if not out:
            break
        out_ids = {o.id for o in out}
        active = [o for o in active if o.id not in out_ids]

    avg = round(avg, 4)
    # Pro-rata buy fills when the batch would sell the Personality out.
    fills: dict[int, int] = {}
    if buy_fill_total < b:
        allotted = 0
        for o in buys:
            q = (o.shares * buy_fill_total) // b
            fills[o.id] = q
            allotted += q
        for o in buys:  # hand leftover shares to the earliest orders
            if allotted >= buy_fill_total:
                break
            if fills[o.id] < o.shares:
                fills[o.id] += 1
                allotted += 1
    else:
        for o in buys:
            fills[o.id] = o.shares

    for o in buys:
        q = fills[o.id]
        user = db.get(User, o.user_id)
        cost = int(round(q * avg * 100))
        h = get_holding(db, o.user_id, p.id, create=True)
        if q > 0:
            h.shares += q
            h.cost_cents += cost
            db.add(Fill(order_id=o.id, user_id=o.user_id, personality_id=p.id, side="buy",
                        shares=q, price=avg, ts=tick))
        user.cash_cents += o.hold_cents - cost
        o.hold_cents = 0
        o.filled_shares = q
        o.fill_price = avg if q else None
        o.status = "filled" if q == o.shares else ("partial" if q > 0 else "soldout")
        o.closed_at = tick

    for o in sells:
        user = db.get(User, o.user_id)
        h = get_holding(db, o.user_id, p.id)
        proceeds = int(round(o.shares * avg * 100))
        basis_out = int(round(h.cost_cents * o.shares / h.shares)) if h.shares else 0
        h.cost_cents -= basis_out
        h.shares -= o.shares
        h.locked = max(0, h.locked - o.shares)
        user.cash_cents += proceeds
        db.add(Fill(order_id=o.id, user_id=o.user_id, personality_id=p.id, side="sell",
                    shares=o.shares, price=avg, ts=tick))
        o.filled_shares = o.shares
        o.fill_price = avg
        o.status = "filled"
        o.closed_at = tick

    p.sold += net
    record_price(db, p, tick)
    return {"bought": buy_fill_total, "sold": s, "net": net, "price": avg,
            "sold_out": p.sold >= p.supply}


# ----------------------------------------------------------------------- IPOs

# IPOs work as one big blind batch: during the window players commit dollars, and at the
# close everyone pays the same price, the curve's average over all the shares the IPO sells.
# The curve then opens at its marginal price, so IPO buyers start in the green (the "pop")
# and the money still balances exactly.

def ipo_clearing_price(p: Personality, total_dollars: float) -> tuple[float, int]:
    """Uniform IPO price and share count for `total_dollars` of commitments."""
    if total_dollars <= 0:
        return p.p0, 0
    price = (p.p0 + (p.p0 ** 2 + 2 * p.k * total_dollars) ** 0.5) / 2
    shares = total_dollars / price
    if shares > p.supply:
        shares = p.supply
        price = avg_price(p, 0, p.supply)
    return price, int(shares)


def ipo_committed_cents(db: Session, pid: int, user_id: int | None = None) -> int:
    q = select(func.sum(Order.hold_cents)).where(Order.personality_id == pid, Order.side == "ipo",
                                                 Order.status == "open")
    if user_id is not None:
        q = q.where(Order.user_id == user_id)
    return int(db.scalar(q) or 0)


def ipo_commit(db: Session, user: User, p: Personality, dollars_in: float) -> Order:
    if user.status != "approved":
        raise MarketError("Your account hasn't been approved yet.")
    if p.status != "ipo":
        raise MarketError(f"{p.name} isn't in an IPO window.")
    cents = int(round(float(dollars_in) * 100))
    if cents < 100:
        raise MarketError("Commit at least $1.")
    room = config.IPO_CAP_CENTS - ipo_committed_cents(db, p.id, user.id)
    if cents > room:
        raise MarketError(
            f"IPO commitments are capped at ${config.IPO_CAP_CENTS / 100:,.0f} per player. You have ${room / 100:,.2f} left.")
    if cents > user.cash_cents:
        raise MarketError(f"You have ${user.cash_cents / 100:,.2f} available.")
    user.cash_cents -= cents
    o = Order(user_id=user.id, personality_id=p.id, side="ipo", shares=0, limit_price=0,
              hold_cents=cents, status="open", created_at=utcnow())
    db.add(o)
    db.flush()
    return o


def settle_ipo(db: Session, p: Personality, now: datetime) -> None:
    orders = db.scalars(select(Order).where(Order.personality_id == p.id, Order.side == "ipo",
                                            Order.status == "open").order_by(Order.created_at)).all()
    total = sum(o.hold_cents for o in orders) / 100
    price, _ = ipo_clearing_price(p, total)
    alloc = {o.id: int((o.hold_cents / 100) / price) for o in orders}
    sold = sum(alloc.values())
    while sold > p.supply:  # trim the most recent allocations if rounding overshoots
        for o in reversed(orders):
            if alloc[o.id] > 0 and sold > p.supply:
                alloc[o.id] -= 1
                sold -= 1
    # Re-price on the whole shares actually sold, so the curve's books balance to the cent.
    final = avg_price(p, 0, sold) if sold else p.p0
    for o in orders:
        q = alloc[o.id]
        cost = int(round(q * final * 100))
        user = db.get(User, o.user_id)
        user.cash_cents += o.hold_cents - cost
        o.hold_cents = 0
        o.shares = o.filled_shares = q
        o.fill_price = round(final, 4) if q else None
        o.limit_price = round(final, 4)
        o.status = "filled" if q else "soldout"
        o.closed_at = now
        if q:
            h = get_holding(db, o.user_id, p.id, create=True)
            h.shares += q
            h.cost_cents += cost
            db.add(Fill(order_id=o.id, user_id=o.user_id, personality_id=p.id, side="ipo", shares=q,
                        price=round(final, 4), ts=now))
    p.sold = sold


def schedule_ipo(db: Session, name: str, category: str, opens_at: datetime, closes_at: datetime) -> Personality:
    if closes_at <= opens_at:
        raise MarketError("The IPO has to close after it opens.")
    existing = db.scalar(select(Personality).where(func.lower(Personality.name) == name.strip().lower()))
    if existing:
        raise MarketError(f"{name} is already on the exchange.")
    k, supply = curve_params(calibration_traders(db), personality_count(db) + 1)
    p = Personality(name=name.strip(), category=category, status="queued", p0=config.P0, k=k, supply=supply,
                    sold=0, ipo_opens_at=opens_at, ipo_closes_at=closes_at)
    db.add(p)
    db.flush()
    return p


def advance_ipos(db: Session, now: datetime | None = None) -> list[str]:
    now = now or utcnow()
    db.flush()
    events = []
    for p in db.scalars(select(Personality).where(Personality.status == "queued",
                                                  Personality.ipo_opens_at <= now)).all():
        p.status = "ipo"
        events.append(f"IPO opened: {p.name}")
    for p in db.scalars(select(Personality).where(Personality.status == "ipo",
                                                  Personality.ipo_closes_at <= now)).all():
        settle_ipo(db, p, now)
        p.status = "live"
        p.listed_at = now
        record_price(db, p, now)
        events.append(f"Listed: {p.name} opens at ${price_at(p):.2f} with {p.sold:,} shares held")
    return events


def default_ipo_window(now: datetime | None = None) -> tuple[datetime, datetime]:
    """Next Monday 2pm game time (at least an hour from now), open for 24 hours. Returns naive UTC."""
    from datetime import timezone
    now_local = (now or utcnow()).replace(tzinfo=timezone.utc).astimezone(config.GAME_TZ)
    days = (config.IPO_WEEKDAY - now_local.weekday()) % 7
    opens = (now_local + timedelta(days=days)).replace(hour=config.IPO_OPEN_HOUR, minute=0, second=0, microsecond=0)
    if opens <= now_local + timedelta(hours=1):
        opens += timedelta(days=7)
    closes = opens + timedelta(hours=config.IPO_WINDOW_HOURS)
    to_utc = lambda d: d.astimezone(timezone.utc).replace(tzinfo=None)
    return to_utc(opens), to_utc(closes)


# ----------------------------------------------------------------- valuation

def portfolio_values(db: Session, user_ids: list[int] | None = None) -> dict[int, dict]:
    """cash, reserved (open buy holds), holdings value (liquidation), net worth — all in cents."""
    pmap = {p.id: p for p in db.scalars(select(Personality)).all()}
    q = select(User).where(User.status == "approved")
    if user_ids is not None:
        q = select(User).where(User.id.in_(user_ids))
    users = db.scalars(q).all()
    ids = [u.id for u in users]
    out = {u.id: {"cash": u.cash_cents, "reserved": 0, "holdings": 0} for u in users}
    if not ids:
        return out
    for h in db.scalars(select(Holding).where(Holding.user_id.in_(ids), Holding.shares > 0)).all():
        out[h.user_id]["holdings"] += liquidation_cents(pmap[h.personality_id], h.shares)
    for uid, hold in db.execute(select(Order.user_id, func.sum(Order.hold_cents))
                                .where(Order.user_id.in_(ids), Order.status == "open")
                                .group_by(Order.user_id)).all():
        out[uid]["reserved"] = int(hold or 0)
    for v in out.values():
        v["net_worth"] = v["cash"] + v["reserved"] + v["holdings"]
    return out


def prices_as_of(db: Session, when: datetime) -> dict[int, float]:
    """Latest recorded price per Personality at or before `when`."""
    sub = (select(PricePoint.personality_id, func.max(PricePoint.ts).label("ts"))
           .where(PricePoint.ts <= when).group_by(PricePoint.personality_id).subquery())
    rows = db.execute(select(PricePoint.personality_id, PricePoint.price)
                      .join(sub, (PricePoint.personality_id == sub.c.personality_id) & (PricePoint.ts == sub.c.ts))).all()
    return {pid: price for pid, price in rows}
