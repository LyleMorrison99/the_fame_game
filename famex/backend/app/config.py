import os
from zoneinfo import ZoneInfo

APP_NAME = os.environ.get("APP_NAME", "FameX")
SEED_CENTS = int(float(os.environ.get("SEED_DOLLARS", "10000")) * 100)
P0 = float(os.environ.get("IPO_PRICE", "10"))
IPO_CAP_CENTS = int(float(os.environ.get("IPO_CAP_DOLLARS", "1000")) * 100)
TICK_SECONDS = 30
ORDER_EXPIRY_HOURS = 24
GROWTH_WARNING = 0.30          # warn when mid-season joins push traders up more than 30%
SEASON_WEEKS = 13              # quarterly
DEFAULT_EXPECTED_TRADERS = int(os.environ.get("EXPECTED_TRADERS", "30"))
DEFAULT_SLIPPAGE = 0.10        # default limit sits 10% beyond the estimate
GAME_TZ = ZoneInfo(os.environ.get("GAME_TZ", "America/New_York"))
# Weekly IPO window defaults (local game time). Admins can override per IPO.
IPO_WEEKDAY = 0                # Monday
IPO_OPEN_HOUR = 14             # 2pm
IPO_WINDOW_HOURS = 24
BOOTSTRAP_PASSPHRASE = os.environ.get("BOOTSTRAP_PASSPHRASE", "")
SECURE_COOKIES = os.environ.get("SECURE_COOKIES", "1") == "1"
