### :rocket: Getting Started

To track your individual progress and receive personal notifications, you must link your Discord account to your trainer profile.

1.  **Find your trainer profile:**
    *   Open the `/list_clubs` command to see which clubs are registered.
2.  **Link your account:**
    *   Use: `/link_trainer trainer_name:YourName club:ClubName`
    *   *Note: Your name must match exactly as it appears in the game/chronogenesis.*
3.  **Done!** You are now linked. You can use `/my_status` at any time to check your progress.

### :bar_chart: Member Commands

*   **/my_status** — View your own fan progress, surplus/deficit, and bomb status.
*   **/member_status** — View the status of any other member in the club.
*   **/check_club** — View the current full club status report without triggering a new scrape.
*   **/progress_chart** — Generate a visual chart showing everyone's progress this month.
*   **/previous_month** — See a full recap of last month's final results.
*   **/notification_settings** — Customize if you want DMs for bombs or falling behind.
*   **/list_clubs** — View all registered clubs in this server.
*   **/list_members** — List all active members currently in the database for a club.
*   **/unlink** — Remove the link between your Discord and trainer profile.
*   **/privacy** — View UmaCore's privacy policy and terms of service.

### :bomb: The "Bomb" System

UmaCore uses a **Bomb System** to help everyone stay on track with the club's daily quota requirements.

*   **Triggering:** If you fall below the required fan count for **3 consecutive days**, a "Bomb" will be placed on your profile.
*   **Countdown:** Once a bomb is active, you have **7 days** to catch up to the expected fan total.
*   **Detonation:** If the countdown reaches 0 and you are still in a deficit, an alert will be sent to the club managers.
*   **Defusal:** Simply earn enough fans to reach a "Surplus" (positive fan count) to automatically defuse the bomb!

You can enable additional alerts for when you fall into a deficit (before a bomb triggers) using `/notification_settings`.

_ _

### :tools: Staff Commands
*Staff commands are available to server Administrators and users with the **UMA LEADER**, **UMA OFFICER**, or **UMA MANAGER** roles.*

**🛠️ Setup & Configuration**
*   **/add_club** — Register a new club to track in this server.
*   **/edit_club** — Change settings like Timezone, Scrape Time, or Bomb rules.
*   **/activate_club** / **/deactivate_club** — Pause or resume tracking for a specific club.
*   **/set_report_channel** — Select where daily reports are posted.
*   **/set_alert_channel** — Select where bomb/kick alerts are posted.
*   **/post_monthly_info** — Create an auto-updating info board in a channel.
*   **/channel_settings** — View current configuration for a specific club.

**👥 Member Management**
*   **/add_member** — Manually add a new member to the database.
*   **/activate_member** / **/deactivate_member** — Manually override a member's status.

**📊 Monitoring & Quota**
*   **/force_check** — Trigger an immediate scrape and post a fresh report.
*   **/quota** — Set the fan requirement for the club (Daily, Weekly, etc.).
*   **/quota_history** — View a log of quota changes for the current month.
*   **/bomb_status** — List all members who currently have an active bomb.
*   **/recalculate** — Bug fix: Force-recalculate all days-behind counts from history.

**🔄 System & Maintenance**
*   **/transfer_club** — Pull a club from another server (or legacy data) to this server.
*   **/reset_month** — Manually clear all history (only use if auto-reset fails).
*   **/sync_guild** — Force Discord to refresh the command list in this server.
*   **/check_channel** — Diagnose bot permissions to see why reports aren't sending.

If the bot isn't finding your name, you can't run commands, or you have other issues, please contact **@duck0908**.
