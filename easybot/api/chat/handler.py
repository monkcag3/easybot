
from dataclasses import asdict
from asyncio.log import logger
import re
import zmq
import time
import asyncio
import msgpack
from sanic import Request, Websocket, Blueprint
import aiosqlite


from easybot.agent.message import InboundMessage
from easybot.core.event_loop import ZMQ_CTX


bp = Blueprint(name="chat", url_prefix="/api/ws")

class WSChannelBus:
    def __init__(self):
        self._push = ZMQ_CTX.socket(zmq.PUSH)
        self._push.connect(f"inproc://easybot.ai/agent.test.rx")

        self._sub = ZMQ_CTX.socket(zmq.SUB)
        self._sub.connect(f"inproc://easybot.ai/agent.test.tx")
        self._sub.setsockopt(zmq.SUBSCRIBE, b"")

    async def send_to_agent(
        self,
        msg: InboundMessage,
    ):
        msg = asdict(msg)
        msg['timestamp'] = msg['timestamp'].isoformat()
        await self._push.send_multipart([
            b"chat:ws",
            msgpack.packb(msg),
        ])

    async def recv_from_agent(
        self,
    ):
        (_, msg) = await self._sub.recv_multipart()
        return msg

bus = WSChannelBus()
USER_SESSIONS: dict[str, object] = {}

@bp.websocket("/chat")
async def chat(
    req: Request,
    ws: Websocket,
):
    """
    1. 连接时携带user_hash. todo: user_hash校验
    2. 每次发送消息携带session_hash和peer_hash. todo: session_hash和peer_hash校验
    """
    user_hash = req.args.get("user_hash")
    print(user_hash)
    if not user_hash:
        await ws.close()
        return

    user_allowed_sessions: dict[str, str] = {}

    # while True:
    #     async for msg in ws:
    #         msg = msgpack.unpackb(msg, raw=False)
    #         print('---msg', msg)
            

    #         if "type" in msg:
    #             if msg["type"] == "ping":
    #                 await ws.send(msgpack.packb({"type": "pong"}))
    #         else:
    #             await __record_msg__(req.app.ctx.db, msg)

    #             inbound_msg = InboundMessage(
    #                 session_hash=msg['session_hash'],
    #                 sender_hash=msg['send_hash'],
    #                 content=msg['content'],
    #             )

    #             # 消息确认
    #             ret = {"type": "ack"}
    #             ret.update(msg)
    #             await ws.send(msgpack.packb(ret))

    #             await bus.send_to_agent(inbound_msg)

    #             async def reply_forwarder():
    #                 while True:
    #                     try:
    #                         reply = await bus.recv_from_agent()
                            
    #                         # await __record_agent_msg__(db, session_hash, peer_hash, reply)

    #                         await ws.send(bytes(reply))
    #                     except Exception:
    #                         await asyncio.sleep(0.01)
    #             await reply_forwarder()

    close_event = asyncio.Event()
    
    async def recv_from_frontend():
        try:
            async for msg in ws:
                msg = msgpack.unpackb(msg, raw=False)
                print('---msg', msg)
                
                if "type" in msg:
                    if msg["type"] == "ping":
                        await ws.send(msgpack.packb({"type": "pong"}))
                else:
                    session_hash = msg.get('session_hash')
                    # todo: check session
                    if not session_hash:
                        continue
                    if session_hash not in user_allowed_sessions:
                        peer_hash = await __get_peer_hash__(
                            req.app.ctx.db, session_hash, user_hash,
                        )
                        if peer_hash is None:
                            logger.warning(f"非法越权访问 session: {user_hash} -> {session_hash}")
                            continue

                        user_allowed_sessions[session_hash] = peer_hash

                    await __record_msg__(req.app.ctx.db, msg)

                    inbound_msg = InboundMessage(
                        session_hash=msg['session_hash'],
                        sender_hash=msg['send_hash'],
                        content=msg['content'],
                    )

                    # 消息确认
                    ret = {
                        "type": "ack",
                        "send_time": int(time.time()),
                    }
                    ret.update(msg)
                    await ws.send(msgpack.packb(ret))

                    await bus.send_to_agent(inbound_msg)
        except Exception as e:
            logger.warning(f"recv error: {e}")
        finally:
            close_event.set()

    async def recv_from_agent():
        try:
            while not close_event.is_set():
                try:
                    reply = await asyncio.wait_for(
                        bus.recv_from_agent(),
                        timeout=2.0,
                    )
                    unpack_msg = msgpack.unpackb(reply)
                    session_hash = unpack_msg.get("session_hash")
                    if session_hash in user_allowed_sessions:
                        peer_hash = user_allowed_sessions[session_hash]

                        await __record_agent_msg__(req.app.ctx.db, session_hash, peer_hash, unpack_msg['content'])

                        await ws.send(bytes(reply))
                    else:
                        # todo: 非法session
                        pass
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.warning(f"agent exception: {e}")
        finally:
            close_event.set()

    try:
        front_recv_task = asyncio.create_task(recv_from_frontend())
        agent_recv_task = asyncio.create_task(recv_from_agent())

        await asyncio.wait(
            [front_recv_task, agent_recv_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
    finally:
        close_event.set()
        await asyncio.gather(front_recv_task, agent_recv_task, return_exceptions=True)
        logger.info("ws closed")



async def __record_msg__(
    db: aiosqlite.Connection,
    record: dict,
):
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

async def __get_peer_hash__(
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