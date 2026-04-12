
from email import message
import time
import asyncio
from dataclasses import asdict
from typing import Callable
import msgpack
import json
from datetime import datetime
from contextlib import nullcontext
from pathlib import Path
import zmq
import zmq.asyncio
from typing import Callable, Awaitable, Any

from easybot.agent.message import InboundMessage, OutboundMessage
from easybot.agent.hook import AgentHook, AgentHookContext, CompositeHook
from easybot.agent.runner import AgentRunner, AgentRunSpec
from easybot.agent.tools.registry import ToolRegistry
from easybot.session import SessionManager
from easybot.utils.logger import logger
from easybot.providers import LLMProvider
from easybot.core.event_loop import ZMQ_CTX, EV_AGENT_REG, EV_AGENT_UNREG


EMPTY_FINAL_RESPONSE_MESSAGE = (
    "I completed the tool steps but couldn't produce a final answer. "
    "Please try again or narrow the task."
)


class _LoopHook(AgentHook):
    """Core hook for the main loop."""

    def __init__(
        self,
        agent_loop: "AgentLoop",
        on_progress: Callable[..., Awaitable[None]] | None = None,
        on_stream: Callable[[str], Awaitable[None]] | None = None,
        on_stream_end: Callable[..., Awaitable[None]] | None = None,
        *,
        channel: str = "cli",
        chat_id: str = "direct",
        message_id: str | None = None,
    ) -> None:
        super().__init__(reraise=True)
        self._loop = agent_loop
        self._on_progress = on_progress
        self._on_stream = on_stream
        self._on_stream_end = on_stream_end
        self._channel = channel
        self._chat_id = chat_id
        self._message_id = message_id
        self._stream_buf = ""

    def wants_streaming(self) -> bool:
        return self._on_stream is not None

    async def on_stream(
        self,
        ctx: AgentHookContext,
        delta: str,
    ) -> None:
        from easybot.utils.helpers import strip_think

        prev_clean = strip_think(self._stream_buf)
        self._stream_buf += delta
        new_clean = strip_think(self._stream_buf)
        incremental = new_clean[len(prev_clean):]
        if incremental and self._on_stream:
            await self._on_stream(incremental)

    async def on_stream_end(
        self,
        ctx: AgentHookContext,
        *,
        resuming: bool,
    ) -> None:
        if self._on_stream_end:
            await self._on_stream_end(resuming=resuming)
        self._stream_buf = ""

    async def before_execute_tools(
        self,
        ctx: AgentHookContext,
    ) -> None:
        if self._on_progress:
            if not self._on_stream:
                thought = self._loop._strip_think(
                    ctx.response.content if ctx.response else None
                )
                if thought:
                    await self._on_progress(thought)
            tool_hint = self._loop._strip_think(self._loop._tool_hint(ctx.tool_calls))
            await self._on_progress(tool_hint, tool_hint=True)
        for tc in ctx.tool_calls:
            args_str = json.dumps(tc.arguments, ensure_ascii=False)
            logger.info("Tool call: {}({})", tc.name, args_str[:200])
        self._loop._set_tool_context(self._channel, self._chat_id, self._message_id)

    async def after_iteration(
        self,
        ctx: AgentHookContext,
    ) -> None:
        u = ctx.usage or {}
        # logger.debug(
        #     "LLM usage: prompt={} completion={} cached={}",
        #     u.get("prompt_tokens", 0),
        #     u.get("completion_tokens", 0),
        #     u.get("cached_tokens", 0),
        # )

    def finalize_content(
        self,
        ctx: AgentHookContext,
        content: str | None,
    ) -> str | None:
        return self._loop._strip_think(content)



