"""House players. They trade through the same order path as everyone else, see only public
prices (delayed a few minutes), keep human hours, and use round-dollar order sizes."""
import json
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config
from .market import (
    MarketError, avg_price, current_price, get_holding, ipo_commit, place_order, prices_as_of,
)
from .models import Holding, Order, Personality, Petition, User, Vote, utcnow
from .seed import BOTS

BOT_META = {b["username"]: b for b in BOTS}
ACT_PROBABILITY = 1 / 30      # per 30s tick while awake: roughly one decision every 15 minutes
SIZES = [100, 150, 200, 250, 300, 400, 500, 600, 750]
MIN_CASH = 20_000             # cents kept in reserve


def _awake(meta: dict, now: datetime) -> bool:
    local = now.replace(tzinfo=timezone.utc).astimezone(config.GAME_TZ)
    h = local.hour
    wake, sleep = meta.get("wake", 8), meta.get("sleep", 23)
    if sleep > 24:
        return h >= wake or h < sleep - 24
    return wake <= h < sleep


class Signals:
    """Price snapshots, deliberately a few minutes stale so bots never react instantly."""

    def __init__(self, db: Session, now: datetime):
        self.live = [p for p in db.scalars(select(Personality).where(Personality.status == "live")).all()]
        self.ipo = [p for p in db.scalars(select(Personality).where(Personality.status == "ipo")).all()]
        lag = now - timedelta(minutes=random.randint(5, 20))
        self.now = prices_as_of(db, lag)
        self.h1 = prices_as_of(db, lag - timedelta(hours=1))
        self.h6 = prices_as_of(db, lag - timedelta(hours=6))
        self.h24 = prices_as_of(db, lag - timedelta(hours=24))
        self.by_id = {p.id: p for p in self.live}

    def px(self, p: Personality) -> float:
        return self.now.get(p.id, current_price(p))

    def change(self, p: Personality, window: str) -> float:
        base = getattr(self, window).get(p.id, p.p0)
        return self.px(p) / base - 1 if base else 0.0


def _dollars(bot: User, low: int = 0) -> int:
    spendable = bot.cash_cents - MIN_CASH
    options = [s for s in SIZES if s * 100 <= spendable and s >= low]
    return random.choice(options) if options else 0


def _buy(db: Session, bot: User, p: Personality, dollars: int) -> bool:
    if dollars <= 0 or p.sold >= p.supply:
        return False
    est = avg_price(p, p.sold, 1)
    shares = max(1, int(dollars / est))
    shares = min(shares, p.supply - p.sold)
    limit = round(avg_price(p, p.sold, shares) * random.uniform(1.04, 1.12), 2)
    try:
        place_order(db, bot, p, "buy", shares, limit)
        return True
    except MarketError:
        return False


def _sell(db: Session, bot: User, h: Holding, p: Personality, fraction: float) -> bool:
    available = h.shares - h.locked
    shares = max(1, int(available * fraction))
    if available <= 0:
        return False
    shares = min(shares, available)
    limit = round(avg_price(p, p.sold, -shares) * random.uniform(0.88, 0.96), 2)
    try:
        place_order(db, bot, p, "sell", shares, limit)
        return True
    except MarketError:
        return False


def _gain(sig: Signals, h: Holding, p: Personality) -> float:
    if h.cost_cents <= 0 or h.shares <= 0:
        return 0.0
    return (sig.px(p) * h.shares * 100) / h.cost_cents - 1


def _holdings(db: Session, bot: User) -> list[Holding]:
    return db.scalars(select(Holding).where(Holding.user_id == bot.id, Holding.shares > 0)).all()


def _pick(seq, k=5):
    seq = list(seq)[:k]
    return random.choice(seq) if seq else None


# ---------------------------------------------------------------- strategies

def momentum(db, bot, sig, state):
    for h in _holdings(db, bot):
        p = sig.by_id.get(h.personality_id)
        if not p:
            continue
        if sig.change(p, "h1") < -0.06 or _gain(sig, h, p) > 0.5:
            if _sell(db, bot, h, p, random.choice([0.5, 1.0])):
                return
    risers = sorted([p for p in sig.live if sig.change(p, "h6") > 0.03 and p.sold < p.supply],
                    key=lambda p: -sig.change(p, "h6"))
    if not risers:
        risers = sorted([p for p in sig.live if p.sold < p.supply], key=lambda p: -sig.change(p, "h1"))
    p = _pick(risers)
    if p:
        _buy(db, bot, p, _dollars(bot))


