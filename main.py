
import asyncio
from sanic import Sanic

from easybot.core.event_loop import EventLoop, ZMQ_CTX
from easybot.agent.loop import AgentLoop
from easybot.chat import QQChat
from easybot.api import app

asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


async def broker():
    loop = EventLoop()
    await loop.run()

async def sender():
    agent = AgentLoop()
    await agent.register()
    await asyncio.sleep(2)
    await agent.unregister()
    await agent.run()

async def qq_chat():
    chat = QQChat()
    await chat.register()
    await asyncio.sleep(2)
    await chat.unregister()


# @app.main_process_start
@app.before_server_start
async def start_backend_service(
    app: Sanic
):
    app.add_task(broker())
    app.add_task(sender())


if __name__ == "__main__":
    app.run(port=8080)
