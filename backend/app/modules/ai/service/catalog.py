"""
内置 AI 厂商与模型清单。
"""

from __future__ import annotations

import json

DEFAULT_TOAPIS_NORMAL_IMAGE_CONFIG = json.dumps(
    {
        "size": "1:1",
        "resolution": "1K",
        "_size_format": "ratio",
        "_allow_custom_size": True,
        "_sizes": [
            {"label": "1:1 (正方形)", "value": "1:1"},
            {"label": "3:4 (竖版绘本)", "value": "3:4"},
            {"label": "4:3 (横版配图)", "value": "4:3"},
            {"label": "16:9 (横屏宽幅)", "value": "16:9"},
            {"label": "9:16 (竖屏短视频)", "value": "9:16"},
            {"label": "3:2 (经典摄影)", "value": "3:2"},
            {"label": "2:3 (竖幅摄影)", "value": "2:3"},
        ],
        "_limits": {"max_n": 1},
    },
    ensure_ascii=False,
)

# ToAPIs gpt-image VIP/Official 版的像素尺寸档位。
#
# 注意：上游不兑现任意像素，会按宽高比做档位规范化。2026-09-21 实测：
#   请求 864x1152   -> 实收 768x1024
#   请求 1248x1664  -> 实收 1536x2048
#   请求 1024x1024  -> 实收 1024x1024（1:1 原样兑现）
# 因此 label 里直接标注实测产出，避免选了 864x1152 却拿到别的尺寸还查不出原因。
DEFAULT_TOAPIS_PIXEL_IMAGE_CONFIG = json.dumps(
    {
        "size": "1024x1024",
        "quality": "low",
        "_size_format": "pixel",
        "_allow_custom_size": True,
        "_sizes": [
            {"label": "1024x1024 (1:1)", "value": "1024x1024"},
            {"label": "1536x2048 (3:4 竖版，实测兑现)", "value": "1536x2048"},
            {"label": "768x1024 (3:4 竖版，实测兑现)", "value": "768x1024"},
            {"label": "864x1152 (3:4，上游会规范化为 768x1024)", "value": "864x1152"},
            {"label": "1152x864 (4:3 横板)", "value": "1152x864"},
            {"label": "1280x720 (16:9 横屏)", "value": "1280x720"},
            {"label": "720x1280 (9:16 竖屏)", "value": "720x1280"},
            {"label": "1536x1024 (3:2 摄影)", "value": "1536x1024"},
            {"label": "1024x1536 (2:3 竖版)", "value": "1024x1536"},
        ],
        "_limits": {"max_n": 1},
    },
    ensure_ascii=False,
)

# Poryf gpt-image-2.5 的像素尺寸档位（官方最大边长 3840px，实测请求尺寸精确兑现、无自动缩放）
DEFAULT_PORYF_IMAGE_CONFIG = json.dumps(
    {
        "size": "1024x1024",
        "quality": "low",
        "_size_format": "pixel",
        "_allow_custom_size": True,
        "_sizes": [
            {"label": "1024x1024 (1:1)", "value": "1024x1024"},
            {"label": "1536x1024 (3:2)", "value": "1536x1024"},
            {"label": "1024x1536 (2:3)", "value": "1024x1536"},
            {"label": "2048x2048 (1:1 2K)", "value": "2048x2048"},
            {"label": "2560x1440 (16:9 2K)", "value": "2560x1440"},
            {"label": "1440x2560 (9:16 2K)", "value": "1440x2560"},
            {"label": "3840x2160 (16:9 4K)", "value": "3840x2160"},
            {"label": "2160x3840 (9:16 4K)", "value": "2160x3840"},
        ],
        "_limits": {"max_n": 1},
    },
    ensure_ascii=False,
)

DEFAULT_SEEDREAM_IMAGE_CONFIG = json.dumps(
    {
        "size": "2048x2048",
        "_size_format": "pixel",
        "_allow_custom_size": True,
        "_sizes": [
            {"label": "2048x2048 (1:1)", "value": "2048x2048"},
            {"label": "2560x1440 (16:9)", "value": "2560x1440"},
            {"label": "1440x2560 (9:16)", "value": "1440x2560"},
            {"label": "2304x1728 (4:3)", "value": "2304x1728"},
            {"label": "1728x2304 (3:4)", "value": "1728x2304"},
        ],
        "_limits": {"max_n": 4},
    },
    ensure_ascii=False,
)

