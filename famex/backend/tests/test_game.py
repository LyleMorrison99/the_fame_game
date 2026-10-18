"""End-to-end check: signup with passphrases, approvals, trading, batch clearing, IPOs,
petitions, bots, season reset, and money conservation. Run: python -m pytest -q tests"""
import os
import random
import tempfile
from datetime import timedelta

DB = tempfile.mktemp(suffix=".db")
os.environ.update(DATABASE_URL=f"sqlite:///{DB}", DISABLE_CLOCK="1", BOOTSTRAP_PASSPHRASE="let-me-in",
                  SECURE_COOKIES="0")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app import bots, market  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Holding, Order, Personality, User, utcnow  # noqa: E402


def money_in_system(db) -> int:
    """Cash + order holds + money locked in curves must equal seed x approved players."""
    cash = sum(u.cash_cents for u in db.scalars(select(User).where(User.status == "approved")))
    holds = sum(o.hold_cents for o in db.scalars(select(Order).where(Order.status == "open")))
    curves = 0.0
    for p in db.scalars(select(Personality)):
        if p.status == "live":
            curves += p.p0 * p.sold + p.k * p.sold * p.sold / 2
        else:
            curves += p.p0 * p.sold
    return cash + holds + round(curves * 100)


def clear(db):
    tick = market.next_tick(utcnow() + timedelta(seconds=1))
    out = market.clear_batch(db, tick)
    db.commit()
    return out


