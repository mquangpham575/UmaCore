# Data Sources

UmaCore reads club data from two sources and picks between them automatically on every scrape:

1. **ChronoGenesis API** (primary) - used whenever `CHRONO_API_KEY` is configured and the request succeeds.
2. **Uma.moe API** (fallback) - used when no Chrono key is set, or when the Chrono request fails.

Both are plain HTTP APIs (no browser is involved) and both use the same numeric `circle_id`.

---

## ChronoGenesis API (primary)

Fetches `api.chronogenesis.net/club_profile?circle_id=<id>` with the key from `CHRONO_API_KEY`.

**What it provides:**
- Full-month cumulative fan history per member.
- The exact join time of every member (so the join day and baseline are precise).
- Club-level daily and monthly history.

The Chrono API is closed source and needs an authorization key from its owner. Without a key the bot simply uses Uma.moe.

---

## Uma.moe API (fallback)

Fetches `uma.moe/api/v4/circles?circle_id=<id>&year=<y>&month=<m>` with the key from `UMAMOE_API_KEY`.

**What it provides:**
- One lifetime-fan snapshot per day per member (slot `d` is day `d` of the month; slot `0` is the month-start baseline).
- Snapshots are taken around 15:00 UTC; the newest populated slot is treated as the current data day.

**Limits compared to Chrono:**
- The API has no join time. The bot infers each member's join day from the first day that has data, so mid-month joiners can be off by about a day.
- Members flagged this way are marked as `join_day_reliable = False` internally.

---

## Choosing a source

| Situation | Source used |
|---|---|
| `CHRONO_API_KEY` set and the request succeeds | ChronoGenesis |
| `CHRONO_API_KEY` missing, or the Chrono request fails | Uma.moe |
| Neither responds | The scrape is retried with exponential backoff, then reported as failed |

---

## Finding your Circle ID

1. Go to [uma.moe/circles](https://uma.moe/circles/) and search for your club, or open your club on [ChronoGenesis](https://chronogenesis.net/).
2. Copy the numeric ID from the URL (for example `https://uma.moe/circles/860280110` -> `860280110`, or `.../club_profile?circle_id=237354394` -> `237354394`).
3. Set it with `/add_club circle_id:...` or `/edit_club circle_id:...`.
