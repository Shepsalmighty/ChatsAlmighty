import twitchio
from twitchio.ext import commands
from twitchio.ext.commands import is_owner


class ModCmds(commands.Component):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.is_owner()
    async def clear(self, ctx: commands.Context):
        """clear all song requests from queue"""
        await self.bot.db.clear_songs()

    @commands.is_owner()
    @commands.command()
    async def brb(self, ctx: commands.Context):
        await ctx.send("Sheps will be right back, he's probably poopin")

    @commands.is_elevated()
    @commands.command(aliases=["allow"])
    async def permit(self, ctx:commands.Context, *users: twitchio.User) -> None:
        query = """INSERT INTO user_perms(user_id, user_name, has_perms)
                VALUES(?,?,?)
                ON CONFLICT(user_id) DO UPDATE
                SET has_perms = 1;"""

        user_names = ", ".join(u.name for u in users)
        await ctx.send(f"permissions granted to: {user_names}")

        async with self.bot.pool.acquire() as con:
            values = [(u.id, u.name, 1) for u in users] #1 used for True in our sqlite table
            await con.executemany(query, values)


    @commands.is_elevated()
    @commands.command()
    async def deny(self, ctx: commands.Context, *users: twitchio.User) -> None:
        sql_upsert = """
        INSERT INTO user_perms (user_id, user_name, has_perms)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE
        SET has_perms = 0;
        """

        user_names = ", ".join(u.name for u in users)
        await ctx.send(f"{user_names} got rekt")

        params = [(u.id, u.name, 0) for u in users]

        async with self.bot.pool.acquire() as con:
            await con.executemany(sql_upsert, params)

    @commands.is_owner()
    @commands.command(aliases=["r"])
    async def reload(self, ctx: commands.Context, *, module: str) -> None:
        try:
            await self.bot.reload_module(module)
        except Exception as e:
            await ctx.reply(f"Error reloading module: {e}")
        else:
            await ctx.reply(f"Successfully reloaded module: {module}")

    async def component_command_error(self, payload: commands.CommandErrorPayload) -> bool | None:
        ctx = payload.context
        error = payload.exception

        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.reply(f"Missing required argument: {error.param.name}")
            return False

        elif isinstance(error, commands.GuardFailure):
            return False


async def setup(bot: commands.Bot) -> None:
    await bot.add_component(ModCmds(bot))