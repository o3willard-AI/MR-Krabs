"""Google Vertex AI provider adapter."""
from __future__ import annotations
import time
from typing import AsyncIterator, List, Optional
from .base_provider import BaseProviderAdapter, LLMResponse, ModelInfo

class VertexAdapter(BaseProviderAdapter):
    provider_name = "vertex"
    display_name = "Google Vertex AI"
    default_model = "gemini-2.5-flash"
    env_var = "GOOGLE_APPLICATION_CREDENTIALS"
    docs_url = "https://cloud.google.com/vertex-ai/docs"

    def __init__(self, config=None, name=""):
        super().__init__(config, name or "vertex")
        self._project_id = self.get_config("vertex_project", env_var="VERTEX_PROJECT") or ""
        self._region = self.get_config("vertex_region", default="us-central1")

    async def complete(self, messages, model=None, **kwargs):
        import aiohttp
        model = model or self.default_model
        
        # Convert messages to Gemini format
        contents = []
        system_instruction = None
        for msg in messages:
            if msg["role"] == "system":
                system_instruction = {"parts": [{"text": msg["content"]}]}
            else:
                role = "user" if msg["role"] == "user" else "model"
                contents.append({"role": role, "parts": [{"text": msg["content"]}]})
        
        url = (f"https://{self._region}-aiplatform.googleapis.com/v1/"
               f"projects/{self._project_id}/locations/{self._region}/"
               f"publishers/google/models/{model}:generateContent")
        
        payload = {"contents": contents}
        if system_instruction:
            payload["systemInstruction"] = system_instruction
        
        # Get access token
        token = await self._get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        
        start = time.monotonic()
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                data = await resp.json()
                latency = (time.monotonic() - start) * 1000
                
                if resp.status != 200:
                    error = data.get("error", {}).get("message", str(data))
                    raise Exception(f"Vertex error {resp.status}: {error}")
                
                candidates = data.get("candidates", [])
                text = ""
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    text = "".join(p.get("text", "") for p in parts)
                
                usage = data.get("usageMetadata", {})
                
                return LLMResponse(
                    content=text,
                    model=model,
                    prompt_tokens=usage.get("promptTokenCount", 0),
                    completion_tokens=usage.get("candidatesTokenCount", 0),
                    tokens_used=usage.get("totalTokenCount", 0),
                    finish_reason=candidates[0].get("finishReason", "STOP").lower() if candidates else "stop",
                    latency_ms=latency,
                    raw_response=data,
                )

    async def _get_access_token(self):
        """Get Google Cloud access token from service account."""
        import os, json
        creds_path = os.getenv(self.env_var, "")
        if not creds_path:
            raise Exception("GOOGLE_APPLICATION_CREDENTIALS not set")
        
        with open(creds_path) as f:
            creds = json.load(f)
        
        import aiohttp
        from datetime import datetime, timedelta
        import jwt  # PyJWT for signing
        
        now = datetime.utcnow()
        assertion = {
            "iss": creds["client_email"],
            "scope": "https://www.googleapis.com/auth/cloud-platform",
            "aud": creds["token_uri"],
            "exp": now + timedelta(minutes=30),
            "iat": now,
        }
        
        signed = jwt.encode(assertion, creds["private_key"], algorithm="RS256")
        
        async with aiohttp.ClientSession() as session:
            async with session.post(creds["token_uri"], data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": signed,
            }) as resp:
                token_data = await resp.json()
                return token_data["access_token"]

    async def stream(self, messages, model=None, **kwargs):
        # Vertex streaming not yet implemented
        raise NotImplementedError("Vertex streaming not yet implemented")

    def list_models(self):
        return [
            ModelInfo(name="gemini-2.5-pro", context_window=2000000, max_output_tokens=65536,
                     capabilities=["vision", "function_calling"]),
            ModelInfo(name="gemini-2.5-flash", context_window=1048576, max_output_tokens=65536,
                     capabilities=["vision"]),
            ModelInfo(name="gemini-2.0-flash", context_window=1048576, max_output_tokens=8192,
                     capabilities=["vision"]),
        ]

    def validate_config(self):
        import os
        return bool(self._project_id) and bool(os.getenv(self.env_var))