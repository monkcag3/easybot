
import chainlit as cl
import sounddevice as sd
import numpy as np
import asyncio

from services.proxy.run import run as proxy_run
from services.proxy.run import shutdown as proxy_shutdown
from services.sherpa.run import load_env
from services.sherpa.run import run as audio_run
from services.sherpa.run import shutdown as audio_shutdown

asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def get_input_devices():
    devices = sd.query_devices()
    input_devices = []
    for idx, device in enumerate(devices):
        if device['max_input_channels'] > 0:
            input_devices.append({
                'index': idx,
                'name': device['name'],
                'channels': device['max_input_channels'],
                'default_samplerate': device['default_samplerate'],
            })
    return input_devices


async def run_audio_recv():
    import zmq
    from zmq.asyncio import Context, Poller
    ctx = Context.instance()
    sub = ctx.socket(zmq.SUB)
    sub.connect("inproc://easybot.ai/tx/audio")
    sub.subscribe(b"")

    msg = await cl.Message(content="").send()

    poller = Poller()
    poller.register(sub, zmq.POLLIN)
    while True:
        events = await poller.poll()
        if sub in dict(events):
            [topic, data] = await sub.recv_multipart()
            # await msg.stream_token(topic.decode("utf-8"))
            await msg.stream_token(data.decode("utf-8"))
            await msg.update()


@cl.on_app_startup
async def startup():
    ## 加载.env
    load_env()
    asyncio.create_task(proxy_run())

@cl.on_app_shutdown
async def shutdown():
    await proxy_shutdown()
    audio_shutdown()


@cl.on_chat_start
async def on_chat_start():
    load_env()

    devices = get_input_devices()
    if not devices:
        await cl.ErrorMessage(content="❌ 未找到任何音频输入设备，请检查麦克风连接").send()
        return

    cl.user_session.set("available_devices", devices)
    print("deivcesssssss")
    actions = []
    for dev in devices:
        actions.append(
            cl.Action(
                name = "select sound device",
                value = str(dev["index"]),
                label = f"🎤 {dev['name']} ({dev['channels']}通道)",
                payload = dev,
                description=f"采样率: {dev['default_samplerate']}Hz"
            )
        )

    await cl.Message(
        content="请选择您的麦克风设备：",
        actions=actions
    ).send()

    msg = cl.Message(content="")
    await msg.send()
    cl.user_session.set("live_msg", msg)

@cl.action_callback("select sound device")
async def on_sound_device_select(
    action: cl.Action
):
    ## 开启扬声器语音捕获
    asyncio.create_task(audio_run())
    ## 监控语音识别结果
    asyncio.create_task(run_audio_recv())

    device = action.payload
    await cl.Message(
        content=f"已选择: **{device['name']}**\n\n"
                f"该设备支持 {device['channels']} 个输入通道。\n"
    ).send()
