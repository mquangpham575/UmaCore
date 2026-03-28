# FAQ

## How do I set up the bot?

Use `/add_club` to register your club, then `/set_report_channel` to set where reports go. After that either wait for the automatic daily scrape or run `/force_check` to trigger it immediately.

See the [Getting Started](getting-started.md) guide for the full walkthrough.

---

## How do I find my circle ID?

**Uma.moe:** Go to [uma.moe/circles](https://uma.moe/circles/), search for your club, and copy the number from the URL. It looks something like `860280110`.

**ChronoGenesis:** The ID is shown directly under your club name on the site. It looks something like `690001342`.

---

## When does fan data update?

This happens once a day. The timing depends on which data source you're using:

- **ChronoGenesis** — updates around 11:00 UTC
- **Uma.moe** (used by the public bot) — updates around 16:00 UTC

It's recommended to set your scrape time to **17:00 UTC** to ensure data is ready before the check runs.

---

## The bot didn't scrape at the time I set

The bot won't run at the exact time you configured — it may be anywhere from 20 to 40 minutes late depending on how the internal scheduler lines up. This is expected behavior.

---

## How do I invite the bot to my server?

You can invite the public bot using the link below, or self-host it since the project is open source.

[Invite UmaCore](https://discord.com/oauth2/authorize?client_id=1467295225184784488&permissions=83968&integration_type=0&scope=bot+applications.commands)

---

## I have a problem

Please describe your issue in detail in the **#support** channel on our Discord. Keep in mind that responses may not be instant.
