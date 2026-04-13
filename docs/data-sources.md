# Data Sources

UmaCore uses **ChronoGenesis.net** as its primary and exclusive data source.

---

## ChronoGenesis Scraper (Default)

The bot uses browser automation (via `zendriver`) to simulate a real user navigating to ChronoGenesis.net, searching for a club, and capturing the detailed member history and monthly fan data.

**Requires:**
- `circle_id` set on the club.
- Chrome/Chromium installed in the environment (bundled in our Docker image).

**What it provides:**
- Full month history per member.
- Daily cumulative fan counts.
- Real-time capturing of the underlying JSON data.

### Finding your Circle ID:
1. Go to [ChronoGenesis](https://chronogenesis.net/)
2. Search for your club by name.
3. Once on the club profile page, copy the numeric ID from the URL (`circle_id=...`).
   - Example: `https://chronogenesis.net/club_profile?circle_id=237354394` → use `237354394`.
4. Set it with `/add_club circle_id:237354394` or `/edit_club circle_id:237354394`.

---

## Technical Flow
The bot follows these steps to fetch data:
1. Initialize a headless browser instance.
2. Navigate to ChronoGenesis search.
3. Input the `circle_id` into the search box.
4. Intercept the JSON response from `api.chronogenesis.net/club_profile`.
5. Parse member growth and history to update the bot's database.

---

## Previous API notice
Direct API integrations (like Uma.moe) have been removed to ensure the project relies entirely on browser-simulated UI interaction, which provides better resilience against bot detection on datacenter IP addresses.
