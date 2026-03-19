
import asyncio
import zmq
import zmq.asyncio

from easybot.core.event_loop import ZMQ_CTX, EV_AGENT_REG, EV_AGENT_UNREG


class AgentLoop:
    def __init__(self):
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
            events = await poller.poll(100)
            if pull in dict(events):
                (ev, msg) = await pull.recv_multipart()
                # print(ev, msg)
                topic = f'agent:{self._provider_name}:ws'
                pub.send_multipart([
                    topic.encode('utf-8'),
                    msg
                ])
            else:
                await asyncio.sleep(0.01)