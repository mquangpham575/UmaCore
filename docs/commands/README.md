# Commands

All commands are Discord slash commands (`/`).

## Categories

- [Club Management](club-management.md) — Add, edit, remove, and list clubs
- [Quota Management](quota-management.md) — Set quotas, view history, force checks
- [Channel Settings](channel-settings.md) — Configure report and alert channels
- [Member Management](member-management.md) — Add, activate, deactivate members
- [User Commands](user-commands.md) — Self-service commands for members
- [Charts & Stats](charts.md) — Progress charts and bot statistics

---

## Quick Reference

| Command | Who | Description |
|---|---|---|
| `/add_club` | Admin | Register a new club |
| `/remove_club` | Admin | Delete a club |
| `/edit_club` | Admin | Modify club settings |
| `/list_clubs` | Admin | View all clubs in server |
| `/activate_club` | Admin | Reactivate a deactivated club |
| `/quota` | Admin | Set daily quota for a club |
| `/quota_history` | Admin | View quota changes this month |
| `/delete_quota` | Admin | Remove a specific quota entry |
| `/force_check` | Admin | Manually trigger daily check |
| `/recalculate` | Admin | Recalculate bombs without clearing data |
| `/reset_month` | Admin | Manually trigger monthly reset |
| `/set_report_channel` | Admin | Set daily report channel |
| `/set_alert_channel` | Admin | Set alert channel |
| `/channel_settings` | Admin | View channel config |
| `/post_monthly_info` | Admin | Post monthly info board |
| `/update_monthly_info` | Admin | Refresh monthly info board |
| `/add_member` | Admin | Manually add a member |
| `/deactivate_member` | Admin | Deactivate a member |
| `/activate_member` | Admin | Reactivate a member |
| `/bomb_status` | Admin | View active bombs |
| `/link_trainer` | Member | Link Discord to trainer name |
| `/unlink` | Member | Remove trainer link |
| `/my_status` | Member | View your own quota status |
| `/member_status` | Member | View any member's status |
| `/notification_settings` | Member | Manage DM preferences |
| `/progress_chart` | Anyone | Fan progression chart this month |
| `/leaderboard` | Anyone | Leaderboard of synced trainers |
| `/verify` | Anyone | Verify a trainer's stats and current club from uma.moe |
| `/database_report` | Anyone | Status report from database data only (no scraping) |
| `/clear_locks` | Admin | Force release all scraping locks |
| `/set_report_channel_id` | Admin | Set report channel by raw ID (useful for threads) |
| `/set_alert_channel_id` | Admin | Set alert channel by raw ID (useful for threads) |
| `/stats` | Author | Bot-wide statistics |
