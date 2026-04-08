
from sanic import Sanic
# from peewee import *
import aiosqlite
# from playhouse.pwasyncio import AsyncSqliteDatabase



async def start_mayim(
    app: Sanic
):
    # db = AsyncSqliteDatabase(".easybot.db")
    # app.ctx.db = db    
    db = await aiosqlite.connect(".easybot.db")
    app.ctx.db = db