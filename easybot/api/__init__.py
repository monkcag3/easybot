
import zmq
import json
import asyncio
import msgpack
from sanic import Request, Sanic, Websocket

from easybot.core.event_loop import ZMQ_CTX



app = Sanic("easybot-ai")

# config = WebSocketConfig(
#     max_message_size=100,  # 100 Bytes limit (RAM protection)
#     rate_limit=20,         # 20 msgs/sec limit (CPU protection)
#     heartbeat_interval=15, # Ping every 15s
#     timeout = 60,          # Timeout after 60s silence
# )


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
            msgpack.dumps(data),
        ])

    async def recv_from_agent(self):
        (_, msg) = await self._sub.recv_multipart()
        return msgpack.loads(msg)

bus = WSChannelBus()
USER_SESSIONS: dict[str, object] = {}

@app.websocket("/chat")
async def chat(
    request: Request,
    ws: Websocket,
):
    try:
        async def reply_forwarder():
            while True:
                try:
                    reply = await bus.recv_from_agent()
                    await ws.send(json.dumps(reply))
                except Exception:
                    await asyncio.sleep(0.01)
        asyncio.create_task(reply_forwarder())

        async for msg in ws:
            dump = {
                "id": 1,
                "sender": "AI",
                "content": "each:"+msg,
                "timestamp": "00:00:00",
            }
            await bus.send_to_agent(dump)
    except Exception as e:
        print(f"Chat error: {e}")
    finally:
        print(f"Chat disconnected.")