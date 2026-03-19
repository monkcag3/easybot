
import asyncio
import zmq
import zmq.asyncio

from easybot.utils.logger import logger

EV_AGENT_REG = b'agent:reg'
EV_AGENT_UNREG = b'agent:unreg'
EV_CHAT_REG = b'chat:reg'
EV_CHAT_UNREG = b'chat:unreg'


class ZMQContext:
    _instance: zmq.asyncio.Context = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = zmq.asyncio.Context()
        return cls._instance

ZMQ_CTX: zmq.asyncio.Context = ZMQContext()


class EventLoop:
    def __init__(self):
        self._ctx = ZMQ_CTX
        self._inbound = self._ctx.socket(zmq.PULL)
        self._inbound.bind("inproc://easybot.ai/loop")
        # self._outound = self._ctx.socket(zmq.PUSH)

    async def run(self):
        poller = zmq.asyncio.Poller()
        poller.register(self._inbound, zmq.POLLIN)
        while True:
            events = await poller.poll(100)
            if self._inbound in dict(events):
                (ev, msg) = await self._inbound.recv_multipart()
                # print(ev, msg)
                if ev == EV_AGENT_REG:
                    logger.info(f"Agent[{msg.decode('utf-8')}] register!")
                elif ev == EV_AGENT_UNREG:
                    logger.info(f"Agent[{msg.decode('utf-8')}] unregister!")
                elif ev == EV_CHAT_REG:
                    logger.info(f"Chat[{msg.decode('utf-8')}] register!")
                elif ev == EV_CHAT_UNREG:
                    logger.info(f"Chat[{msg.decode('utf-8')}] unregister!")
            else:
                await asyncio.sleep(0.01)
                