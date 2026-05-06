from functools import lru_cache
import re
import logging

import torch
from transformers import pipeline

from app.core.config import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_summarizer():
    device = 0 if torch.cuda.is_available() else -1
    try:
        return pipeline(
            task="text-generation",
            model=settings.summarizer_model,
            max_new_tokens=110,
            do_sample=False,
            device=device,
        )
    except Exception:
        logger.exception("Failed to load summarizer model")
        return None


def _extractive_bullets(text: str) -> str:
    chunks = [c.strip() for c in re.split(r"[.!?]\s+", text) if c.strip()]
    bullets = chunks[:3] if chunks else [text[:200].strip()]
    return "\n".join(f"- {item[:180]}" for item in bullets)


def summarize_as_bullets(text: str) -> str:
    if not settings.use_llm_summarizer:
        return _extractive_bullets(text)

    prompt = (
        "Summarize the disruption news into 3 short bullet points with operational impact. "
        "Focus on location, delay duration, and supply chain impact.\n\n"
        f"Article:\n{text[:2200]}\n\n"
        "Answer format:\n"
        "- ...\n- ...\n- ..."
    )

    model = get_summarizer()
    if model is None:
        return _extractive_bullets(text)

    try:
        outputs = model(prompt, max_new_tokens=110, do_sample=False)
        if isinstance(outputs, list) and outputs:
            gen = outputs[0].get("generated_text", "")
        elif isinstance(outputs, dict):
            gen = outputs.get("generated_text", "")
        else:
            gen = str(outputs)

        if gen.startswith(prompt):
            gen = gen[len(prompt):].strip()

        lines = [l.strip() for l in gen.splitlines() if l.strip()]
        bullets = []
        for line in lines:
            if line.startswith("-"):
                bullets.append(line)
            else:
                sentences = re.split(r'(?<=[.!?])\s+', line)
                for s in sentences:
                    if s.strip():
                        bullets.append(f"- {s.strip()}")

        if not bullets:
            return _extractive_bullets(text)
        return "\n".join(bullets[:3])
    except Exception:
        logger.exception("LLM summarization failed, falling back to extractive bullets")
        return _extractive_bullets(text)
