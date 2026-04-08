
from sanic import Sanic, Blueprint
from sanic_ext import Extend
# from mayim.extension import SanicMayimExtension


from easybot.core.event_loop import ZMQ_CTX
from .agent import agent_bp
from .chat import chat_bp
from .session import session_bp
from .user import user_bp




def create_app():
    app = Sanic("easybot-ai")

    # app.config.CORS_ORIGINS = "*"
    # app.config.CORS_METHODS = "GET,POST,PUT,DELETE,OPTIONS"
    # app.config.CORS_ALLOW_HEADERS = "Content-Type,Authorization"
    Extend(app)
    # Extend.register(
    #     SanicMayimExtension(
    #         executors=[
    #             AgentTemplateExecutor,
    #         ],
    #         dsn="sqlite:///.easybot.db"
    #     )
    # )

    api_v1 = Blueprint.group(
        agent_bp,
        session_bp,
        user_bp,
        url_prefix="/api/v1",
    )
    # app.blueprint(agent_bp)
    # app.blueprint(chat_bp)
    # app.blueprint(session_bp)
    app.blueprint(api_v1)
    app.blueprint(chat_bp)
    return app


# class WSChannelBus:
#     def __init__(self):
#         self._push = ZMQ_CTX.socket(zmq.PUSH)
#         self._push.connect(f"inproc://easybot.ai/agent.test.rx")

#         self._sub = ZMQ_CTX.socket(zmq.SUB)
#         self._sub.connect(f"inproc://easybot.ai/agent.test.tx")
#         self._sub.setsockopt(zmq.SUBSCRIBE, b"")

#     async def send_to_agent(self, data: dict):
#         await self._push.send_multipart([
#             b"chat:ws",
#             # msgpack.dumps(data),
#             b'how are you?'
#         ])

#     async def recv_from_agent(self):
#         (_, msg) = await self._sub.recv_multipart()
#         # return msgpack.loads(msg)
#         return msg.decode('utf-8')

# bus = WSChannelBus()
# USER_SESSIONS: dict[str, object] = {}

# @app.websocket("/chat")
# async def chat(
#     request: Request,
#     ws: Websocket,
# ):
#     try:
#         async def reply_forwarder():
#             while True:
#                 try:
#                     reply = await bus.recv_from_agent()
#                     # await ws.send(json.dumps(reply))
#                     dump = {
#                         "id": 1,
#                         "sender": "AI",
#                         "content": "each:"+reply,
#                         "timestamp": "00:00:00",
#                     }
#                     await ws.send(json.dumps(dump))
#                 except Exception:
#                     await asyncio.sleep(0.01)
#         asyncio.create_task(reply_forwarder())

#         async for msg in ws:
#             print(msg)
#             dump = {
#                 "id": 1,
#                 "sender": "AI",
#                 "content": "each:"+msg,
#                 "timestamp": "00:00:00",
#             }
#             await bus.send_to_agent(dump)
#     except Exception as e:
#         print(f"Chat error: {e}")
#     finally:
#         print(f"Chat disconnected.")