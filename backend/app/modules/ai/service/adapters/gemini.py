from __future__ import annotations

import base64
from typing import Any

import httpx

from app.modules.ai.service.adapters.base import BaseHttpAdapter, UnsupportedCapabilityError, iter_sse_events, loads_json, normalize_usage


class GeminiAdapter(BaseHttpAdapter):
    default_base_url = "https://generativelanguage.googleapis.com/v1beta"
    supported_capabilities = {"chat", "stream_chat", "embedding", "image"}

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["x-goog-api-key"] = self.api_key
        return headers

    def chat(self, *, model: str, messages: list[dict[str, Any]], options: dict[str, Any]) -> dict:
        call_options = dict(options or {})
        response_format = call_options.pop("response_format", None)
        generation_config = call_options.pop("generationConfig", call_options.pop("generation_config", {}))
        if not isinstance(generation_config, dict):
            generation_config = {}
        if response_format:
            generation_config["responseMimeType"] = "application/json"

        payload = {
            "contents": [_gemini_content(item) for item in messages if item.get("role") != "system"],
            **call_options,
        }
        if generation_config:
            payload["generationConfig"] = generation_config

        system_text = "\n".join(item.get("content", "") for item in messages if item.get("role") == "system")
        if system_text:
            payload["systemInstruction"] = {"parts": [{"text": system_text}]}
        data, response = self._post(f"/models/{model}:generateContent", payload, self._headers())
        candidate = (data.get("candidates") or [{}])[0]
        parts = ((candidate.get("content") or {}).get("parts") or [])
        return {
            "content": "\n".join(part.get("text", "") for part in parts if part.get("text")),
            "raw": data,
            "usage": normalize_usage(data.get("usageMetadata")),
            "requestId": response.headers.get("x-request-id"),
        }

    def stream_chat(self, *, model: str, messages: list[dict[str, Any]], options: dict[str, Any]):
        call_options = dict(options or {})
        response_format = call_options.pop("response_format", None)
        generation_config = call_options.pop("generationConfig", call_options.pop("generation_config", {}))
        if not isinstance(generation_config, dict):
            generation_config = {}
        if response_format:
            generation_config["responseMimeType"] = "application/json"

        payload = {
            "contents": [_gemini_content(item) for item in messages if item.get("role") != "system"],
            **call_options,
        }
        if generation_config:
            payload["generationConfig"] = generation_config

        system_text = "\n".join(item.get("content", "") for item in messages if item.get("role") == "system")
        if system_text:
            payload["systemInstruction"] = {"parts": [{"text": system_text}]}
        path = f"/models/{model}:streamGenerateContent?alt=sse"
        with httpx.stream("POST", f"{self.base_url}{path}", json=payload, headers=self._headers(), timeout=self.timeout) as response:
            response.raise_for_status()
            request_id = response.headers.get("x-request-id")
            for event in iter_sse_events(response.iter_lines()):
                data = loads_json(event.get("data"))
                candidate = (data.get("candidates") or [{}])[0]
                parts = ((candidate.get("content") or {}).get("parts") or [])
                for part in parts:
                    text = part.get("text")
                    if text:
                        yield {"event": "delta", "content": text, "raw": data, "requestId": request_id}
                usage = normalize_usage(data.get("usageMetadata"))
                finish_reason = candidate.get("finishReason")
                if usage or finish_reason:
                    yield {"event": "done", "raw": data, "usage": usage, "finishReason": finish_reason, "requestId": request_id}

    def embedding(self, *, model: str, input: str | list[str], options: dict[str, Any]) -> dict:
        texts = input if isinstance(input, list) else [input]
        data_items = []
        for text in texts:
            data, _ = self._post(
                f"/models/{model}:embedContent",
                {"content": {"parts": [{"text": text}]}, **options},
                self._headers(),
            )
            data_items.append({"embedding": (data.get("embedding") or {}).get("values", [])})
        return {"data": data_items, "raw": {"data": data_items}, "usage": {}}

    def image(self, *, model: str, prompt: str, options: dict[str, Any]) -> dict:
        normalized_options = dict(options or {})
        parts = []
        image_val = normalized_options.pop("image", None)

        if image_val:
            if isinstance(image_val, list):
                for img in image_val:
                    part = _prepare_gemini_image_part(img)
                    if part:
                        parts.append(part)
            elif isinstance(image_val, str):
                part = _prepare_gemini_image_part(image_val)
                if part:
                    parts.append(part)

        parts.append({"text": prompt})
        
        generation_config = {"responseModalities": ["TEXT", "IMAGE"]}
        for k, v in normalized_options.items():
            if k not in {"n", "response_format", "watermark"}:
                generation_config[k] = v

        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": generation_config
        }
        
        data, response = self._post(f"/models/{model}:generateContent", payload, self._headers())
        
        output_images = []
        candidates = data.get("candidates") or []
        if candidates:
            candidate = candidates[0]
            parts_output = (candidate.get("content") or {}).get("parts") or []
            for part in parts_output:
                if "inlineData" in part:
                    inline_data = part["inlineData"]
                    output_images.append({
                        "b64_json": inline_data.get("data")
                    })

        return {
            "data": output_images,
            "raw": data,
            "usage": normalize_usage(data.get("usageMetadata")),
            "requestId": response.headers.get("x-request-id")
        }

    def video(self, *, model: str, prompt: str, options: dict[str, Any]) -> dict:
        raise UnsupportedCapabilityError("Gemini 视频生成需按具体模型 API 继续扩展")

    def test(self) -> dict:
        data, _ = self._get("/models", self._headers())
        return {"success": True, "count": len(data.get("models", []))}

    def list_models(self) -> list[dict[str, Any]]:
        data, _ = self._get("/models", self._headers())
        result: list[dict[str, Any]] = []
        for item in data.get("models", []):
            if not isinstance(item, dict):
                continue
            raw_name = item.get("name") or ""
            code = raw_name.removeprefix("models/") or item.get("displayName")
            if code:
                result.append({"code": str(code), "name": str(item.get("displayName") or code)})
        return result


