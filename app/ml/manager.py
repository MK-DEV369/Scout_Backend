from datetime import datetime
import logging

from app.core.config import settings
from app.ml.models import get_distilbert_bundle, get_mistral_bundle
from app.nlp.event_classifier import get_classifier, get_classifier_info

logger = logging.getLogger(__name__)

_state = {
    "distilbert": None,
    "mistral": None,
    "classifier_loaded": False,
    "classifier_model": None,
    "classifier_last_loaded": None,
}


def load_models() -> dict:
    """Load ML models into memory and record timestamps."""
    try:
        _state["distilbert"] = get_distilbert_bundle()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to load distilbert: %s", exc)

    if getattr(settings, "load_mistral_on_startup", False):
        try:
            _state["mistral"] = get_mistral_bundle()
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to load mistral: %s", exc)
    else:
        _state["mistral"] = None

    try:
        # force classifier pipeline creation
        clf = get_classifier()
        info = get_classifier_info()
        _state["classifier_loaded"] = True
        _state["classifier_model"] = info.get("model_id")
        _state["classifier_last_loaded"] = datetime.utcnow()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to load classifier: %s", exc)
        _state["classifier_loaded"] = False

    return dict(_state)


def get_status() -> dict:
    return {
        "classifier_loaded": _state.get("classifier_loaded", False),
        "classifier_model": _state.get("classifier_model"),
        "classifier_last_loaded": _state.get("classifier_last_loaded"),
    }
