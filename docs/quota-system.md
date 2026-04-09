# Quota System

## How Quotas Work

Each club has a quota — a fan-earning goal that members need to meet. The bot checks progress daily and compares each member's actual fans against the expected cumulative total.

### Deficit & Surplus

```
deficit_surplus = cumulative_fans - expected_fans
```

- **Positive** → member is ahead of quota
- **Negative** → member is behind quota
- Surplus from previous days can cover future deficits

### Quota Periods

| Period | Description |
|---|---|
| `daily` | Quota applies per day (e.g. 1M/day = 30M/month) |
| `weekly` | Quota applies per 7 days (e.g. 5M/week) |
| `biweekly` | Quota applies per 14 days (e.g. 10M/2 weeks) |

Set or change the period with `/edit_club`.

### Mid-Month Quota Changes

You can change the quota at any time with `/quota`. The new quota applies from that day forward — historical data is unaffected and expected fans are recalculated automatically. The monthly info board also updates.

---

## Bomb System

The bomb system warns members who consistently fall behind quota.

### How It Works

1. A member falls behind quota for `bomb_trigger_days` consecutive days (default: 3)
2. A bomb is activated — the member is notified via DM (if linked)
3. The member has `bomb_countdown_days` days (default: 7) to get back on track
4. If they catch up within the countdown, the bomb is defused
5. If they don't, an alert is posted in the alert channel

### Configuration

Configured per club via `/edit_club`:

| Setting | Default | Description |
|---|---|---|
| `bomb_trigger_days` | 3 | Days behind before bomb activates |
| `bomb_countdown_days` | 7 | Days to recover before alert |
| `bombs_enabled` | false | Toggle bomb system on/off |

Use `/bomb_status` to see all active bombs for a club.

---

## Monthly Reset

At the start of each month, the bot automatically detects when fan counts drop significantly (below 50% of the previous total) and triggers a reset, which:

- Clears quota history
- Clears active bombs
- Clears tracking data
- Starts fresh for the new month

You can also trigger it manually with `/reset_month` if something went wrong.
