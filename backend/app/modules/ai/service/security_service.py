"""
AI 安全服务，负责拦截提示词注入攻击并进行输出数据脱敏。
"""

import logging
import re
from typing import Any

from fastapi import HTTPException, status

from app.modules.ai.model.ai import AiRuntimeMessage

logger = logging.getLogger(__name__)

# 最大允许总字符数，防止 DoS
MAX_INPUT_LENGTH = 20000

# 恶意意图正则字典（包含常见的越狱/注入关键词）
# 忽略大小写
INJECTION_PATTERNS = [
    r"\bignore\s+(all\s+)?(previous\s+)?instructions\b",
    r"忽略.*?(之前|前面|所有)的指令",
    r"忽略所有的设定",
    r"(输出|打印|告诉我).*(系统提示词|系统指令|system\s+prompt|developer\s+prompt)",
    r"(让你|现在|可以|是个).*不受限制",
    r"(让你|现在|可以|是个).*无视规则",
    r"(尝试|进行|开始)?越狱(模式|操作)?",
    r"\bact\s+as\s+.*dan\s+mode\b",
    r"\bstands\s+for\s+do\s+anything\s+now\b",
]
INJECTION_REGEX = re.compile("|".join(INJECTION_PATTERNS), re.IGNORECASE)

# PII 脱敏正则
# 大陆手机号
PHONE_REGEX = re.compile(r"(?<!\d)(1[3-9]\d{9})(?!\d)")
# 简单身份证号 (18位)
ID_CARD_REGEX = re.compile(r"(?<!\d)(\d{6})(\d{8})(\d{3}[0-9Xx])(?!\d)")
# 邮箱
EMAIL_REGEX = re.compile(r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)")

# 凭据入库检测正则（长期记忆节点写入路径使用，设计 §9.3）：少量高置信模式。
# 现有 PII 正则不含凭据形态（现状核实 §2.3），此集为其补位；
# 定位是「入库质量提示」而非拦截——命中仅 warning 不阻断（讨论密钥管理是
# 合法内容），由管理页凭据警告列承接人工审计。
CREDENTIAL_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # OpenAI 风格 API key（\bsk- 词边界排除 risk-value 等英文单词内误伤）
    ("openai_style_key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    # PEM 私钥头
    ("pem_private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    # AWS Access Key ID（固定 AKIA 前缀 + 16 位大写字母数字）
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    # 通用赋值形态：password=xxxx / "apiKey": "xxxx"（值 ≥16 字符，短词不触发；
    # 键后允许引号以覆盖 JSON "token": "value" 形态）
    (
        "credential_assignment",
        re.compile(
            r"\b(api[_-]?key|secret|token|password|passwd|pwd)\b['\"]?\s*[=:]\s*['\"]?[A-Za-z0-9+/_=-]{16,}",
            re.IGNORECASE,
        ),
    ),
]


def detect_credential_patterns(text: str) -> list[str]:
    """检测文本中的高置信凭据形态，返回命中模式名列表（warning 日志 / 管理页标记用）。"""
    if not text:
        return []
    return [name for name, pattern in CREDENTIAL_PATTERNS if pattern.search(text)]


class AiSecurityService:
    @staticmethod
    def check_input_safety(messages: list[AiRuntimeMessage | dict[str, Any]]) -> None:
        """
        检查输入安全性。如果存在安全风险，抛出异常。
        """
        total_length = 0
        for msg in messages:
            # 注意：system 消息同样需要经过注入检测。
            # 调用方 runtime_service 直接将用户提交的 payload.messages 传入此处，
            # role 字段无服务端约束，攻击者可通过构造 role="system" 的消息绕过校验，
            # 因此不得对 system 角色做任何跳过处理。
            content = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
            # 多模态 content（list 形式，如 OpenAI [{type:'text', text:'...'}]）：提取文本部分检测，
            # 避免对非字符串 content 静默跳过导致注入检测被绕过
            if isinstance(content, list):
                texts: list[str] = []
                for item in content:
                    if isinstance(item, dict):
                        t = item.get("text") if "text" in item else item.get("content")
                        if isinstance(t, str):
                            texts.append(t)
                    elif isinstance(item, str):
                        texts.append(item)
                content = "\n".join(texts)
            if not isinstance(content, str):
                continue

            total_length += len(content)

            # 检查 DoS
            if total_length > MAX_INPUT_LENGTH:
                logger.warning(f"AI 调用被拦截: 输入长度超限 ({total_length} > {MAX_INPUT_LENGTH})")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="请求内容过长，为防止系统过载已被拦截。"
                )

            # 检查 Prompt Injection / Jailbreak
            if INJECTION_REGEX.search(content):
                logger.warning(f"AI 调用被拦截: 疑似提示词注入攻击. Content Snippet: {content[:100]}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="检测到潜在的安全风险（如提示词注入或越狱），请求已被拦截。",
                )

    @staticmethod
    def mask_sensitive_output(text: str) -> str:
        """
        对模型输出进行 PII 脱敏处理。
        """
        if not text or not isinstance(text, str):
            return text

        masked_text = text

        # 脱敏手机号 (保留前3后4)
        def mask_phone(match):
            phone = match.group(1)
            return f"{phone[:3]}****{phone[7:]}"

        masked_text = PHONE_REGEX.sub(mask_phone, masked_text)

        # 脱敏身份证 (保留前6后4)
        def mask_id_card(match):
            return f"{match.group(1)}********{match.group(3)}"

        masked_text = ID_CARD_REGEX.sub(mask_id_card, masked_text)

        # 脱敏邮箱 (隐藏用户名中间部分)
        def mask_email(match):
            email = match.group(1)
            parts = email.split("@")
            user_part = parts[0]
            domain_part = parts[1]
            if len(user_part) <= 2:
                user_part = "***"
            elif len(user_part) <= 5:
                user_part = f"{user_part[0]}***{user_part[-1]}"
            else:
                user_part = f"{user_part[:2]}***{user_part[-2:]}"
            return f"{user_part}@{domain_part}"

        masked_text = EMAIL_REGEX.sub(mask_email, masked_text)

        return masked_text

    @staticmethod
    def mask_sensitive_dict(data: Any) -> Any:
        """
        递归脱敏 dict / list 结构中的所有字符串叶子值。

        用于工作流执行日志、SSE 推送等「落库/传输副本」的 PII 脱敏：
        叶子字符串走 mask_sensitive_output；dict / list 递归处理；其余类型原样返回。
        运行时状态不应调用此方法（会破坏下游节点对原始 PII 数据的计算）。
        """
        if isinstance(data, str):
            return AiSecurityService.mask_sensitive_output(data)
        if isinstance(data, dict):
            return {key: AiSecurityService.mask_sensitive_dict(value) for key, value in data.items()}
        if isinstance(data, list):
            return [AiSecurityService.mask_sensitive_dict(item) for item in data]
        return data
