"""Optional local text-generation backends; heavyweight imports stay lazy."""

from lazylabel.adapters.outbound.models.text_generation import TextGenerationBackend, TransformersTextGenerationBackend

__all__ = ["TextGenerationBackend", "TransformersTextGenerationBackend"]