def _gemini_content(message: dict[str, Any]) -> dict:
    role = "model" if message.get("role") == "assistant" else "user"
    return {"role": role, "parts": [{"text": str(message.get("content") or "")}]}


MAX_IMAGE_DOWNLOAD_SIZE = 10 * 1024 * 1024  # 10MB


def _prepare_gemini_image_part(val: str) -> dict | None:
    if not isinstance(val, str):
        return None
    if val.startswith("data:"):
        try:
            header, b64_data = val.split(",", 1)
            mime_type = header.split(";")[0].split(":")[1]
            return {"inlineData": {"mimeType": mime_type, "data": b64_data}}
        except Exception:
            return None
    elif val.startswith("http://") or val.startswith("https://"):
        try:
            with httpx.stream("GET", val, timeout=15) as r:
                r.raise_for_status()
                content_length = r.headers.get("content-length")
                if content_length and int(content_length) > MAX_IMAGE_DOWNLOAD_SIZE:
                    raise ValueError(f"Image size exceeds limit: {content_length} bytes")
                
                chunks = []
                bytes_read = 0
                for chunk in r.iter_bytes(chunk_size=8192):
                    bytes_read += len(chunk)
                    if bytes_read > MAX_IMAGE_DOWNLOAD_SIZE:
                        raise ValueError("Image size exceeds limit (10MB)")
                    chunks.append(chunk)
                content = b"".join(chunks)
                
                mime_type = r.headers.get("content-type", "image/png")
                b64_data = base64.b64encode(content).decode("utf-8")
                return {"inlineData": {"mimeType": mime_type, "data": b64_data}}
        except Exception:
            return None
    return None
