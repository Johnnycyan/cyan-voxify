from __future__ import annotations

import asyncio
import base64
import io
import logging
from typing import Optional

from mistralai.client import Mistral
from mistralai.client.errors import SDKError

from bot.utils.sanitize import MAX_TTS_LENGTH

log = logging.getLogger(__name__)

MODEL = "voxtral-mini-tts-2603"
_MAX_RETRIES = 3
_RETRY_DELAY = 1.0  # seconds


class TTSService:
    def __init__(self, api_key: str) -> None:
        self._client = Mistral(api_key=api_key)

    async def generate_speech(self, text: str, voice_id: str) -> Optional[bytes]:
        """Generate audio bytes from *text* using *voice_id*.

        Returns ``None`` if the API call fails after retries.  The caller is
        expected to have already sanitised the text; this method only enforces
        the length cap.
        """
        truncated = text[:MAX_TTS_LENGTH]

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                response = await asyncio.get_running_loop().run_in_executor(
                    None,
                    lambda: self._client.audio.speech.complete(
                        model=MODEL,
                        input=truncated,
                        voice_id=voice_id,
                        response_format="wav",
                    ),
                )
                return base64.b64decode(response.audio_data)
            except SDKError as exc:
                if (
                    attempt < _MAX_RETRIES
                    and exc.status_code is not None
                    and exc.status_code >= 500
                ):
                    log.warning(
                        "Voxtral TTS request failed (attempt %d/%d, status %s) – retrying in %.1fs",
                        attempt,
                        _MAX_RETRIES,
                        exc.status_code,
                        _RETRY_DELAY,
                    )
                    await asyncio.sleep(_RETRY_DELAY)
                else:
                    log.exception("Voxtral TTS request failed permanently")
                    return None
            except Exception:
                log.exception("Voxtral TTS request failed permanently")
                return None

        return None  # unreachable but satisfies type checker

    async def close(self) -> None:
        """Best-effort cleanup of the underlying HTTP client."""
        try:
            await self._client.close()  # type: ignore[union-attr]
        except Exception:
            pass
