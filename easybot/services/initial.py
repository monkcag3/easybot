
import aiosqlite
from easybot.config.schema import Config


async def init_db(
    config: Config,
):
    async with aiosqlite.connect(".easybot.db") as conn:
        await __create_table__(conn)
        await __init_default_agent_templates__(conn)


async def __create_table__(
    conn: aiosqlite.Connection,
):
    # ## 创建agent_templates表
    # cursor = await conn.cursor()
    # await cursor.execute("""
    #     CREATE TABLE IF NOT EXISTS agent_templates(
    #         id INTEGER PRIMARY KEY,
    #         hash TEXT UNIQUE,
    #         name TEXT UNIQUE,
    #         tags TEXT,
    #         desc TEXT,
    #         is_local bool,
    #         is_gateway bool,
    #         type TEXT
    #     )
    # """)
    # await conn.commit()

    # ## 创建users表 -- agent看作是一个user
    # await cursor.execute("""
    #     CREATE TABLE IF NOT EXISTS users(
    #         id INTEGER PRIMARY KEY,
    #         hash TEXT UNIQUE,
    #         name TEXT UNIQUE,
    #         type TEXT     --类型: auto, agent, user
    #     )
    # """)

    # ## 创建sessions表
    # await cursor.execute("""
    #     CREATE TABLE IF NOT EXISTS sessions(
    #         id INTEGER PRIMARY KEY,
    #         hash TEXT UNIQUE,
    #         user_hash TEXT,
    #         agent_hash TEXT,
    #         type TEXT DEFAULT "human-agent"  --类型:human-agent,human-human
    #     )
    # """)
    # await conn.commit()
    pass


async def __init_default_agent_templates__(
    conn: aiosqlite.Connection,
):
    import json
    import time
    import hashlib
    from easybot.providers.registry import PROVIDERS

    ## 默认agent模板
    tm_str = str(int(time.time()))
    cursor = await conn.cursor()
    for p in PROVIDERS:
        origin = f"{p.name}-{tm_str}"
        hash = hashlib.sha256(origin.encode()).hexdigest()[:24]
        await cursor.execute("INSERT OR IGNORE INTO agent_templates(hash, name, tags, desc, is_local, is_gateway, type) VALUES(?,?,?,?,?,?,?)",
            (hash, p.display_name, json.dumps(p.keywords), p.desc, p.is_local, p.is_gateway, p.type))
    await conn.commit()

    ## 默认用户
    tm_str = str(int(time.time()))
    cursor = await conn.cursor()
    name = "默认用户"
    origin = f"{name}-{tm_str}"
    hash = hashlib.sha256(origin.encode()).hexdigest()[:24]
    await cursor.execute("INSERT OR IGNORE INTO users(hash, name, type) VALUES(?,?,?)",
        (hash, name, "user"))
    await conn.commit()