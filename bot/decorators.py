import discord
from discord import app_commands
import typing

def is_admin_or_authorized():
    """Allows Administrators or specific UMA roles (Leader, Officer, Manager)"""
    async def predicate(interaction: discord.Interaction) -> bool:
        # Admins are always allowed
        if interaction.user.guild_permissions.administrator:
            return True

        # Check for specific role names
        allowed_roles = {"UMA LEADER", "UMA OFFICER", "UMA MANAGER"}
        # Ensure we have roles (Member object)
        if hasattr(interaction.user, 'roles'):
            user_roles = {role.name.upper() for role in interaction.user.roles}
            return any(role in allowed_roles for role in user_roles)

        return False
    return app_commands.check(predicate)
