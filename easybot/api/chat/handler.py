
import zmq
import json
import asyncio
from sanic import Request, Websocket, Blueprint
import aiosqlite


from easybot.core.event_loop import ZMQ_CTX


bp = Blueprint(name="chat", url_prefix="/api/ws")

class WSChannelBus:
    def __init__(self):
        self._push = ZMQ_CTX.socket(zmq.PUSH)
        self._push.connect(f"inproc://easybot.ai/agent.test.rx")

        self._sub = ZMQ_CTX.socket(zmq.SUB)
        self._sub.connect(f"inproc://easybot.ai/agent.test.tx")
        self._sub.setsockopt(zmq.SUBSCRIBE, b"")

    async def send_to_agent(self, data: dict):
        await self._push.send_multipart([
            b"chat:ws",
            # msgpack.dumps(data),
            # b'how are you?'
            data['content'].encode()
        ])

    async def recv_from_agent(self):
        (_, msg) = await self._sub.recv_multipart()
        # return msgpack.loads(msg)
        return msg.decode('utf-8')

bus = WSChannelBus()
USER_SESSIONS: dict[str, object] = {}

@bp.websocket("/chat")
async def chat(
    req: Request,
    ws: Websocket,
):
    session_hash = req.args.get("session_hash")
    user_hash = req.args.get("user_hash")
    print(session_hash, user_hash)
    if not session_hash or not user_hash:
        await ws.close()
        return

    db = req.app.ctx.db
    peer_hash = await __get_agent_hash__(db, session_hash, user_hash)
    if peer_hash is None:
        await ws.close()
        return

    try:
        async def reply_forwarder():
            while True:
                try:
                    reply = await bus.recv_from_agent()
                    
                    await __record_agent_msg__(db, session_hash, peer_hash, reply)

                    dump = {
                        "id": 1,
                        "sender": "AI",
                        "content": reply,
                        "timestamp": "00:00:00",
                    }
                    print('----return:', reply)
                    await ws.send(json.dumps(dump))
                except Exception:
                    await asyncio.sleep(0.01)
        asyncio.create_task(reply_forwarder())

        async for msg in ws:
            print('---msg', msg)
            await __record_msg__(req.app.ctx.db, msg)
 
            dump = {
                "id": 1,
                "sender": "AI",
                "content": msg,
                "timestamp": "00:00:00",
            }
            await bus.send_to_agent(dump)
    except Exception as e:
        print(f"Chat error: {e}")
    finally:
        print(f"Chat disconnected.")


async def __record_msg__(
    db: aiosqlite.Connection,
    msg: str,
):
    record = json.loads(msg)
    print(record)
    async with db.execute(f"INSERT INTO messages(session_hash, sender_hash, content) VALUES(?,?,?)",
                (record['session_hash'], record['send_hash'], record['content'])) as cursor:
        await db.commit()

async def __record_agent_msg__(
    db: aiosqlite.Connection,
    session_hash: str,
    send_hash: str,
    content: str,
):
    await db.execute("""
        INSERT INTO messages(
            session_hash, sender_hash, content
        )
        VALUES(?,?,?)
    """, (session_hash, send_hash, content))
    await db.commit()

async def __get_agent_hash__(
    db: aiosqlite.Connection,
    session_hash: str,
    user_hash: str,
) -> str|None:
    cursor = await db.execute("""
        SELECT peer_a, peer_b FROM sessions WHERE hash = ?
    """, (session_hash,))
    item = await cursor.fetchone()
    if not item:
        return None

    peer_a, peer_b = item
    if peer_a == user_hash:
        return peer_b
    else:
        return peer_a