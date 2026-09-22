# Charts & Stats

---

## /progress_chart

Generate a cumulative fan progression chart for all members in a club this month.

| Parameter | Required | Description |
|---|---|---|
| `club` | Yes | Target club |

The chart shows one line per active member with dates on the X-axis and cumulative fans on the Y-axis. Members who joined mid-month will only have data from their join date onward.

**Data sources (in priority order):**
1. Live club data (ChronoGenesis API, or Uma.moe as fallback) - full month history, requires `circle_id`
2. Database history if the live fetch fails

> On day 1 of the month, the chart falls back to previous month data since the current month hasn't populated yet.

---

## /stats

View bot-wide statistics including total clubs, members, active bombs, and uptime.

**Restricted to the bot author only.**

No parameters.
