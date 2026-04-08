
import asyncio


SHUTDOWN = asyncio.Event()

async def stop_all():
    SHUTDOWN.set()