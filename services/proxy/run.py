
import zmq
from zmq.asyncio import Context, Poller
import asyncio


async def run():
    ctx = Context.instance()
    xpub = ctx.socket(zmq.PUB)
    xpub.bind("inproc://easybot.ai/tx/audio")
    xsub = ctx.socket(zmq.SUB)
    xsub.bind("inproc://easybot.ai/rx/audio")
    xsub.setsockopt(zmq.SUBSCRIBE, b"")

    poller = Poller()
    poller.register(xsub, zmq.POLLIN)
    while True:
        events = await poller.poll()
        if xsub in dict(events):
            [topic, data] = await xsub.recv_multipart()
            if topic == b'exit':
                break
            await xpub.send_multipart([topic, data])

async def shutdown():
    ctx = Context.instance()
    pub = ctx.socket(zmq.PUB)
    pub.connect("inproc://easybot.ai/rx/audio")
    await pub.send_multipart([b'exit', b''])
