"""Shared lifecycle hook primitives for agent runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from easybot.utils.logger import logger
from easybot.providers.base import LLMResponse, ToolCallRequest


@dataclass(slots=True)
class AgentHookContext:
    """Mutable per-iteration state exposed to runner hooks."""
    iteration: int
    messages: list[dict[str, Any]]
    response: LLMResponse | None = None
    usage: dict[str, int] = field(default_factory=dict)
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    tool_ressults: list[Any] = field(default_factory=list)
    tool_events: list[dict[str, str]] = field(default_factory=list)
    final_content: str | None = None
    stop_reason: str | None = None
    error: str | None = None


class AgentHook:
    """Minimal lifecycle surface for shared runner customization."""
    def __init__(
        self,
        reraise: bool = False,
    ) -> None:
        self._reraise = False

    def wants_streaming(self) -> bool:
        return False

    async def before_iteration(
        self,
        ctx: AgentHookContext,
    ) -> None:
        pass

    async def on_stream(
        self,
        ctx: AgentHookContext,
        delta: str,
    ) -> None:
        pass

    async def on_stream_end(
        self,
        ctx: AgentHookContext,
        *,
        resuming: bool,
    ) -> None:
        pass

    async def before_execute_tools(
        self,
        ctx: AgentHookContext,
    ) -> None:
        pass

    async def after_iteration(
        self,
        ctx: AgentHookContext,
    ) -> None:
        pass

    def finalize_content(
        self,
        ctx: AgentHookContext,
        content: str | None,
    ) -> str | None:
        return content


class CompositeHook(AgentHook):
    """Fan-out hook that delegates to an ordered list of hooks.
    Error isolation: async methods catch and log per-hook exceptions
    so a faulty custom hook cannot crash the agent loop.
    ``finalize_content`` is a pipeline (no isolation — bugs should surface).
    """
    __slots__ = ("_hooks",)

    def __init__(
        self,
        hooks: list[AgentHook],
    ) -> None:
        super().__init__()
        self._hooks = list(hooks)

    def wants_streaming(
        self,
    ) -> bool:
        return any(h.wants_streaming() for h in self._hooks)

    async def __for_each_hook_safe__(
        self,
        method_name: str,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        for h in self._hooks:
            if getattr(h, "_reraise", False):
                await getattr(h, method_name)(*args, **kwargs)
                continue

        try:
            await getattr(h, method_name)(*args, **kwargs)
        except Exception:
            logger.exception("AgentHook.{} error in {}", method_name, type(h).__name__)

    async def before_iteration(
        self,
        ctx: AgentHookContext,
    ) -> None:
        await self.__for_each_hook_safe__("before_iteration", ctx)

    async def on_stream(
        self,
        ctx: AgentHookContext,
        delta: str,
    ) -> None:
        await self.__for_each_hook_safe__("on_stream", ctx, delta)

    async def on_stream_end(
        self,
        ctx: AgentHookContext,
        *,
        resuming: bool,
    ) -> None:
        await self.__for_each_hook_safe__("on_stream_end", ctx, resuming=resuming)

    async def before_execute_tools(
        self,
        ctx: AgentHookContext,
    ) -> None:
        await self.__for_each_hook_safe__("before_execute_tools", ctx)

    async def after_iteration(
        self,
        ctx: AgentHookContext,
    ) -> None:
        await self.__for_each_hook_safe__("after_iteration", ctx)

    def finalize_content(
        self,
        ctx: AgentHookContext,
        content: str | None,
    ) -> str | None:
        for h in self._hooks:
            content = h.finalize_content(ctx, content)
        return content