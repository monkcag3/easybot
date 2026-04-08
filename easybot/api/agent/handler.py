
import json
from sanic import Request
from sanic import response
from sanic.blueprints import Blueprint
import aiosqlite



bp = Blueprint(name='agent', url_prefix="/templates/agents")
cnt = 1

@bp.get("/")
async def get_agents(
    req: Request,
):
    agents = list()
    db: aiosqlite.Connection = req.app.ctx.db
    async with db.execute("SELECT * FROM agent_templates") as cursor:
        async for row in cursor:
            agent = dict()
            agent['hash'] = row[1]
            agent['name'] = row[2]
            agent['desc'] = row[4]
            agent['tags'] = json.loads(row[3])
            agents.append(agent)
    return response.json(agents)


@bp.get("/<agent_id>")
async def get_agent_info(
    req: Request,
    agent_id: str,
):
    return json({"name": "test"})


@bp.post("/")
async def create_agent(
    req: Request,
):
    return json({"name": "test"})