
import time
import hashlib
from sanic import Request
from sanic import response
from sanic.blueprints import Blueprint
import aiosqlite


bp = Blueprint(name='session', url_prefix="/sessions")


@bp.post("/")
async def create_session(
    req: Request,
):
    data = req.json
    if 'template_hash' in data.keys():
        # 先查询去重
        async with req.app.ctx.db.execute(f"SELECT hash FROM users WHERE name = '{data['agent_name']}'") as cursor:
            item = await cursor.fetchone()
            if item is not None:
                return response.json({"hash": item[0],"name": data["agent_name"]})

        # 创建agent
        agent_hash = await __create_agent__(
            req.app.ctx.db,
            data['agent_name'],
            data['template_hash'],
            data['desc']
        )
        # 创建user - 把agent实例当作一个用户
        await __create_agent_user__(
            req.app.ctx.db,
            data['agent_name'],
            agent_hash,
        )
        # 创建session
        sorted_user = sorted([data['user_hash'], agent_hash])
        union_user = f"{sorted_user[0]}-{sorted_user[1]}"
        session_hash = hashlib.sha256(union_user.encode()).hexdigest()[:24]
        async with req.app.ctx.db.execute(f"INSERT INTO sessions(hash, peer_a, peer_b) VALUES('{session_hash}', '{data['user_hash']}', '{agent_hash}')") as cursor:
            await req.app.ctx.db.commit()

        return response.json({
            "hash": session_hash,
            "peer_hash": agent_hash,
            "peer_name": data['agent_name'],
            "peer_avator": '',
            "peer_type": 'agent',
        })
    else:
        return response.json({"error": "not implemented"})


@bp.get("/")
async def get_sessions(
    req: Request,
):
    user_hash = req.args.get("user_hash")

    if user_hash is None:
        return response.json({"error": "need user hash"})

    # async with req.app.ctx.db.execute(f"SELECT * FROM sessions WHERE peer_a = '{user_hash}' or peer_b = '{user_hash}'") as cursor:
    #     rows = await cursor.fetchall()
    #     print(rows)
    items = await __query_sessions_peer_info__(req.app.ctx.db, user_hash)

    return response.json(items)


@bp.get("/<hash>/messages")
async def get_session_messages(
    req: Request,
    hash,
):
    limit = int(req.args.get("limit", 20))
    before = req.args.get("before")
    
    if before is None: # 首次加载
        sql = """
            SELECT *
            FROM (
                SELECT *
                FROM messages
                WHERE session_hash = :hash
                ORDER BY id DESC
                LIMIT :limit
            ) AS latest_msgs
            ORDER BY id ASC;
        """
    else: # 加载历史数据
        sql = """
            SELECT *
            FROM messages
            WHERE session_hash = :hash
            AND id < :id
            ORDER BY id DESC
            LIMIT :limit;
        """
    async with req.app.ctx.db.execute(sql, {"hash": hash, "limit": limit}) as cursor:
        items = await cursor.fetchall()
        messages = []
        for item in items:
            message = dict()
            message['id'] = item[0]
            message['content'] = item[3]
            message['send_hash'] = item[2]
            message['send_time'] = item[5]
            messages.append(message)
        return response.json(messages)



async def __create_agent__(
    db: aiosqlite.Connection,
    agent_name: str,
    template_hash: str,
    desc: str,
) -> str|None:
    tm_str = str(int(time.time()))
    origin = f"{agent_name}-{tm_str}"
    agent_hash = hashlib.sha256(origin.encode()).hexdigest()[:24]
    async with db.execute(f"SELECT * FROM agent_templates where hash = '{template_hash}'") as cursor:
        item = await cursor.fetchone()
    if item is None:
        return None
    async with db.execute(f"INSERT INTO agents(hash, template_hash) VALUES('{agent_hash}', '{template_hash}')") as cursor:
        await db.commit()
    return agent_hash

async def __create_agent_user__(
    db: aiosqlite.Connection,
    agent_name: str,
    agent_hash: str,
) -> str|None:
    async with db.execute("INSERT OR IGNORE INTO users(hash, name, type) VALUES(?,?,?)",
                (agent_hash, agent_name, "agent")) as cursor:
        await db.commit()

async def __query_sessions_peer_info__(
    db: aiosqlite.Connection,
    peer_hash: str,
):
    sql = """
        SELECT
            s.hash AS session_hash,
            s.peer_a,
            s.peer_b,
            u.hash as partner_hash,
            u.name as partner_name,
            u.avatar as partner_avatar,
            u.type as partner_type
        FROM
            sessions s
        LEFT JOIN users u
            ON (u.hash = s.peer_a AND u.hash != :peer_hash)
            OR (u.hash = s.peer_b and u.hash != :peer_hash)
        WHERE
            s.peer_a = :peer_hash
            OR s.peer_b = :peer_hash
        ORDER BY s.id DESC;
    """
    async with db.execute(sql, {"peer_hash": peer_hash}) as cursor:
        items = await cursor.fetchall()
        sessions = []
        for item in items:
            session = {}
            session['hash'] = item[0]
            session['peer_hash'] = item[3]
            session['peer_name'] = item[4]
            session['peer_avator'] = item[5]
            session['peer_type'] = item[6]
            session['online'] = True
            sessions.append(session)
        return sessions