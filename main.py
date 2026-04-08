
import zmq
import asyncio
from sanic import Sanic

from easybot.core.event_loop import EventLoop, ZMQ_CTX
from easybot.agent.loop import AgentLoop
from easybot.chat import QQChat, WSChat
from easybot.api import create_app
from easybot.utils.logger import logger
from easybot.services.initial import init_db
from easybot.services.mayim import start_mayim

asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


app = create_app()

async def broker():
    loop = EventLoop()
    await loop.run()

async def sender():
    # agent = AgentLoop()
    # await agent.register()
    # await asyncio.sleep(2)
    # await agent.unregister()
    # await agent.run()
    pass

async def qq_chat():
    chat = QQChat()
    await chat.register()
    await asyncio.sleep(2)
    await chat.unregister()

async def ws_chat():
    chat = WSChat()
    await chat.register()
    await asyncio.sleep(2)
    await chat.unregister()
    await chat.run()


# @app.main_process_start
@app.before_server_start
async def start_backend_service(
    app: Sanic,
):
    from easybot.config.loader import load_config
    from pathlib import Path
    config_path = Path("./config.json").expanduser().resolve()
    print(config_path)
    config = load_config(config_path)

    from easybot.services.agent import start_agent

    app.add_task(start_agent(config))
    app.add_task(sender())
    app.add_task(init_db(config))
    app.add_task(start_mayim(app))

@app.after_server_stop
async def clean_backend_service(
    app: Sanic,
):
    logger.info("after server stop")



async def start_agent():
    from easybot.config.loader import load_config
    from pathlib import Path
    config_path = Path("./config.json").expanduser().resolve()
    print(config_path)
    config = load_config(config_path)
    model = config.agents.defaults.model
    provider_name = config.get_provider_name(model)
    p = config.get_provider(model)
    print(model, provider_name, p)

    from easybot.providers.base import GenerationSettings
    from easybot.providers import LlamaCppProvider
    provider = LlamaCppProvider(
        api_key=p.api_key if p else "no-key",
        api_base=config.get_api_base(model) or "http://localhost:8000",
        default_model=model,
        extra_headers=p.extra_headers if p else None,
    )
    print("load llama-cpp")

    defaults = config.agents.defaults
    provider.generation = GenerationSettings(
        temperature=defaults.temperature,
        max_tokens=defaults.max_tokens,
        reasoning_effort=defaults.reasoning_effort,
    )
  
    agent = AgentLoop(
        provider=provider
    )
    await agent.run()

async def chat():
    pull = ZMQ_CTX.socket(zmq.PUSH)
    pull.connect(f"inproc://easybot.ai/agent.test.rx")

    await pull.send_multipart([b'test', b'How are you ?'])

    sub = ZMQ_CTX.socket(zmq.SUB)
    sub.connect(f"inproc://easybot.ai/agent.test.tx")
    sub.setsockopt(zmq.SUBSCRIBE, b"")
    while True:
        [topic, msg] = await sub.recv_multipart()
        print(topic, msg)

async def __main__():
    task = asyncio.create_task(start_agent())
    task1 = asyncio.create_task(chat())

    await asyncio.gather(*[task, task1])

def main():
    asyncio.run(__main__())


if __name__ == "__main__":
    app.run(port=8080, debug=True)
    # main()    