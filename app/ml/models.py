from functools import lru_cache
import os
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoModelForSequenceClassification, AutoTokenizer

BASE_DIR = Path(__file__).resolve().parent
DISTILBERT_ARTIFACT_DIR = BASE_DIR / "artifacts" / "distilbert"
MISTRAL_ARTIFACT_DIR = BASE_DIR / "artifacts" / "mistral"


def resolve_model_id(env_name: str, default_id: str, artifact_dir: Path) -> str:
    env_value = os.getenv(env_name)
    if env_value:
        return env_value
    if artifact_dir.exists():
        return str(artifact_dir)
    return default_id


DISTILBERT_MODEL_ID = resolve_model_id("DISTILBERT_MODEL_ID", "distilbert-base-uncased", DISTILBERT_ARTIFACT_DIR)
MISTRAL_MODEL_ID = resolve_model_id("MISTRAL_MODEL_ID", "mistralai/Mistral-7B-Instruct-v0.3", MISTRAL_ARTIFACT_DIR)


def gpu_available() -> bool:
    return torch.cuda.is_available()


def get_runtime_device() -> str:
    return "cuda:0" if gpu_available() else "cpu"


@lru_cache(maxsize=1)
def get_distilbert_bundle() -> dict:
    tokenizer = AutoTokenizer.from_pretrained(DISTILBERT_MODEL_ID)
    model = AutoModelForSequenceClassification.from_pretrained(DISTILBERT_MODEL_ID)
    if gpu_available():
        model = model.to("cuda:0")
    model.eval()
    return {
        "tokenizer": tokenizer,
        "model": model,
        "model_id": DISTILBERT_MODEL_ID,
        "device": get_runtime_device(),
    }


@lru_cache(maxsize=1)
def get_mistral_bundle() -> dict:
    tokenizer = AutoTokenizer.from_pretrained(MISTRAL_MODEL_ID)
    use_4bit = os.getenv("MISTRAL_USE_4BIT", "false").lower() in {"1", "true", "yes"}

    if gpu_available():
        model_kwargs = {
            "torch_dtype": torch.float16,
            "device_map": "auto",
            "low_cpu_mem_usage": True,
            "max_memory": {0: "7GiB", "cpu": "16GiB"},
            "offload_folder": str(BASE_DIR / "offload"),
        }
        if use_4bit:
            model_kwargs["load_in_4bit"] = True
        model = AutoModelForCausalLM.from_pretrained(MISTRAL_MODEL_ID, **model_kwargs)
    else:
        model = AutoModelForCausalLM.from_pretrained(
            MISTRAL_MODEL_ID,
            torch_dtype=torch.float32,
            device_map="cpu",
            low_cpu_mem_usage=True,
        )

    model.eval()

    return {
        "tokenizer": tokenizer,
        "model": model,
        "model_id": MISTRAL_MODEL_ID,
        "device": get_runtime_device(),
        "use_4bit": use_4bit,
    }