def contrarian(db, bot, sig, state):
    for h in _holdings(db, bot):
        p = sig.by_id.get(h.personality_id)
        if p and _gain(sig, h, p) > 0.15 and random.random() < 0.6:
            if _sell(db, bot, h, p, 1.0):
                return
    dippers = sorted([p for p in sig.live if sig.change(p, "h24") < -0.05], key=lambda p: sig.change(p, "h24"))
    if not dippers:
        prices = sorted(sig.px(p) for p in sig.live)
        median = prices[len(prices) // 2] if prices else 0
        dippers = [p for p in sig.live if sig.px(p) <= median]
        random.shuffle(dippers)
    p = _pick(dippers)
    if p:
        _buy(db, bot, p, _dollars(bot))


def ipo_flipper(db, bot, sig, state):
    done = set(state.get("ipo_done", []))
    for p in sig.ipo:
        if p.id in done:
            continue
        cap = config.IPO_CAP_CENTS // 100
        dollars = min(int(cap * random.uniform(0.6, 1.0)) // 50 * 50, (bot.cash_cents - MIN_CASH) // 100)
        if dollars > 0:
            try:
                ipo_commit(db, bot, p, dollars)
            except MarketError:
                pass
        done.add(p.id)
        state["ipo_done"] = sorted(done)
        return
    for h in _holdings(db, bot):
        p = sig.by_id.get(h.personality_id)
        if not p:
            continue
        flipped = p.id in done
        age_days = (utcnow() - p.listed_at).days if p.listed_at else 99
        if flipped and (_gain(sig, h, p) > 0.25 or age_days >= 3):
            if _sell(db, bot, h, p, 0.5 if age_days < 3 else 1.0):
                return
        elif _gain(sig, h, p) > 0.3 or _gain(sig, h, p) < -0.15:
            if _sell(db, bot, h, p, 1.0):
                return
    if random.random() < 0.35:
        risers = sorted([p for p in sig.live if p.sold < p.supply], key=lambda p: -sig.change(p, "h6"))
        p = _pick(risers, 8)
        if p:
            _buy(db, bot, p, _dollars(bot) // 2)


def index(db, bot, sig, state):
    targets = [pid for pid in state.get("targets", []) if pid in sig.by_id]
    if len(targets) < 15:
        ranked = sorted(sig.live, key=lambda p: -(sig.px(p) * p.sold + random.random() * 50))
        for p in ranked:
            if p.id not in targets:
                targets.append(p.id)
            if len(targets) >= 15:
                break
        state["targets"] = targets
    holdings = {h.personality_id: h for h in _holdings(db, bot)}
    values = {pid: (sig.px(sig.by_id[pid]) * holdings[pid].shares if pid in holdings else 0) for pid in targets}
    total = sum(values.values()) + bot.cash_cents / 100
    for pid, v in values.items():
        if total and v / total > 0.15 and random.random() < 0.5:
            if _sell(db, bot, holdings[pid], sig.by_id[pid], 0.3):
                return
    under = sorted(targets, key=lambda pid: values[pid])
    pid = _pick(under, 4)
    if pid:
        size = random.choice([150, 200, 250, 300])
        if bot.cash_cents - MIN_CASH >= size * 100:
            _buy(db, bot, sig.by_id[pid], size)


def superfan(db, bot, sig, state):
    fav = BOT_META.get(bot.username, {}).get("fav", "Music")
    for h in _holdings(db, bot):
        p = sig.by_id.get(h.personality_id)
        if p and _gain(sig, h, p) > 0.6 and random.random() < 0.5:
            if _sell(db, bot, h, p, 0.33):
                return
    pool = [p for p in sig.live if p.category == fav and p.sold < p.supply]
    if random.random() < 0.15:
        pool = [p for p in sig.live if p.sold < p.supply]
    if not pool:
        return
    weights = [max(0.2, 1 + 5 * sig.change(p, "h24")) for p in pool]
    p = random.choices(pool, weights=weights, k=1)[0]
    _buy(db, bot, p, _dollars(bot))


STRATEGIES = {"momentum": momentum, "contrarian": contrarian, "ipo_flipper": ipo_flipper,
              "index": index, "superfan": superfan}


def _maybe_vote(db: Session, bot: User) -> None:
    petitions = db.scalars(select(Petition).where(Petition.status == "open")).all()
    if not petitions:
        return
    p = random.choice(petitions)
    vote = db.get(Vote, bot.id)
    if vote:
        vote.petition_id = p.id
        vote.created_at = utcnow()
    else:
        db.add(Vote(user_id=bot.id, petition_id=p.id))


def run_bots(db: Session, now: datetime) -> int:
    bots = db.scalars(select(User).where(User.is_bot.is_(True), User.status == "approved")).all()
    acting = []
    for bot in bots:
        meta = BOT_META.get(bot.username, {})
        if not _awake(meta, now):
            continue
        chance = ACT_PROBABILITY
        if bot.bot_strategy == "ipo_flipper":
            chance *= 1.5
        if random.random() < chance:
            acting.append(bot)
    if not acting:
        return 0
    sig = Signals(db, now)
    for bot in acting:
        try:
            state = json.loads(bot.bot_state or "{}")
        except ValueError:
            state = {}
        # Bots that already have an order waiting usually let it ride.
        waiting = db.scalar(select(Order.id).where(Order.user_id == bot.id, Order.status == "open"))
        if waiting and random.random() < 0.7:
            continue
        STRATEGIES.get(bot.bot_strategy, momentum)(db, bot, sig, state)
        if random.random() < 0.03:
            _maybe_vote(db, bot)
        bot.bot_state = json.dumps(state)
    return len(acting)
