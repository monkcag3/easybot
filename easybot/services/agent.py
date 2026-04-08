
from easybot.agent.loop import AgentLoop
from easybot.config.schema import Config


async def start_agent(
    config: Config,
):
    from easybot.providers.base import GenerationSettings
    from easybot.providers import LlamaCppProvider

    model = config.agents.defaults.model
    provider_name = config.get_provider_name(model)
    p = config.get_provider(model)
    print(model, provider_name, p)
    
    provider = LlamaCppProvider(
        api_key=p.api_key if p else "no-key",
        api_base=config.get_api_base(model) or "http://localhost:8000",
        default_model=model,
        extra_headers=p.extra_headers if p else None,
    )
    print("load llama-cpp")

    defaults = config.agents.defaults
    provider.generation = GenerationSettings(
        temperature=defaults.temperature,
        max_tokens=defaults.max_tokens,
        reasoning_effort=defaults.reasoning_effort,
    )
  
    agent = AgentLoop(
        provider=provider
    )
    await agent.run()