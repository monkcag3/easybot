
from __future__ import annotations

import uuid
import json
import asyncio
from typing import Any, Awaitable, Callable
from llama_cpp import Llama

from easybot.providers.base import LLMProvider, LLMResponse, ToolCallRequest
from easybot.utils.logger import logger


class LlamaCppProvider(LLMProvider):

    def __init__(
        self,
        api_key: str = "no-key",
        api_base: str = "http://localhost:8000/v1",
        default_model: str = "default",
        extra_headers: dict[str, Any] | None = None,
    ):
        super().__init__(api_key, api_base)
        self.default_model = default_model

        self.llm = Llama(
            model_path=extra_headers["model_path"],
            n_ctx=8192,
            n_threads=4,
            n_gpu_layers=0,
            verbose=False,
        )

        self.ALLOWED_MESSAGE_KEYS = frozenset(
            {"role", "content", "tool_calls", "tool_call_id", "name"}
        )

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        reasoning_effort: str | None = None,
        tool_choice: str | dict[str, Any] | None = None
    ) -> LLMResponse:
        try:
            # 1. 清理消息
            sanitized = self._sanitize_request_messages(
                messages, self.ALLOWED_MESSAGE_KEYS
            )
            sanitized = self._sanitize_empty_content(sanitized)

            # 2. 构建提示词(支持函数调用)
            prompt = self._build_chat_prompt(sanitized, tools)

            # 3. 异步执行推理(不阻塞asyncio)
            loop = asyncio.get_event_loop()
            raw_output = await loop.run_in_executor(
                None,
                self._run_inference,
                prompt,
                0.7,    #temperature,
                8192, #max_tokens
            )

            # 4. 解析输出：文本/工具调用
            content, tool_calls = self._parse_response(raw_output.strip(), tools)

            # 5. 返回标准LLMResponse
            return LLMResponse(
                content=content,
                tool_calls=tool_calls,
                finish_reason="stop",
                usage={}
            )
        except Exception as e:
            logger.error(f"LlamaCpp 推理异常: {str(e)}")
            return LLMResponse(
                content=f"本地模型推理失败: {str(e)}",
                finish_reason="error"
            )


    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        reasoning_effort: str | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        on_content_delta: Callable[[str], Awaitable[None]] | None = None,
    ) -> LLMResponse:
        try:
            # 1. 清理消息
            sanitized = self._sanitize_request_messages(
                messages, self.ALLOWED_MESSAGE_KEYS
            )
            sanitized = self._sanitize_empty_content(sanitized)

            # 2. 构建提示词(支持函数调用)
            prompt = self._build_chat_prompt(sanitized, tools)

            # 3. 异步执行推理(不阻塞asyncio)
            stream = self.llm.create_chat_completion(
                prompt=prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                stop=["<|end|>", "<|user|>", "<|system|>"],
                stream=True,
            )
            async for chunk in stream:
                print(chunk)


                # 4. 解析输出：文本/工具调用
                content, tool_calls = self._parse_response(chunk.strip(), tools)

            # 5. 返回标准LLMResponse
            return LLMResponse(
                content=None,
                tool_calls=tool_calls,
                finish_reason="stop",
                usage={}
            )
        except Exception as e:
            logger.error(f"LlamaCpp 推理异常: {str(e)}")
            return LLMResponse(
                content=f"本地模型推理失败: {str(e)}",
                finish_reason="error"
            )

    def _build_chat_prompt(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict] | None = None,
    ):
        system_prompt = ""

        if tools:
            tool_desc = json.dumps(tools, ensure_ascii=False, indent=2)
            system_prompt = f"""
你是一个AI助手，必须严格按照规则调用工具。
可用工具：
{tool_desc}

输出规则：
1. 需要调用工具时，必须输出**纯JSON**，格式如下：
{{"name": "工具名", "parameters": {{参数}}}}

2. 不需要调用工具，直接回答问题。
3. 不要输出多余内容。
""".strip()

        prompt = ""
        if system_prompt:
            prompt += f"<|system|>\n{system_prompt}\n<|end|>\n"

        for msg in messages:
            role = msg["role"]
            content = msg.get("content", "")
            prompt += f"<|{role}|>\n{content}\n<|end|>\n"

        prompt += "<|assistant|>\n"
        return prompt

    def _run_inference(
        self,
        prompt: str,
        temperature: float,
        max_tokens: int,
    ):
        output = self.llm.create_completion(
            prompt=prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            stop=["<|end|>", "<|user|>", "<|system|>"],
            echo=False,
        )
        return output['choices'][0]["text"].strip()


    def _parse_response(
        self,
        text: str,
        tools: list[dict[str, Any]] | None = None,
    ):
        tool_calls = []
        if not tools:
            return text, []

        try:
            tool_data = json.loads(text)
            if "name" in tool_data and "parameters" in tool_data:
                tool_call = ToolCallRequest(
                    id=f"call_{uuid.uuid4().hex[:8]}",
                    name=tool_data["name"],
                    arguments=tool_data["parameters"],
                )
                tool_calls.append(tool_call)
                return None, tool_calls
        except:
            pass
        return text, []

    def get_default_model(self) -> str:
        return self.default_model

