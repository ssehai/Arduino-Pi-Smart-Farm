from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class DiseasePrediction:
    label: str
    confidence: float
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DiseaseModel:
    model_name = "disease_dummy_interface_v1"

    def predict(self, image_bytes: bytes) -> DiseasePrediction:
        if not image_bytes:
            return DiseasePrediction("invalid_image", 0.0, "No image bytes received.")

        # Placeholder: replace this method with MobileNetV2/EfficientNet/ONNX inference.
        confidence = 0.52 if len(image_bytes) > 20000 else 0.38
        label = "healthy_or_unknown" if confidence < 0.5 else "disease_suspected_review_required"
        return DiseasePrediction(
            label=label,
            confidence=confidence,
            message="Dummy model result. Use as a review hint only, never for automatic treatment.",
        )
