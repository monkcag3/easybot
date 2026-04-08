
import json
from sanic import Request
from sanic import response
from sanic.blueprints import Blueprint
import aiosqlite



bp = Blueprint(name='user', url_prefix="/users")
cnt = 1

@bp.get("/default")
async def get_default_user(
    req: Request,
):
    user = dict()
    db: aiosqlite.Connection = req.app.ctx.db
    async with db.execute("SELECT * FROM users where id = 1") as cursor:
        one = await cursor.fetchone()
        print(one)
        user['hash'] = one[1]
        user['name'] = one[2]
        user['avator'] = ""

    return response.json(user)