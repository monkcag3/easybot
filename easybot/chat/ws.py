
import asyncio
import zmq
import zmq.asyncio
from loguru import logger

from easybot.core.event_loop import ZMQ_CTX, EV_CHAT_REG, EV_CHAT_UNREG


class WSChat:
    def __init__(self):
        self._provider_name = "WS"

    async def register(self):
        print("register")
        push = ZMQ_CTX.socket(zmq.PUSH)
        push.connect("inproc://easybot.ai/loop")

        await push.send_multipart([EV_CHAT_REG, self._provider_name.encode('utf-8')])

    async def unregister(self):
        push = ZMQ_CTX.socket(zmq.PUSH)
        push.connect("inproc://easybot.ai/loop")

        await push.send_multipart([EV_CHAT_UNREG, self._provider_name.encode('utf-8')])

    async def run(self):
        questions = [
            "How are you ?",
            "What's your name ?"
        ]

        sub = ZMQ_CTX.socket(zmq.SUB)
        sub.subscribe(b'agent:test:ws')

        poller = zmq.asyncio.Poller()
        poller.register(sub, zmq.POLLIN)
        while True:
            events = await poller.poll(1)
            if sub in dict(events):
                (topic, msg) = sub.recv_multipart()
                logger.debug(f"{topic} - {msg}")

            push = ZMQ_CTX.socket(zmq.PUSH)
            push.connect("inproc://easybot.ai/agent.test.rx")
            for Q in questions:
                await asyncio.sleep(1)
                push.send_multipart([b"", Q.encode('utf-8')])