class AgentLoop:
    """
    The agent loop is the core processing engine.
    1. Receives messages from the bus
    2. Builds context with history, memory, skills
    3. Calls the LLM
    4. Executes tool calls
    5. Sends responses back
    """
    def __init__(
        self,
        provider: LLMProvider,
    ):
        self._provider = provider
        self._provider_name = "test"

        self.model = provider.get_default_model()
        self.max_iterations = 200
        self.max_tool_result_chars = 16_000
        self._extra_hooks: list[AgentHook] = []
        self.sessions = SessionManager(workspace=Path(""))
        self.tools = ToolRegistry()
        self.runner = AgentRunner(provider)

        self._active_tasks: dict[str, list[asyncio.Task]] = {}
        self._background_tasks: list[asyncio.Task] = []
        self._session_locks: dict[str, asyncio.Lock] = {}
        _max = 3
        self._concurrency_gate: asyncio.Semaphore | None = (
            asyncio.Semaphore(_max) if _max > 0 else None
        )

        self.pub = ZMQ_CTX.socket(zmq.PUB)
        self.pub.bind(f"inproc://easybot.ai/agent.{self._provider_name}.tx")

    async def register(self):
        push = ZMQ_CTX.socket(zmq.PUSH)
        push.connect("inproc://easybot.ai/loop")

        await push.send_multipart([EV_AGENT_REG, self._provider_name.encode('utf-8')])

    async def unregister(self):
        push = ZMQ_CTX.socket(zmq.PUSH)
        push.connect("inproc://easybot.ai/loop")

        await push.send_multipart([EV_AGENT_UNREG, self._provider_name.encode('utf-8')])

    async def run(self):
        """Run the agent loop, dispatching messages as tasks to stay responsive to /stop."""
        pull = ZMQ_CTX.socket(zmq.PULL)
        pull.bind(f"inproc://easybot.ai/agent.{self._provider_name}.rx")

        # pub = ZMQ_CTX.socket(zmq.PUB)
        # pub.bind(f"inproc://easybot.ai/agent.{self._provider_name}.tx")
        
        poller = zmq.asyncio.Poller()
        poller.register(pull, zmq.POLLIN)
        while True:
            try:
                events = await poller.poll(100)
                if pull in dict(events):
                    (ev, msg) = await pull.recv_multipart()
                    print(ev, msg)

                    # todo:
                    msg_dict = msgpack.unpackb(msg)
                    msg_dict['timestamp'] = datetime.fromisoformat(msg_dict['timestamp'])
                    inbound_message = InboundMessage(**msg_dict)
                else:
                    await asyncio.sleep(0.01)
                    continue
            except Exception as e:
                logger.warning("Error consuming inbound message: {}, continuing...", e)
                continue

            # todo: commands check
            
            effective_key = inbound_message.session_hash
            task = asyncio.create_task(self.__dispatch__(inbound_message))
            self._active_tasks.setdefault(effective_key, []).append(task)
            task.add_done_callback(
                lambda t, 
                k=effective_key: self._active_tasks.get(k, []) and self._active_tasks[k].remove(t)
                if t in self._active_tasks.get(k, []) else None
            )

    async def __dispatch__(
        self,
        msg: InboundMessage,
    ) -> None:
        """Process a message: per-session serial, cross-session concurrent."""
        lock = self._session_locks.setdefault(msg.session_hash, asyncio.Lock())
        gate = self._concurrency_gate or nullcontext()
        async with lock, gate:
            try:
                on_stream = on_stream_end = None
                if msg.metadata.get("_wants_stream"):
                    print("---wants stream")
                    # Split one answer inot distinct stream segments.
                    stream_base_id = f"{msg.sender_hash}:{time.time_ns()}"
                    stream_segment = 0

                    def _current_stream_id() -> str:
                        return f"{stream_base_id}:{stream_segment}"

                    async def on_stream(delta: str) -> None:
                        meta = dict(msg.metadata or {})
                        meta["_stream_delta"] = True
                        meta["_stream_id"] = _current_stream_id()
                        await self.__send_outbound__(OutboundMessage(
                            session_hash=msg.session_hash, reply_to=msg.sender_hash,
                            content=delta,
                            metadata=meta,
                        ))

                    async def on_stream_end(*, resuming: bool = False) -> None:
                        nonlocal stream_segment
                        meta = dict(msg.metadata or {})
                        meta["_stream_end"] = True
                        meta["_resuming"] = resuming
                        meta["_stream_id"] = _current_stream_id()
                        await self.__send_outbound__(OutboundMessage(
                            session_hash=msg.session_hash, reply_to=msg.sender_hash,
                            content="",
                            metadata=meta,
                        ))
                        stream_segment += 1

                response = await self.__process_message__(
                    msg, on_stream=on_stream, on_stream_end=on_stream_end,
                )
                if response is not None:
                    await self.__send_outbound__(response)

            except asyncio.CancelledError:
                logger.info("Task cancelled for session {}", msg.session_hash)
                raise
            except Exception as e:
                logger.exception(f"Error processing message for session {msg.session_hash} - {e}")
                await self.__send_outbound__(OutboundMessage(
                    session_hash=msg.session_key, reply_to=msg.sender_hash,
                    content="Sorry, I encountered an error."
                ))

    async def __send_outbound__(
        self,
        msg: OutboundMessage,
    ) -> None:
        topic = f'agent:{self._provider_name}:ws'
        await self.pub.send_multipart([
            topic.encode('utf-8'),
            msgpack.packb(asdict(msg))
        ])

    async def __process_message__(
        self,
        msg: InboundMessage,
        on_progress: Callable[[str], Awaitable[None]] | None = None,
        on_stream: Callable[[str], Awaitable[None]] | None = None,
        on_stream_end: Callable[..., Awaitable[None]] | None = None,
    ) -> OutboundMessage | None:
        """Process a single inbound message and return the response."""
        # preview = msg.content[:80] + "..." if len(msg.content) > 80 else msg.content
        # logger.info("Processing message from {}:{}: {}", msg.sender_hash, msg.sender_hash, preview)

        # key = msg.session_hash
        # session = self.sessions.get_or_create(key)
        # if self._restore_runtime_checkpoint(session):
        #     self.sessions.save(session)
        
        initial_messages = [
            {"role": "system", "content": ""},
            # *history,
            {"role": "user", "content": msg.content},
        ]

        async def __agent_progress__(content: str, *, tool_hint: bool = False) -> None:
            meta=dict(msg.metadata or {})
            meta["_progress"]=True
            meta["_tool_hint"]=tool_hint
            await self.__send_outbound__(OutboundMessage(
                session_hash=msg.session_hash, reply_to=msg.sender_hash,
                content=content, metadata=meta,
            ))

        final_content, _, all_msgs, stop_reason = await self.__run_agent_loop__(
            initial_messages,
            on_progress=on_progress or __agent_progress__,
            on_stream=on_stream,
            on_stream_end=on_stream_end,
            channel=msg.session_hash,
            chat_id=msg.sender_hash,
            message_id=msg.metadata.get("message_id"),
        )

        if final_content is None or not final_content.strip():
            final_content = EMPTY_FINAL_RESPONSE_MESSAGE

        meta = dict(msg.metadata or {})
        if on_stream is not None:
            meta["_streamed"] = True
        return OutboundMessage(
            session_hash=msg.session_hash, reply_to=msg.sender_hash,
            content=final_content,
            metadata=meta,
        )

    async def __run_agent_loop__(
        self,
        initial_messages: list[dict],
        on_progress: Callable[..., Awaitable[None]] | None = None,
        on_stream: Callable[[str], Awaitable[None]] | None = None,
        on_stream_end: Callable[..., Awaitable[None]] | None = None,
        *,
        channel: str = "",
        chat_id: str = "",
        message_id: str = "",
    ) -> tuple[str | None, list[str], list[dict]]:
        """Run the agent iteration loop.
        *on_stream*: called with each content delta during streaming.
        *on_stream_end(resuming)*: called when a streaming session finishes.
        ``resuming=True`` means tool calls follow (spinner should restart);
        ``resuming=False`` means this is the final response.
        """
        loop_hook = _LoopHook(
            self,
            on_progress=on_progress,
            on_stream=on_stream,
            on_stream_end=on_stream_end,
            channel=channel,
            chat_id=chat_id,
            message_id=message_id,
        )
        hook: AgentHook = (
            CompositeHook([loop_hook] + self._extra_hooks)
            if self._extra_hooks
            else loop_hook
        )

        result = await self.runner.run(AgentRunSpec(
            initial_messages=initial_messages,
            tools=self.tools,
            model=self.model,
            max_iterations=self.max_iterations,
            max_tool_result_chars=self.max_tool_result_chars,
            hook=hook,
            error_message="Sorry, I encountered an error calling the AI model.",
            concurrent_tools=True,
        ))
        if result.stop_reason == "max_iterations":
            logger.warning(f"Max iterations ({self.max_iterations}) reached")
        elif result.stop_reason == "error":
            logger.error(f"LLM returned error: {(result.final_content or "")[:200]}")
        return result.final_content, result.tools_used, result.messages, result.stop_reason


    @staticmethod
    def _strip_think(
        text: str | None,
    ) -> str | None:
        """Remove <think>…</think> blocks that some models embed in content."""
        if not text:
            return None
        from easybot.utils.helpers import strip_think
        return strip_think(text) or None