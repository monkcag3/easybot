
import asyncio
from socket import MsgFlag
import zmq
import zmq.asyncio

from easybot.utils.logger import logger
from easybot.providers import LLMProvider
from easybot.core.event_loop import ZMQ_CTX, EV_AGENT_REG, EV_AGENT_UNREG


class AgentLoop:
    def __init__(
        self,
        provider: LLMProvider,
    ):
        self._provider = provider
        self._provider_name = "test"

    async def register(self):
        push = ZMQ_CTX.socket(zmq.PUSH)
        push.connect("inproc://easybot.ai/loop")

        await push.send_multipart([EV_AGENT_REG, self._provider_name.encode('utf-8')])

    async def unregister(self):
        push = ZMQ_CTX.socket(zmq.PUSH)
        push.connect("inproc://easybot.ai/loop")

        await push.send_multipart([EV_AGENT_UNREG, self._provider_name.encode('utf-8')])

    async def run(self):
        pull = ZMQ_CTX.socket(zmq.PULL)
        pull.bind(f"inproc://easybot.ai/agent.{self._provider_name}.rx")

        pub = ZMQ_CTX.socket(zmq.PUB)
        pub.bind(f"inproc://easybot.ai/agent.{self._provider_name}.tx")
        
        poller = zmq.asyncio.Poller()
        poller.register(pull, zmq.POLLIN)
        while True:
            try:
                events = await poller.poll(100)
                if pull in dict(events):
                    (ev, msg) = await pull.recv_multipart()
                    print(ev, msg)

                    messages = [
                        {"role": "system", "content": ""},
                        {"role": "user", "content": f"{msg.decode('utf-8')}"},
                    ]
                    resp = await self._provider.chat(messages)
                    print(resp)

                    topic = f'agent:{self._provider_name}:ws'
                    pub.send_multipart([
                        topic.encode('utf-8'),
                        # msg
                        resp.content.encode('utf-8')
                    ])
                else:
                    await asyncio.sleep(0.01)
            except Exception as e:
                logger.warning("Error consuming inbound message: {}, continuing...", e)
                continue