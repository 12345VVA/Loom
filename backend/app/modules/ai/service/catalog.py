"""
内置 AI 厂商与模型清单。
"""
from __future__ import annotations

AI_MODEL_CATALOG = [
    {
        "code": "gemini",
        "name": "Google Gemini",
        "adapter": "gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "models": [
            {"code": "gemini-2.5-pro", "name": "Gemini 2.5 Pro", "model_type": "chat", "capabilities": "chat,vision,tools,stream", "context_window": 1048576},
            {"code": "gemini-2.5-flash", "name": "Gemini 2.5 Flash", "model_type": "chat", "capabilities": "chat,vision,tools,stream", "context_window": 1048576},
            {"code": "text-embedding-004", "name": "Text Embedding 004", "model_type": "embedding", "capabilities": "embedding"},
        ],
    },
    {
        "code": "claude",
        "name": "Anthropic Claude",
        "adapter": "claude",
        "base_url": "https://api.anthropic.com/v1",
        "models": [
            {"code": "claude-sonnet-4-5", "name": "Claude Sonnet 4.5", "model_type": "chat", "capabilities": "chat,vision,tools,stream,thinking", "context_window": 200000},
            {"code": "claude-opus-4-1", "name": "Claude Opus 4.1", "model_type": "chat", "capabilities": "chat,vision,tools,stream,thinking", "context_window": 200000},
            {"code": "claude-haiku-4-5", "name": "Claude Haiku 4.5", "model_type": "chat", "capabilities": "chat,vision,tools,stream", "context_window": 200000},
        ],
    },
    {
        "code": "deepseek",
        "name": "DeepSeek",
        "adapter": "deepseek",
        "base_url": "https://api.deepseek.com",
        "models": [
            {"code": "deepseek-v4-flash", "name": "DeepSeek V4 Flash", "model_type": "chat", "capabilities": "chat,stream,tools,json,thinking"},
            {"code": "deepseek-v4-pro", "name": "DeepSeek V4 Pro", "model_type": "chat", "capabilities": "chat,stream,tools,json,thinking"},
        ],
    },
    {
        "code": "volcengine-ark",
        "name": "火山方舟",
        "adapter": "volcengine-ark",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "models": [
            {"code": "doubao-seed-1-6", "name": "Doubao Seed 1.6", "model_type": "chat", "capabilities": "chat,stream,tools"},
            {"code": "doubao-embedding", "name": "Doubao Embedding", "model_type": "embedding", "capabilities": "embedding"},
            {"code": "doubao-seedream-5.0-lite", "name": "Doubao Seedream 5.0 Lite", "model_type": "image", "capabilities": "image,text-to-image,image-to-image"},
        ],
    },
    {
        "code": "bailian",
        "name": "阿里百炼",
        "adapter": "bailian",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": [
            {"code": "qwen-plus", "name": "Qwen Plus", "model_type": "chat", "capabilities": "chat,stream,tools"},
            {"code": "qwen-max", "name": "Qwen Max", "model_type": "chat", "capabilities": "chat,stream,tools"},
            {"code": "text-embedding-v4", "name": "Text Embedding V4", "model_type": "embedding", "capabilities": "embedding"},
        ],
    },
    {
        "code": "hunyuan",
        "name": "腾讯混元",
        "adapter": "hunyuan",
        "base_url": "https://api.hunyuan.cloud.tencent.com/v1",
        "models": [
            {"code": "hunyuan-turbos-latest", "name": "Hunyuan TurboS", "model_type": "chat", "capabilities": "chat,stream,tools"},
            {"code": "hunyuan-large", "name": "Hunyuan Large", "model_type": "chat", "capabilities": "chat,stream"},
        ],
    },
    {
        "code": "qianfan",
        "name": "百度千帆",
        "adapter": "qianfan",
        "base_url": "https://qianfan.baidubce.com/v2",
        "models": [
            {"code": "ernie-4.5-turbo-128k", "name": "ERNIE 4.5 Turbo 128K", "model_type": "chat", "capabilities": "chat,stream,tools"},
            {"code": "bge-large-zh", "name": "BGE Large ZH", "model_type": "embedding", "capabilities": "embedding"},
            {"code": "bce-reranker-base_v1", "name": "BCE Reranker Base", "model_type": "rerank", "capabilities": "rerank"},
        ],
    },
    {
        "code": "zhipu",
        "name": "智谱 GLM",
        "adapter": "zhipu",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "models": [
            {"code": "glm-4.6", "name": "GLM 4.6", "model_type": "chat", "capabilities": "chat,stream,tools"},
            {"code": "glm-4.5", "name": "GLM 4.5", "model_type": "chat", "capabilities": "chat,stream,tools"},
            {"code": "embedding-3", "name": "Embedding 3", "model_type": "embedding", "capabilities": "embedding"},
        ],
    },
    {
        "code": "minimax",
        "name": "MiniMax",
        "adapter": "minimax",
        "base_url": "https://api.minimax.chat/v1",
        "models": [
            {"code": "MiniMax-M2", "name": "MiniMax M2", "model_type": "chat", "capabilities": "chat,stream,tools"},
            {"code": "abab6.5s-chat", "name": "abab6.5s Chat", "model_type": "chat", "capabilities": "chat,stream"},
        ],
    },
    {
        "code": "mimo",
        "name": "小米 MiMo",
        "adapter": "mimo",
        "base_url": "",
        "models": [
            {"code": "MiMo-7B", "name": "MiMo 7B", "model_type": "chat", "capabilities": "chat,placeholder"},
        ],
    },
]


def get_catalog(provider_code: str | None = None) -> list[dict]:
    if provider_code:
        return [item for item in AI_MODEL_CATALOG if item["code"] == provider_code]
    return AI_MODEL_CATALOG
