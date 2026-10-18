# FameX

A play-money stock market for famous people. Friends buy and sell shares in 100 "Personalities"; prices move only with trading.

## How the game works

- **Bankroll:** every approved player starts the season with $10,000.
- **Prices:** each Personality sits on a bonding curve, `price = $10 + k × shares held by players`. Buying pushes the price up; selling pulls it down.
- **Calibration:** `k = 0.75 × p₀² × Personalities ÷ (traders × seed)` and `supply ≈ 1.6 × traders × seed ÷ (p₀ × √Personalities)`. With 30 traders and 100 Personalities that's k = 0.025 and about 4,800 shares each. These are locked per Personality when it lists.
- **30-second clearing:** orders collect until the next :00 or :30. Then buys and sells for each Personality are netted and everyone in that batch trades at the same price, the curve's average over the net move. Every order carries a price limit (10% beyond the estimate by default); orders outside the clearing price wait for a later batch and expire after 24 hours.
- **Sold out:** when all shares are held, buys are filled pro-rata and the rest are refunded until someone sells.
- **Weekly IPO:** players petition and vote (one vote each, changeable). Admins schedule one IPO a week, by default Monday 2pm ET for 24 hours. During the window players commit up to $1,000. At the close everyone pays one price (the curve average over all IPO shares) and trading opens higher, at the curve's marginal price.
- **House players:** five bots with distinct styles (momentum, contrarian, IPO flipper, index, superfan). They use the same order path, see prices 5–20 minutes stale, sleep at night, and use round-dollar order sizes. Only admins can see who they are.
- **Joining:** admins create single-use passphrases. Players sign up with passphrase, username, password, email, short bio and an optional avatar, then wait for approval. Approvals that push the season more than 30% above its starting size ask the admin to confirm or defer the player to next season.
- **Seasons:** quarterly. Ending a season records the top 10 in the Hall of Fame, resets every bankroll, admits deferred players, and recalibrates all curves for the new player count.
- **Scoring:** net worth is cash plus each holding valued as if sold alone along the curve, so giant positions can't claim a price they couldn't actually cash out at.

## Deploy on Railway

1. Push this folder to a GitHub repo.
2. In Railway: **New Project → Deploy from GitHub repo**. It builds from the `Dockerfile`.
3. Add a database: **New → Database → PostgreSQL**. In your app service's **Variables**, add `DATABASE_URL` and reference the Postgres service's `DATABASE_URL`.
4. Add the variable `BOOTSTRAP_PASSPHRASE` with a secret phrase of your choosing.
5. Under **Settings → Networking**, generate a domain.
6. Open `https://<your-domain>/#/signup` and sign up using the bootstrap passphrase. The first person to do so becomes the admin. After that the bootstrap passphrase stops working.
7. In **Admin → Passphrases**, generate one passphrase per friend and send each the signup link with their passphrase.

Keep the service at **one replica**. The market clock and trade lock run inside the app process.

### Optional variables

| Variable | Default | What it does |
|---|---|---|
| `APP_NAME` | FameX | Name shown in the app |
| `SEED_DOLLARS` | 10000 | Starting bankroll |
| `IPO_PRICE` | 10 | Base price p₀ |
| `IPO_CAP_DOLLARS` | 1000 | Max IPO commitment per player |
| `EXPECTED_TRADERS` | 30 | Trader count used to calibrate season 1 (include the 5 bots) |
| `GAME_TZ` | America/New_York | Time zone for IPO windows and bot hours |
| `SECURE_COOKIES` | 1 | Set to 0 only for local http testing |

## Run locally

```bash
# API (http://localhost:8000)
cd backend
pip install -r requirements.txt
BOOTSTRAP_PASSPHRASE=let-me-in SECURE_COOKIES=0 uvicorn app.main:app --reload

# Frontend with hot reload (http://localhost:5173, proxies /api)
cd frontend
npm install
npm run dev
```

Without `DATABASE_URL` it uses a local SQLite file. Run the end-to-end test with `cd backend && pip install pytest httpx && python -m pytest -q tests`.

## Layout

```
backend/app/
  market.py   curve math, order holds, batch clearing, IPOs, valuation
  engine.py   startup seeding, the 30-second market clock, season rollover
  bots.py     the five house players
  seed.py     starting roster of 100 Personalities and bot profiles
  main.py     API routes and static file serving
frontend/src/
  App.jsx     shell, clearing clock, ticker, routing
  pages/      Market, Personality, Portfolio, Leaderboard, IPO, Player, Settings, Admin
```
