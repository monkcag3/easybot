
import zmq
import zmq.asyncio

from easybot.core.event_loop import ZMQ_CTX, EV_CHAT_REG, EV_CHAT_UNREG


class QQChat:
    def __init__(self):
        self._provider_name = "QQ"

    async def register(self):
        push = ZMQ_CTX.socket(zmq.PUSH)
        push.connect("inproc://easybot.ai/loop")

        await push.send_multipart([EV_CHAT_REG, self._provider_name.encode('utf-8')])

    async def unregister(self):
        push = ZMQ_CTX.socket(zmq.PUSH)
        push.connect("inproc://easybot.ai/loop")

        await push.send_multipart([EV_CHAT_UNREG, self._provider_name.encode('utf-8')])

    async def run(self):
        pass