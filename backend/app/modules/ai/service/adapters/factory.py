from __future__ import annotations

from app.modules.ai.model.ai import AiProvider
from app.modules.ai.service.adapters.claude import ClaudeAdapter
from app.modules.ai.service.adapters.gemini import GeminiAdapter
from app.modules.ai.service.adapters.ollama import OllamaAdapter
from app.modules.ai.service.adapters.openai_compatible import OpenAICompatibleAdapter
from app.modules.ai.service.adapters.openai_http import OpenAIHttpAdapter


class BailianAdapter(OpenAIHttpAdapter):
    default_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"


class VolcengineArkAdapter(OpenAIHttpAdapter):
    default_base_url = "https://ark.cn-beijing.volces.com/api/v3"


class HunyuanAdapter(OpenAIHttpAdapter):
    default_base_url = "https://api.hunyuan.cloud.tencent.com/v1"


class QianfanAdapter(OpenAIHttpAdapter):
    default_base_url = "https://qianfan.baidubce.com/v2"


class ZhipuAdapter(OpenAIHttpAdapter):
    default_base_url = "https://open.bigmodel.cn/api/paas/v4"


class MiniMaxAdapter(OpenAIHttpAdapter):
    default_base_url = "https://api.minimax.chat/v1"


class MimoAdapter(OpenAIHttpAdapter):
    default_base_url = ""

    def test(self) -> dict:
        if not self.base_url:
            return {"success": False, "message": "小米 MiMo 尚未配置稳定公开 API baseUrl，请在厂商配置中补充"}
        return super().test()


ADAPTERS = {
    "openai-compatible": OpenAICompatibleAdapter,
    "ollama": OllamaAdapter,
    "gemini": GeminiAdapter,
    "claude": ClaudeAdapter,
    "volcengine-ark": VolcengineArkAdapter,
    "bailian": BailianAdapter,
    "hunyuan": HunyuanAdapter,
    "qianfan": QianfanAdapter,
    "zhipu": ZhipuAdapter,
    "minimax": MiniMaxAdapter,
    "mimo": MimoAdapter,
}


def build_adapter(provider: AiProvider):
    adapter_cls = ADAPTERS.get(provider.adapter)
    if adapter_cls is None:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不支持的模型厂商适配器")
    return adapter_cls(provider)