def test_full_game():
    with TestClient(app) as c:
        admin = TestClient(app)
        r = admin.post("/api/auth/signup", json={"passphrase": "let-me-in", "username": "lyle",
                                                 "password": "hunter2hunter2", "email": "l@example.com",
                                                 "bio": "Commissioner"})
        assert r.status_code == 200 and r.json()["status"] == "approved", r.text
        codes = admin.post("/api/admin/invites", json={"count": 3, "note": "friends"}).json()["codes"]
        assert len(codes) == 3

        # bad passphrase, then good signups
        p1 = TestClient(app)
        assert p1.post("/api/auth/signup", json={"passphrase": "nope", "username": "amy", "password": "password123",
                                                 "email": "a@x.com"}).status_code == 400
        assert p1.post("/api/auth/signup", json={"passphrase": codes[0].upper(), "username": "amy",
                                                 "password": "password123", "email": "a@x.com"}).status_code == 200
        p2 = TestClient(app)
        assert p2.post("/api/auth/signup", json={"passphrase": codes[1], "username": "ben",
                                                 "password": "password123", "email": "b@x.com"}).status_code == 200
        # passphrase can't be reused
        assert TestClient(app).post("/api/auth/signup", json={"passphrase": codes[1], "username": "cat",
                                    "password": "password123", "email": "c@x.com"}).status_code == 400
        # pending players can't trade
        assert p1.post("/api/orders", json={"personality_id": 1, "side": "buy", "shares": 5}).status_code == 403
        pend = admin.get("/api/admin/overview").json()["pending"]
        for u in pend:
            assert admin.post(f"/api/admin/users/{u['id']}/approve", json={}).status_code == 200
        # avatar
        png = b"\x89PNG\r\n\x1a\n" + b"0" * 100
        assert p1.post("/api/me/avatar", files={"file": ("a.png", png, "image/png")}).status_code == 200

        m = c.get("/api/market").json()["personalities"]
        assert len(m) == 100
        swift = next(p for p in m if p["name"] == "Taylor Swift")
        # bots must not be identifiable through public endpoints
        lb = c.get("/api/leaderboard").json()["players"]
        assert len(lb) == 8 and all("is_bot" not in p["user"] and "bot" not in str(p) for p in lb)

        with SessionLocal() as db:
            start_money = money_in_system(db)
            assert start_money == 8 * 1_000_000

        # same batch: two buyers and a seller get one price
        assert p1.post("/api/orders", json={"personality_id": swift["id"], "side": "buy", "shares": 100}).status_code == 200
        assert p2.post("/api/orders", json={"personality_id": swift["id"], "side": "buy", "shares": 50,
                                                 "limit_price": 20}).status_code == 200
        with SessionLocal() as db:
            clear(db)
        assert p2.post("/api/orders", json={"personality_id": swift["id"], "side": "sell", "shares": 20}).status_code == 200
        assert p1.post("/api/orders", json={"personality_id": swift["id"], "side": "buy", "shares": 40}).status_code == 200
        with SessionLocal() as db:
            summary = clear(db)
            assert summary["Taylor Swift"]["net"] == 20
            assert abs(money_in_system(db) - start_money) <= 50
        orders = p1.get("/api/portfolio").json()["orders"]
        o2 = p2.get("/api/portfolio").json()["orders"]
        assert orders[0]["fill_price"] == o2[0]["fill_price"]  # same batch, same price

        # tight limit rests instead of filling
        r = p1.post("/api/orders", json={"personality_id": swift["id"], "side": "buy", "shares": 10, "limit_price": 1})
        assert r.status_code == 200
        with SessionLocal() as db:
            clear(db)
        assert p1.get("/api/portfolio").json()["orders"][0]["status"] == "open"
        oid = p1.get("/api/portfolio").json()["orders"][0]["id"]
        assert p1.delete(f"/api/orders/{oid}").status_code == 200

        # overspending and overselling are refused
        assert p1.post("/api/orders", json={"personality_id": 2, "side": "buy", "shares": 5000}).status_code == 400
        assert p2.post("/api/orders", json={"personality_id": 2, "side": "sell", "shares": 1}).status_code == 400

        # sold out: shrink supply and pile in
        with SessionLocal() as db:
            p = db.get(Personality, 3)
            p.supply = 60
            db.commit()
        p1.post("/api/orders", json={"personality_id": 3, "side": "buy", "shares": 50})
        p2.post("/api/orders", json={"personality_id": 3, "side": "buy", "shares": 50})
        with SessionLocal() as db:
            s = clear(db)
            p = db.get(Personality, 3)
            assert p.sold == 60 and s[p.name]["sold_out"]
            assert abs(money_in_system(db) - start_money) <= 50
        assert c.get("/api/market").json()["personalities"][2]["sold_out"]

        # petitions -> scheduled IPO -> window -> listing
        r = p1.post("/api/petitions", json={"name": "Jack Harlow", "category": "Music", "pitch": "Lovely"})
        ptid = r.json()["open"][0]["id"]
        p2.post(f"/api/petitions/{ptid}/vote")
        assert p2.get("/api/petitions").json()["open"][0]["votes"] == 2
        r = admin.post(f"/api/admin/petitions/{ptid}/schedule", json={})
        assert r.status_code == 200, r.text
        ipo = r.json()["ipos"][0]
        with SessionLocal() as db:
            p = db.get(Personality, ipo["id"])
            p.ipo_opens_at = utcnow() - timedelta(minutes=1)
            market.advance_ipos(db)
            db.commit()
        r = p1.post("/api/ipo/commit", json={"personality_id": ipo["id"], "dollars": 600})
        assert r.status_code == 200, r.text
        assert p1.post("/api/ipo/commit", json={"personality_id": ipo["id"], "dollars": 500}).status_code == 400  # cap
        assert p2.post("/api/ipo/commit", json={"personality_id": ipo["id"], "dollars": 400}).status_code == 200
        info = c.get("/api/market").json()["personalities"]
        live_ipo = next(x for x in info if x["id"] == ipo["id"])["ipo"]
        assert live_ipo["committed"] == 1000 and live_ipo["est_open"] > live_ipo["est_price"] > 10
        with SessionLocal() as db:
            p = db.get(Personality, ipo["id"])
            p.ipo_closes_at = utcnow() - timedelta(minutes=1)
            market.advance_ipos(db)
            db.commit()
            assert p.status == "live" and p.sold > 50
            assert abs(money_in_system(db) - start_money) <= 50

        # bots trade through the same path
        random.seed(4)
        orig = bots.ACT_PROBABILITY
        bots.ACT_PROBABILITY = 1.0
        bots._awake = lambda meta, now: True
        with SessionLocal() as db:
            for _ in range(30):
                bots.run_bots(db, utcnow())
                db.commit()
                clear(db)
                bp = db.scalars(select(Personality).where(Personality.status == "ipo")).all()
            # the IPO flipper commits to open IPOs
            r = admin.post("/api/admin/ipos", json={"name": "Jon Hamm", "category": "Film & TV"})
            assert r.status_code == 200, r.text
            jh = db.scalar(select(Personality).where(Personality.name == "Jon Hamm"))
            jh.ipo_opens_at = utcnow() - timedelta(minutes=1)
            market.advance_ipos(db)
            db.commit()
            for _ in range(5):
                bots.run_bots(db, utcnow())
                db.commit()
            assert market.ipo_committed_cents(db, jh.id) > 0
            jh.ipo_closes_at = utcnow() - timedelta(minutes=1)
            market.advance_ipos(db)
            db.commit()
            assert abs(money_in_system(db) - start_money) <= 200
            traded = db.scalars(select(Holding).join(User, User.id == Holding.user_id)
                                .where(User.is_bot.is_(True), Holding.shares > 0)).all()
            assert len(traded) > 5
        bots.ACT_PROBABILITY = orig

        assert len(c.get("/api/feed").json()["items"]) > 0
        assert c.get(f"/api/players/amy").status_code == 200
        assert c.get(f"/api/personalities/{swift['id']}").json()["history"]

        # season reset
        assert admin.post("/api/admin/season/end", json={"expected_traders": 30, "confirm": "end season"}).status_code == 200
        hof = c.get("/api/hall-of-fame").json()["seasons"]
        assert hof and hof[0]["season"] == 1
        with SessionLocal() as db:
            assert money_in_system(db) == 8 * 1_000_000
        assert c.get("/api/state").json()["season"]["number"] == 2
