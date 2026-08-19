"""Python client for Midjourney image generation workflows on MuAPI."""

import os
import time
from typing import Any, Dict, List, Optional

import requests


DEFAULT_BASE_URL = "https://api.muapi.ai/api/v1"
MODEL_ENDPOINTS = {
    "midjourney-v7": "midjourney-v7",
    "midjourney-v8": "midjourney-v8",
    "midjourney-niji": "midjourney-niji",
}
SUPPORTED_ASPECT_RATIOS = frozenset({"1:1", "16:9", "9:16", "3:4", "4:3", "21:9"})
TERMINAL_SUCCESS_STATUSES = frozenset({"completed", "success", "succeeded", "done"})
TERMINAL_FAILURE_STATUSES = frozenset({"failed", "error", "cancelled", "canceled"})


class MidjourneyAPI:
    """Submit Midjourney V7, V8, and Niji jobs and retrieve their results."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        session: Optional[requests.Session] = None,
    ):
        self.api_key = api_key or os.getenv("MUAPI_API_KEY")
        if not self.api_key:
            raise ValueError("An API key is required. Set MUAPI_API_KEY or pass api_key.")

        configured_base_url = base_url or os.getenv("MIDJOURNEY_API_BASE_URL") or DEFAULT_BASE_URL
        self.base_url = configured_base_url.rstrip("/")
        self.headers = {"x-api-key": self.api_key, "Content-Type": "application/json"}
        self.session = session or requests.Session()

    def generate(
        self,
        prompt: str,
        *,
        model: str = "midjourney-v8",
        image_url: Optional[str] = None,
        aspect_ratio: str = "1:1",
        stylize: int = 100,
        chaos: int = 0,
        weird: int = 0,
        negative_prompt: Optional[str] = None,
        seed: Optional[int] = None,
        webhook_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate four images with Midjourney V7, V8, or Niji."""
        self._validate_generation(
            prompt,
            model=model,
            aspect_ratio=aspect_ratio,
            stylize=stylize,
            chaos=chaos,
            weird=weird,
            seed=seed,
        )
        payload = self._without_none(
            {
                "prompt": prompt,
                "image_url": image_url,
                "aspect_ratio": aspect_ratio,
                "stylize": stylize,
                "chaos": chaos,
                "weird": weird,
                "negative_prompt": negative_prompt,
                "seed": seed,
                "webhook_url": webhook_url,
            }
        )
        return self._post(MODEL_ENDPOINTS[model], payload)

    def v8(self, prompt: str, **kwargs: Any) -> Dict[str, Any]:
        """Generate four images with Midjourney V8."""
        return self.generate(prompt, model="midjourney-v8", **kwargs)

    def v7(self, prompt: str, **kwargs: Any) -> Dict[str, Any]:
        """Generate four images with Midjourney V7."""
        return self.generate(prompt, model="midjourney-v7", **kwargs)

    def niji(self, prompt: str, **kwargs: Any) -> Dict[str, Any]:
        """Generate four anime or illustration-style images with Midjourney Niji."""
        return self.generate(prompt, model="midjourney-niji", **kwargs)

    def text_to_image(self, prompt: str, **kwargs: Any) -> Dict[str, Any]:
        """Compatibility alias for :meth:`v8`, the default image workflow."""
        return self.v8(prompt, **kwargs)

    def get_result(self, request_id: str) -> Dict[str, Any]:
        """Retrieve the current status and output for a submitted job."""
        if not request_id:
            raise ValueError("request_id is required.")
        response = self.session.get(
            f"{self.base_url}/predictions/{request_id}/result",
            headers=self.headers,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def wait_for_completion(
        self,
        request_id: str,
        poll_interval: float = 5,
        timeout: float = 900,
    ) -> Dict[str, Any]:
        """Poll until a job completes, fails, or reaches the timeout."""
        if poll_interval < 0:
            raise ValueError("poll_interval must be zero or greater.")
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero.")

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = self.get_result(request_id)
            status = str(result.get("status", "")).lower()
            if status in TERMINAL_SUCCESS_STATUSES:
                return result
            if status in TERMINAL_FAILURE_STATUSES:
                detail = result.get("error") or result.get("message") or result
                raise RuntimeError(f"Midjourney generation {status}: {detail}")

            remaining = deadline - time.monotonic()
            if remaining > 0:
                time.sleep(min(poll_interval, remaining))

        raise TimeoutError(f"Timed out waiting for Midjourney job {request_id}.")

    def generate_and_wait(
        self,
        prompt: str,
        *,
        poll_interval: float = 5,
        timeout: float = 900,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Submit a generation and block until the final result is available."""
        submission = self.generate(prompt, **kwargs)
        request_id = submission.get("request_id")
        if not request_id:
            raise RuntimeError(f"No request_id in submission response: {submission}")
        return self.wait_for_completion(request_id, poll_interval=poll_interval, timeout=timeout)

    @staticmethod
    def extract_image_urls(result: Dict[str, Any]) -> List[str]:
        """Extract generated image URLs from a completed MuAPI result."""
        outputs = result.get("outputs")
        if isinstance(outputs, list):
            return [str(item) for item in outputs if item]
        if isinstance(outputs, str) and outputs:
            return [outputs]

        output = result.get("output")
        if isinstance(output, dict):
            images = output.get("images") or output.get("image")
            if isinstance(images, list):
                return [str(item) for item in images if item]
            if isinstance(images, str) and images:
                return [images]
        if isinstance(output, list):
            return [str(item) for item in output if item]
        if isinstance(output, str) and output:
            return [output]
        return []

    def _post(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        response = self.session.post(
            f"{self.base_url}/{endpoint}",
            json=payload,
            headers=self.headers,
            timeout=120,
        )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _without_none(payload: Dict[str, Any]) -> Dict[str, Any]:
        return {key: value for key, value in payload.items() if value is not None}

    @staticmethod
    def _validate_generation(
        prompt: str,
        *,
        model: str,
        aspect_ratio: str,
        stylize: int,
        chaos: int,
        weird: int,
        seed: Optional[int],
    ) -> None:
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must be a non-empty string.")
        if model not in MODEL_ENDPOINTS:
            supported = ", ".join(MODEL_ENDPOINTS)
            raise ValueError(f"Unsupported model {model!r}. Choose one of: {supported}.")
        if aspect_ratio not in SUPPORTED_ASPECT_RATIOS:
            supported = ", ".join(sorted(SUPPORTED_ASPECT_RATIOS))
            raise ValueError(f"Unsupported aspect_ratio {aspect_ratio!r}. Choose one of: {supported}.")
        if not 0 <= stylize <= 1000:
            raise ValueError("stylize must be between 0 and 1000.")
        if not 0 <= chaos <= 100:
            raise ValueError("chaos must be between 0 and 100.")
        if not 0 <= weird <= 3000:
            raise ValueError("weird must be between 0 and 3000.")
        if seed is not None and not 0 <= seed <= 4294967295:
            raise ValueError("seed must be between 0 and 4294967295.")