DEFAULT_BAILIAN_IMAGE_CONFIG = json.dumps(
    {
        "size": "1024x1024",
        "_size_format": "pixel",
        "_allow_custom_size": False,
        "_sizes": [
            {"label": "1024x1024 (1:1)", "value": "1024x1024"},
            {"label": "768x1024 (3:4)", "value": "768x1024"},
            {"label": "1024x768 (4:3)", "value": "1024x768"},
            {"label": "720x1280 (9:16)", "value": "720x1280"},
            {"label": "1280x720 (16:9)", "value": "1280x720"},
        ],
        "_limits": {"max_n": 4},
    },
    ensure_ascii=False,
)

AI_MODEL_CATALOG = [
    {
        "code": "gemini",
        "name": "Google Gemini",
        "adapter": "gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "models": [
            {
                "code": "gemini-2.5-pro",
                "name": "Gemini 2.5 Pro",
                "model_type": "chat",
                "capabilities": "chat,vision,tools,stream",
                "context_window": 1048576,
            },
            {
                "code": "gemini-2.5-flash",
                "name": "Gemini 2.5 Flash",
                "model_type": "chat",
                "capabilities": "chat,vision,tools,stream",
                "context_window": 1048576,
            },
            {
                "code": "text-embedding-004",
                "name": "Text Embedding 004",
                "model_type": "embedding",
                "capabilities": "embedding",
            },
        ],
    },
    {
        "code": "claude",
        "name": "Anthropic Claude",
        "adapter": "claude",
        "base_url": "https://api.anthropic.com/v1",
        "models": [
            {
                "code": "claude-sonnet-4-5",
                "name": "Claude Sonnet 4.5",
                "model_type": "chat",
                "capabilities": "chat,vision,tools,stream,thinking",
                "context_window": 200000,
            },
            {
                "code": "claude-opus-4-1",
                "name": "Claude Opus 4.1",
                "model_type": "chat",
                "capabilities": "chat,vision,tools,stream,thinking",
                "context_window": 200000,
            },
            {
                "code": "claude-haiku-4-5",
                "name": "Claude Haiku 4.5",
                "model_type": "chat",
                "capabilities": "chat,vision,tools,stream",
                "context_window": 200000,
            },
        ],
    },
    {
        "code": "deepseek",
        "name": "DeepSeek",
        "adapter": "deepseek",
        "base_url": "https://api.deepseek.com",
        "models": [
            {
                "code": "deepseek-v4-flash",
                "name": "DeepSeek V4 Flash",
                "model_type": "chat",
                "capabilities": "chat,stream,tools,json,thinking",
            },
            {
                "code": "deepseek-v4-pro",
                "name": "DeepSeek V4 Pro",
                "model_type": "chat",
                "capabilities": "chat,stream,tools,json,thinking",
            },
        ],
    },
    {
        "code": "volcengine-ark",
        "name": "火山方舟",
        "adapter": "volcengine-ark",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "models": [
            {
                "code": "doubao-seed-1-6",
                "name": "Doubao Seed 1.6",
                "model_type": "chat",
                "capabilities": "chat,stream,tools",
            },
            {
                "code": "doubao-embedding",
                "name": "Doubao Embedding",
                "model_type": "embedding",
                "capabilities": "embedding",
            },
            {
                "code": "doubao-seedream-5.0-lite",
                "name": "Doubao Seedream 5.0 Lite",
                "model_type": "image",
                "capabilities": "image,text-to-image,image-to-image",
                "default_config": DEFAULT_SEEDREAM_IMAGE_CONFIG,
            },
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
            {
                "code": "text-embedding-v4",
                "name": "Text Embedding V4",
                "model_type": "embedding",
                "capabilities": "embedding",
            },
            {
                "code": "wan2.6-t2i",
                "name": "Wan 2.6 Text to Image",
                "model_type": "image",
                "capabilities": "image,text-to-image",
                "default_config": DEFAULT_BAILIAN_IMAGE_CONFIG,
            },
            {
                "code": "wan2.5-t2i-preview",
                "name": "Wan 2.5 Text to Image Preview",
                "model_type": "image",
                "capabilities": "image,text-to-image",
                "default_config": DEFAULT_BAILIAN_IMAGE_CONFIG,
            },
            {
                "code": "wan2.2-t2i-flash",
                "name": "Wan 2.2 Text to Image Flash",
                "model_type": "image",
                "capabilities": "image,text-to-image",
                "default_config": DEFAULT_BAILIAN_IMAGE_CONFIG,
            },
        ],
    },
    {
        "code": "hunyuan",
        "name": "腾讯混元",
        "adapter": "hunyuan",
        "base_url": "https://api.hunyuan.cloud.tencent.com/v1",
        "models": [
            {
                "code": "hunyuan-turbos-latest",
                "name": "Hunyuan TurboS",
                "model_type": "chat",
                "capabilities": "chat,stream,tools",
            },
            {"code": "hunyuan-large", "name": "Hunyuan Large", "model_type": "chat", "capabilities": "chat,stream"},
        ],
    },
    {
        "code": "qianfan",
        "name": "百度千帆",
        "adapter": "qianfan",
        "base_url": "https://qianfan.baidubce.com/v2",
        "models": [
            {
                "code": "ernie-4.5-turbo-128k",
                "name": "ERNIE 4.5 Turbo 128K",
                "model_type": "chat",
                "capabilities": "chat,stream,tools",
            },
            {"code": "bge-large-zh", "name": "BGE Large ZH", "model_type": "embedding", "capabilities": "embedding"},
            {
                "code": "bce-reranker-base_v1",
                "name": "BCE Reranker Base",
                "model_type": "rerank",
                "capabilities": "rerank",
            },
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
    {
        "code": "toapis",
        "name": "ToAPIs",
        "adapter": "toapis",
        "base_url": "https://api.toapis.cn",
        "models": [
            {
                "code": "gpt-image-2.5-flare",
                "name": "GPT-Image-2.5 Flare",
                "model_type": "image",
                "capabilities": "image,text-to-image,image-to-image",
                "default_config": DEFAULT_TOAPIS_NORMAL_IMAGE_CONFIG,
            },
            {
                "code": "gpt-image-2.5-sunburst",
                "name": "GPT-Image-2.5 Sunburst",
                "model_type": "image",
                "capabilities": "image,text-to-image,image-to-image",
                "default_config": DEFAULT_TOAPIS_NORMAL_IMAGE_CONFIG,
            },
            {
                "code": "gpt-image-2.5-flare-vip",
                "name": "GPT-Image-2.5 Flare VIP",
                "model_type": "image",
                "capabilities": "image,text-to-image,image-to-image",
                "default_config": DEFAULT_TOAPIS_PIXEL_IMAGE_CONFIG,
            },
            {
                "code": "gpt-image-2.5-sunburst-vip",
                "name": "GPT-Image-2.5 Sunburst VIP",
                "model_type": "image",
                "capabilities": "image,text-to-image,image-to-image",
                "default_config": DEFAULT_TOAPIS_PIXEL_IMAGE_CONFIG,
            },
            {
                "code": "gpt-image-2.5-flare-official",
                "name": "GPT-Image-2.5 Flare Official",
                "model_type": "image",
                "capabilities": "image,text-to-image,image-to-image",
                "default_config": DEFAULT_TOAPIS_PIXEL_IMAGE_CONFIG,
            },
            {
                "code": "gpt-image-2.5-sunburst-official",
                "name": "GPT-Image-2.5 Sunburst Official",
                "model_type": "image",
                "capabilities": "image,text-to-image,image-to-image",
                "default_config": DEFAULT_TOAPIS_PIXEL_IMAGE_CONFIG,
            },
        ],
    },
    {
        "code": "poryf",
        "name": "Poryf（再来点Token）",
        "adapter": "poryf",
        "base_url": "https://token.poryf.com/v1",
        "models": [
            {
                "code": "gpt-image-2.5-flare",
                "name": "GPT-Image-2.5 Flare",
                "model_type": "image",
                "capabilities": "image,text-to-image,image-to-image",
                "default_config": DEFAULT_PORYF_IMAGE_CONFIG,
            },
            {
                "code": "gpt-image-2.5-sunburst",
                "name": "GPT-Image-2.5 Sunburst",
                "model_type": "image",
                "capabilities": "image,text-to-image,image-to-image",
                "default_config": DEFAULT_PORYF_IMAGE_CONFIG,
            },
        ],
    },
]


def get_catalog(provider_code: str | None = None) -> list[dict]:
    if provider_code:
        return [item for item in AI_MODEL_CATALOG if item["code"] == provider_code]
    return AI_MODEL_CATALOG
