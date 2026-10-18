import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import config
from .auth import (
    COOKIE, EMAIL_RE, USERNAME_RE, admin_user, approved_user, create_session, current_user,
    hash_password, new_passphrase, optional_user, verify_password,
)
from .db import MARKET_LOCK, get_db
from .engine import bootstrap, clock, end_season
from .market import (
    MarketError, active_season, cancel_order, current_price, default_ipo_window, estimate, ipo_clearing_price,
    ipo_commit, ipo_committed_cents,
    liquidation_cents, next_tick, place_order, portfolio_values, prices_as_of, schedule_ipo, trader_count,
)
from .models import (
    Fill, HallOfFame, Holding, Invite, Order, Personality, Petition, PricePoint, SessionToken, User, Vote, utcnow,
)
from .seed import CATEGORIES

logging.basicConfig(level=logging.INFO)
app = FastAPI(title=config.APP_NAME)


@app.on_event("startup")
def _startup():
    bootstrap()
    if os.environ.get("DISABLE_CLOCK") != "1":
        clock.start()


@app.exception_handler(MarketError)
def _market_error(_: Request, exc: MarketError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


def iso(dt: datetime | None) -> str | None:
    return dt.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z") if dt else None


def dollars(cents: int) -> float:
    return round(cents / 100, 2)


def public_user(u: User) -> dict:
    return {
        "id": u.id, "username": u.username, "bio": u.bio, "is_admin": u.is_admin,
        "avatar_url": f"/api/users/{u.id}/avatar?v={u.avatar_version}" if u.avatar else None,
        "joined": iso(u.created_at),
    }


def personality_dict(p: Personality, changes: dict | None = None) -> dict:
    price = current_price(p)
    d = {
        "id": p.id, "name": p.name, "category": p.category, "status": p.status,
        "price": round(price, 2), "sold": p.sold, "supply": p.supply, "p0": p.p0, "k": p.k,
        "sold_out": p.status == "live" and p.sold >= p.supply,
        "market_cap": round(price * p.sold, 2),
        "ipo_opens_at": iso(p.ipo_opens_at), "ipo_closes_at": iso(p.ipo_closes_at),
        "listed_at": iso(p.listed_at),
    }
    if changes is not None:
        for key, base in changes.items():
            b = base.get(p.id)
            d[key] = round(price / b - 1, 4) if b else 0.0
    return d


# -------------------------------------------------------------------- auth

class SignupIn(BaseModel):
    passphrase: str
    username: str
    password: str
    email: str
    bio: str = Field(default="", max_length=160)


class LoginIn(BaseModel):
    username: str
    password: str


def _set_cookie(resp: Response, token: str):
    resp.set_cookie(COOKIE, token, httponly=True, samesite="lax", secure=config.SECURE_COOKIES,
                    max_age=60 * 60 * 24 * 120)


def me_dict(db: Session, u: User) -> dict:
    d = public_user(u)
    d.update({"email": u.email, "status": u.status, "cash": dollars(u.cash_cents)})
    if u.status == "approved":
        v = portfolio_values(db, [u.id]).get(u.id)
        d.update({"net_worth": dollars(v["net_worth"]), "reserved": dollars(v["reserved"]),
                  "holdings_value": dollars(v["holdings"])})
    return d


@app.post("/api/auth/signup")
def signup(body: SignupIn, resp: Response, db: Session = Depends(get_db)):
    code = body.passphrase.strip().lower()
    username = body.username.strip()
    if not USERNAME_RE.match(username):
        raise HTTPException(400, "Usernames are 3–24 letters, numbers, dots or underscores.")
    if len(body.password) < 8:
        raise HTTPException(400, "Use a password of at least 8 characters.")
    if not EMAIL_RE.match(body.email.strip()):
        raise HTTPException(400, "Enter a valid email address.")
    with MARKET_LOCK:
        if db.scalar(select(User.id).where(func.lower(User.username) == username.lower())):
            raise HTTPException(400, "That username is taken.")
        no_admin = db.scalar(select(User.id).where(User.is_admin.is_(True))) is None
        bootstrap_ok = bool(config.BOOTSTRAP_PASSPHRASE) and no_admin and \
            code == config.BOOTSTRAP_PASSPHRASE.strip().lower()
        invite = None
        if not bootstrap_ok:
            invite = db.scalar(select(Invite).where(func.lower(Invite.code) == code))
            if invite is None or invite.used_by is not None:
                raise HTTPException(400, "That passphrase isn't valid. Ask an admin for yours.")
        u = User(username=username, email=body.email.strip(), password_hash=hash_password(body.password),
                 bio=body.bio.strip(), status="pending", cash_cents=0)
        if bootstrap_ok:
            u.is_admin, u.status, u.cash_cents, u.approved_at = True, "approved", config.SEED_CENTS, utcnow()
        db.add(u)
        db.flush()
        if invite:
            invite.used_by, invite.used_at = u.id, utcnow()
        db.commit()
    _set_cookie(resp, create_session(db, u))
    return me_dict(db, u)


@app.post("/api/auth/login")
def login(body: LoginIn, resp: Response, db: Session = Depends(get_db)):
    u = db.scalar(select(User).where(func.lower(User.username) == body.username.strip().lower()))
    if not u or u.is_bot or not verify_password(body.password, u.password_hash):
        raise HTTPException(400, "That username and password don't match.")
    if u.status == "denied":
        raise HTTPException(403, "An admin declined this account.")
    _set_cookie(resp, create_session(db, u))
    return me_dict(db, u)


@app.post("/api/auth/logout")
def logout(resp: Response, request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get(COOKIE)
    if token:
        s = db.get(SessionToken, token)
        if s:
            db.delete(s)
            db.commit()
    resp.delete_cookie(COOKIE)
    return {"ok": True}


@app.get("/api/me")
def get_me(user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    if user is None or user.is_bot:
        return {"user": None}
    return {"user": me_dict(db, user)}


class ProfileIn(BaseModel):
    bio: str = Field(default="", max_length=160)
    email: str


@app.put("/api/me")
def update_me(body: ProfileIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not EMAIL_RE.match(body.email.strip()):
        raise HTTPException(400, "Enter a valid email address.")
    user.bio, user.email = body.bio.strip(), body.email.strip()
    db.commit()
    return me_dict(db, user)


@app.post("/api/me/avatar")
async def upload_avatar(file: UploadFile = File(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    if file.content_type not in ("image/png", "image/jpeg", "image/webp", "image/gif"):
        raise HTTPException(400, "Upload a PNG, JPEG, WebP or GIF image.")
    data = await file.read()
    if len(data) > 600_000:
        raise HTTPException(400, "Keep the image under 600 KB.")
    user.avatar, user.avatar_type = data, file.content_type
    user.avatar_version = (user.avatar_version or 0) + 1
    db.commit()
    return me_dict(db, user)


@app.get("/api/users/{uid}/avatar")
def get_avatar(uid: int, db: Session = Depends(get_db)):
    u = db.get(User, uid)
    if not u or not u.avatar:
        raise HTTPException(404, "No avatar.")
    return Response(content=u.avatar, media_type=u.avatar_type,
                    headers={"Cache-Control": "public, max-age=31536000, immutable"})


# ------------------------------------------------------------------ market

@app.get("/api/state")
def state(db: Session = Depends(get_db)):
    season = active_season(db)
    return {
        "app_name": config.APP_NAME, "server_time": iso(utcnow()), "next_tick": iso(next_tick()),
        "tick_seconds": config.TICK_SECONDS, "seed": dollars(config.SEED_CENTS),
        "ipo_cap": dollars(config.IPO_CAP_CENTS), "ipo_price": config.P0,
        "season": {"number": season.number, "starts_at": iso(season.starts_at), "ends_at": iso(season.ends_at)}
        if season else None,
        "last_tick": iso(clock.last_tick), "categories": CATEGORIES,
    }


@app.get("/api/market")
def market(db: Session = Depends(get_db)):
    now = utcnow()
    changes = {"change_1h": prices_as_of(db, now - timedelta(hours=1)),
               "change_24h": prices_as_of(db, now - timedelta(hours=24))}
    ps = db.scalars(select(Personality).where(Personality.status.in_(["live", "ipo", "queued"]))).all()
    holders = dict(db.execute(select(Holding.personality_id, func.count())
                              .where(Holding.shares > 0).group_by(Holding.personality_id)).all())
    volume = dict(db.execute(select(Fill.personality_id, func.sum(Fill.shares))
                             .where(Fill.ts >= now - timedelta(hours=24)).group_by(Fill.personality_id)).all())
    # 24h sparkline: one point per ~hour
    spark_rows = db.execute(select(PricePoint.personality_id, PricePoint.ts, PricePoint.price)
                            .where(PricePoint.ts >= now - timedelta(hours=24))
                            .order_by(PricePoint.ts)).all()
    sparks: dict[int, list] = {}
    for pid, ts, price in spark_rows:
        bucket = int((ts - (now - timedelta(hours=24))).total_seconds() // 3600)
        s = sparks.setdefault(pid, {})
        s[bucket] = price
    out = []
    for p in ps:
        d = personality_dict(p, changes)
        if p.status == "ipo":
            d["ipo"] = ipo_info(db, p)
        d["holders"] = holders.get(p.id, 0)
        d["volume_24h"] = int(volume.get(p.id) or 0)
        d["spark"] = [round(v, 2) for _, v in sorted(sparks.get(p.id, {}).items())]
        out.append(d)
    return {"personalities": out, "next_tick": iso(next_tick()), "server_time": iso(now)}


@app.get("/api/personalities/{pid}")
def personality(pid: int, user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    p = db.get(Personality, pid)
    if not p:
        raise HTTPException(404, "Not found.")
    now = utcnow()
    changes = {"change_1h": prices_as_of(db, now - timedelta(hours=1)),
               "change_24h": prices_as_of(db, now - timedelta(hours=24)),
               "change_7d": prices_as_of(db, now - timedelta(days=7))}
    d = personality_dict(p, changes)
    if p.status == "ipo":
        d["ipo"] = ipo_info(db, p)
    pts = db.execute(select(PricePoint.ts, PricePoint.price).where(PricePoint.personality_id == pid)
                     .order_by(PricePoint.ts)).all()
    # thin long histories to ~400 points
    step = max(1, len(pts) // 400)
    d["history"] = [{"t": iso(t), "p": round(pr, 2)} for t, pr in pts[::step]]
    if pts and (len(pts) - 1) % step:
        d["history"].append({"t": iso(pts[-1][0]), "p": round(pts[-1][1], 2)})
    rows = db.execute(select(Holding, User).join(User, User.id == Holding.user_id)
                      .where(Holding.personality_id == pid, Holding.shares > 0)
                      .order_by(Holding.shares.desc()).limit(10)).all()
    d["holders"] = db.scalar(select(func.count()).select_from(Holding)
                             .where(Holding.personality_id == pid, Holding.shares > 0)) or 0
    d["top_holders"] = [{"user": public_user(u), "shares": h.shares,
                         "pct": round(h.shares / p.supply, 4)} for h, u in rows]
    fills = db.execute(select(Fill, User).join(User, User.id == Fill.user_id)
                       .where(Fill.personality_id == pid).order_by(Fill.ts.desc()).limit(20)).all()
    d["recent"] = [{"user": u.username, "side": f.side, "shares": f.shares, "price": round(f.price, 2),
                    "ts": iso(f.ts)} for f, u in fills]
    if user and user.status == "approved":
        h = db.scalar(select(Holding).where(Holding.user_id == user.id, Holding.personality_id == pid))
        d["mine"] = {
            "shares": h.shares if h else 0, "locked": h.locked if h else 0,
            "cost": dollars(h.cost_cents) if h else 0,
            "value": dollars(liquidation_cents(p, h.shares)) if h else 0,
            "ipo_committed": dollars(ipo_committed_cents(db, pid, user.id)),
        }
    return d


@app.get("/api/personalities/{pid}/quote")
def quote(pid: int, side: str, shares: int, db: Session = Depends(get_db)):
    p = db.get(Personality, pid)
    if not p:
        raise HTTPException(404, "Not found.")
    shares = max(1, shares)
    est = estimate(p, side, shares)
    return {"estimate": round(est, 4), "total": round(est * shares, 2),
            "price_after": round(p.p0 + p.k * (p.sold + (shares if side == "buy" else -shares)), 2)}


class OrderIn(BaseModel):
    personality_id: int
    side: str
    shares: int
    limit_price: float | None = None


@app.post("/api/orders")
def create_order(body: OrderIn, user: User = Depends(approved_user), db: Session = Depends(get_db)):
    with MARKET_LOCK:
        db.refresh(user)
        p = db.get(Personality, body.personality_id)
        if not p:
            raise HTTPException(404, "Personality not found.")
        db.refresh(p)
        o = place_order(db, user, p, body.side, body.shares, body.limit_price)
        db.commit()
    return {"order": order_dict(o, p), "next_tick": iso(next_tick())}


@app.delete("/api/orders/{oid}")
def delete_order(oid: int, user: User = Depends(approved_user), db: Session = Depends(get_db)):
    with MARKET_LOCK:
        db.refresh(user)
        o = cancel_order(db, user, oid)
        db.commit()
    return {"ok": True, "status": o.status}


class IpoIn(BaseModel):
    personality_id: int
    dollars: float


@app.post("/api/ipo/commit")
def commit_ipo(body: IpoIn, user: User = Depends(approved_user), db: Session = Depends(get_db)):
    with MARKET_LOCK:
        db.refresh(user)
        p = db.get(Personality, body.personality_id)
        if not p:
            raise HTTPException(404, "Personality not found.")
        db.refresh(p)
        ipo_commit(db, user, p, body.dollars)
        db.commit()
    return {"ok": True}


def ipo_info(db: Session, p: Personality) -> dict:
    total = ipo_committed_cents(db, p.id) / 100
    price, shares = ipo_clearing_price(p, total)
    backers = db.scalar(select(func.count(func.distinct(Order.user_id))).where(
        Order.personality_id == p.id, Order.side == "ipo", Order.status == "open")) or 0
    return {"committed": round(total, 2), "est_price": round(price, 2), "est_shares": shares,
            "est_open": round(p.p0 + p.k * shares, 2), "backers": backers}


def order_dict(o: Order, p: Personality) -> dict:
    return {"id": o.id, "personality": {"id": p.id, "name": p.name}, "side": o.side, "shares": o.shares,
            "limit_price": o.limit_price, "status": o.status, "amount": dollars(o.hold_cents), "filled_shares": o.filled_shares,
            "fill_price": o.fill_price, "created_at": iso(o.created_at), "closed_at": iso(o.closed_at)}


@app.get("/api/portfolio")
def portfolio(user: User = Depends(approved_user), db: Session = Depends(get_db)):
    pmap = {p.id: p for p in db.scalars(select(Personality)).all()}
    holdings = []
    for h in db.scalars(select(Holding).where(Holding.user_id == user.id, Holding.shares > 0)).all():
        p = pmap[h.personality_id]
        holdings.append({"personality": personality_dict(p), "shares": h.shares, "locked": h.locked,
                         "cost": dollars(h.cost_cents), "value": dollars(liquidation_cents(p, h.shares))})
    holdings.sort(key=lambda x: -x["value"])
    orders = db.scalars(select(Order).where(Order.user_id == user.id)
                        .order_by(Order.created_at.desc()).limit(60)).all()
    return {"me": me_dict(db, user), "holdings": holdings,
            "orders": [order_dict(o, pmap[o.personality_id]) for o in orders], "next_tick": iso(next_tick())}


@app.get("/api/leaderboard")
def leaderboard(db: Session = Depends(get_db)):
    values = portfolio_values(db)
    users = {u.id: u for u in db.scalars(select(User).where(User.status == "approved")).all()}
    counts = dict(db.execute(select(Holding.user_id, func.count()).where(Holding.shares > 0)
                             .group_by(Holding.user_id)).all())
    rows = sorted(values.items(), key=lambda kv: -kv[1]["net_worth"])
    return {"seed": dollars(config.SEED_CENTS), "players": [
        {"rank": i + 1, "user": public_user(users[uid]), "net_worth": dollars(v["net_worth"]),
         "cash": dollars(v["cash"] + v["reserved"]), "positions": counts.get(uid, 0)}
        for i, (uid, v) in enumerate(rows)]}


@app.get("/api/players/{username}")
def player(username: str, db: Session = Depends(get_db)):
    u = db.scalar(select(User).where(func.lower(User.username) == username.lower(), User.status == "approved"))
    if not u:
        raise HTTPException(404, "Player not found.")
    v = portfolio_values(db, [u.id])[u.id]
    pmap = {p.id: p for p in db.scalars(select(Personality)).all()}
    holdings = []
    for h in db.scalars(select(Holding).where(Holding.user_id == u.id, Holding.shares > 0)).all():
        p = pmap[h.personality_id]
        holdings.append({"personality": {"id": p.id, "name": p.name, "category": p.category},
                         "shares": h.shares, "value": dollars(liquidation_cents(p, h.shares))})
    holdings.sort(key=lambda x: -x["value"])
    fills = db.execute(select(Fill, Personality).join(Personality, Personality.id == Fill.personality_id)
                       .where(Fill.user_id == u.id).order_by(Fill.ts.desc()).limit(15)).all()
    titles = db.scalars(select(HallOfFame).where(HallOfFame.user_id == u.id).order_by(HallOfFame.season_number)).all()
    return {"user": public_user(u), "net_worth": dollars(v["net_worth"]), "holdings": holdings,
            "recent": [{"personality": p.name, "pid": p.id, "side": f.side, "shares": f.shares,
                        "price": round(f.price, 2), "ts": iso(f.ts)} for f, p in fills],
            "finishes": [{"season": t.season_number, "rank": t.rank} for t in titles]}


@app.get("/api/feed")
def feed(db: Session = Depends(get_db)):
    rows = db.execute(select(Fill, User, Personality).join(User, User.id == Fill.user_id)
                      .join(Personality, Personality.id == Fill.personality_id)
                      .order_by(Fill.ts.desc(), Fill.id.desc()).limit(40)).all()
    return {"items": [{"user": u.username, "personality": p.name, "pid": p.id, "side": f.side,
                       "shares": f.shares, "price": round(f.price, 2), "ts": iso(f.ts)} for f, u, p in rows]}


@app.get("/api/hall-of-fame")
def hall_of_fame(db: Session = Depends(get_db)):
    rows = db.scalars(select(HallOfFame).order_by(HallOfFame.season_number.desc(), HallOfFame.rank)).all()
    seasons: dict[int, list] = {}
    for r in rows:
        seasons.setdefault(r.season_number, []).append(
            {"rank": r.rank, "username": r.username, "net_worth": dollars(r.net_worth_cents)})
    return {"seasons": [{"season": s, "standings": v} for s, v in seasons.items()]}


# ------------------------------------------------------- petitions & IPOs

class PetitionIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    category: str
    pitch: str = Field(default="", max_length=280)


def petitions_payload(db: Session, user: User | None) -> dict:
    counts = dict(db.execute(select(Vote.petition_id, func.count()).group_by(Vote.petition_id)).all())
    my_vote = db.get(Vote, user.id) if user else None
    rows = db.execute(select(Petition, User).join(User, User.id == Petition.created_by)
                      .where(Petition.status == "open")).all()
    open_ = sorted([{"id": pt.id, "name": pt.name, "category": pt.category, "pitch": pt.pitch,
                     "by": u.username, "created_at": iso(pt.created_at), "votes": counts.get(pt.id, 0)}
                    for pt, u in rows], key=lambda x: (-x["votes"], x["created_at"]))
    upcoming = db.scalars(select(Personality).where(Personality.status.in_(["queued", "ipo"]))
                          .order_by(Personality.ipo_opens_at)).all()
    recent = db.scalars(select(Personality).where(Personality.status == "live", Personality.ipo_closes_at.is_not(None))
                        .order_by(Personality.listed_at.desc()).limit(5)).all()
    ipos = []
    for p in upcoming:
        d = personality_dict(p)
        if p.status == "ipo":
            d["ipo"] = ipo_info(db, p)
        ipos.append(d)
    return {"open": open_, "my_vote": my_vote.petition_id if my_vote else None,
            "ipos": ipos,
            "recent_ipos": [personality_dict(p) for p in recent]}


@app.get("/api/petitions")
def petitions(user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    return petitions_payload(db, user)


@app.post("/api/petitions")
def create_petition(body: PetitionIn, user: User = Depends(approved_user), db: Session = Depends(get_db)):
    name = body.name.strip()
    if body.category not in CATEGORIES:
        raise HTTPException(400, "Pick one of the listed categories.")
    if db.scalar(select(Personality.id).where(func.lower(Personality.name) == name.lower())):
        raise HTTPException(400, f"{name} is already on the exchange.")
    if db.scalar(select(Petition.id).where(func.lower(Petition.name) == name.lower(), Petition.status == "open")):
        raise HTTPException(400, f"Someone already petitioned for {name}. Vote for it instead.")
    pt = Petition(name=name, category=body.category, pitch=body.pitch.strip(), created_by=user.id)
    db.add(pt)
    db.flush()
    vote = db.get(Vote, user.id)
    if vote:
        vote.petition_id, vote.created_at = pt.id, utcnow()
    else:
        db.add(Vote(user_id=user.id, petition_id=pt.id))
    db.commit()
    return petitions_payload(db, user)


@app.post("/api/petitions/{ptid}/vote")
def vote(ptid: int, user: User = Depends(approved_user), db: Session = Depends(get_db)):
    pt = db.get(Petition, ptid)
    if not pt or pt.status != "open":
        raise HTTPException(400, "That petition is closed.")
    v = db.get(Vote, user.id)
    if v:
        v.petition_id, v.created_at = ptid, utcnow()
    else:
        db.add(Vote(user_id=user.id, petition_id=ptid))
    db.commit()
    return petitions_payload(db, user)


@app.delete("/api/petitions/vote")
def unvote(user: User = Depends(approved_user), db: Session = Depends(get_db)):
    v = db.get(Vote, user.id)
    if v:
        db.delete(v)
        db.commit()
    return petitions_payload(db, user)


# ------------------------------------------------------------------- admin

def growth(db: Session) -> dict:
    season = active_season(db)
    baseline = max(season.traders_at_start, season.expected_traders) if season else trader_count(db)
    now = trader_count(db)
    return {"baseline": baseline, "traders": now,
            "growth": round(now / baseline - 1, 4) if baseline else 0.0, "limit": config.GROWTH_WARNING}


@app.get("/api/admin/overview")
def admin_overview(admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    pending = db.scalars(select(User).where(User.status.in_(["pending", "deferred"]), User.is_bot.is_(False))
                         .order_by(User.created_at)).all()
    invites = db.scalars(select(Invite).order_by(Invite.created_at.desc()).limit(200)).all()
    users = {u.id: u.username for u in db.scalars(select(User)).all()}
    bots = db.scalars(select(User).where(User.is_bot.is_(True))).all()
    values = portfolio_values(db)
    ranks = {uid: i + 1 for i, (uid, _) in enumerate(sorted(values.items(), key=lambda kv: -kv[1]["net_worth"]))}
    season = active_season(db)
    humans = db.scalars(select(User).where(User.is_bot.is_(False), User.status == "approved")
                        .order_by(User.username)).all()
    return {
        "pending": [dict(public_user(u), email=u.email, status=u.status, created_at=iso(u.created_at))
                    for u in pending],
        "players": [dict(public_user(u), email=u.email) for u in humans],
        "invites": [{"id": i.id, "code": i.code, "note": i.note, "created_at": iso(i.created_at),
                     "used_by": users.get(i.used_by), "used_at": iso(i.used_at)} for i in invites],
        "bots": [{"username": b.username, "strategy": b.bot_strategy, "rank": ranks.get(b.id),
                  "net_worth": dollars(values.get(b.id, {}).get("net_worth", 0))} for b in bots],
        "growth": growth(db),
        "season": {"number": season.number, "starts_at": iso(season.starts_at), "ends_at": iso(season.ends_at),
                   "expected_traders": season.expected_traders} if season else None,
        "default_ipo_window": [iso(x) for x in default_ipo_window()],
        "clock": {"last_tick": iso(clock.last_tick), "running": clock.is_alive()},
    }


class InviteIn(BaseModel):
    count: int = Field(default=1, ge=1, le=50)
    note: str = Field(default="", max_length=120)


@app.post("/api/admin/invites")
def create_invites(body: InviteIn, admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    made = []
    for _ in range(body.count):
        code = new_passphrase()
        while db.scalar(select(Invite.id).where(Invite.code == code)):
            code = new_passphrase()
        db.add(Invite(code=code, note=body.note.strip(), created_by=admin.id))
        made.append(code)
    db.commit()
    return {"codes": made}


@app.delete("/api/admin/invites/{iid}")
def delete_invite(iid: int, admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    i = db.get(Invite, iid)
    if i and i.used_by is None:
        db.delete(i)
        db.commit()
    return {"ok": True}


class ApproveIn(BaseModel):
    force: bool = False


@app.post("/api/admin/users/{uid}/approve")
def approve(uid: int, body: ApproveIn, admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    with MARKET_LOCK:
        u = db.get(User, uid)
        if not u or u.is_bot:
            raise HTTPException(404, "User not found.")
        if u.status == "approved":
            return {"ok": True}
        g = growth(db)
        after = (g["traders"] + 1) / g["baseline"] - 1 if g["baseline"] else 0
        if after > config.GROWTH_WARNING and not body.force:
            return JSONResponse(status_code=409, content={
                "detail": f"Approving now puts this season {after:.0%} above its starting size. "
                          f"Prices will run hot. Approve anyway, or defer them to next season.",
                "growth_after": round(after, 4)})
        u.status, u.cash_cents, u.approved_at = "approved", config.SEED_CENTS, utcnow()
        db.commit()
    return {"ok": True}


@app.post("/api/admin/users/{uid}/{action}")
def user_action(uid: int, action: str, admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    u = db.get(User, uid)
    if not u or u.is_bot:
        raise HTTPException(404, "User not found.")
    if action == "deny":
        u.status = "denied"
    elif action == "defer":
        u.status = "deferred"
    elif action == "make-admin":
        u.is_admin = True
    elif action == "remove-admin":
        if u.id == admin.id:
            raise HTTPException(400, "You can't remove your own admin access.")
        u.is_admin = False
    else:
        raise HTTPException(400, "Unknown action.")
    db.commit()
    return {"ok": True}


class ScheduleIn(BaseModel):
    opens_at: datetime | None = None
    closes_at: datetime | None = None


def _naive_utc(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def _window(db: Session, body: ScheduleIn) -> tuple[datetime, datetime]:
    if body.opens_at and body.closes_at:
        return _naive_utc(body.opens_at), _naive_utc(body.closes_at)
    opens, closes = default_ipo_window()
    taken = {p.ipo_opens_at for p in db.scalars(select(Personality).where(Personality.status.in_(["queued", "ipo"]))).all()}
    while opens in taken:  # one IPO per week
        opens += timedelta(days=7)
        closes += timedelta(days=7)
    return opens, closes


@app.post("/api/admin/petitions/{ptid}/schedule")
def schedule_petition(ptid: int, body: ScheduleIn, admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    with MARKET_LOCK:
        pt = db.get(Petition, ptid)
        if not pt or pt.status != "open":
            raise HTTPException(400, "That petition is closed.")
        opens, closes = _window(db, body)
        p = schedule_ipo(db, pt.name, pt.category, opens, closes)
        pt.status, pt.personality_id = "scheduled", p.id
        for v in db.scalars(select(Vote).where(Vote.petition_id == pt.id)).all():
            db.delete(v)
        db.commit()
    return petitions_payload(db, admin)


class DirectIpoIn(ScheduleIn):
    name: str = Field(min_length=2, max_length=80)
    category: str


@app.post("/api/admin/ipos")
def direct_ipo(body: DirectIpoIn, admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    if body.category not in CATEGORIES:
        raise HTTPException(400, "Pick one of the listed categories.")
    with MARKET_LOCK:
        opens, closes = _window(db, body)
        schedule_ipo(db, body.name, body.category, opens, closes)
        db.commit()
    return petitions_payload(db, admin)


@app.delete("/api/admin/ipos/{pid}")
def cancel_ipo(pid: int, admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    with MARKET_LOCK:
        p = db.get(Personality, pid)
        if not p or p.status != "queued":
            raise HTTPException(400, "Only IPOs that haven't opened yet can be cancelled.")
        pt = db.scalar(select(Petition).where(Petition.personality_id == pid))
        if pt:
            pt.status, pt.personality_id = "open", None
        db.delete(p)
        db.commit()
    return petitions_payload(db, admin)


@app.post("/api/admin/petitions/{ptid}/reject")
def reject_petition(ptid: int, admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    pt = db.get(Petition, ptid)
    if pt and pt.status == "open":
        pt.status = "rejected"
        for v in db.scalars(select(Vote).where(Vote.petition_id == pt.id)).all():
            db.delete(v)
        db.commit()
    return petitions_payload(db, admin)


class SeasonIn(BaseModel):
    expected_traders: int = Field(ge=5, le=1000)
    confirm: str


@app.post("/api/admin/season/end")
def admin_end_season(body: SeasonIn, admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    if body.confirm.strip().upper() != "END SEASON":
        raise HTTPException(400, "Type END SEASON to confirm.")
    with MARKET_LOCK:
        s = end_season(db, body.expected_traders)
        db.commit()
    return {"ok": True, "season": s.number}


# ------------------------------------------------------------------ frontend

STATIC_DIR = Path(os.environ.get("STATIC_DIR", Path(__file__).resolve().parents[2] / "frontend" / "dist"))
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Not found.")
        f = STATIC_DIR / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(STATIC_DIR / "index.html")
