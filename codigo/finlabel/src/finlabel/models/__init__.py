"""Optional local text-generation backends; heavyweight imports stay lazy."""

from finlabel.adapters.outbound.models.text_generation import TextGenerationBackend, TransformersTextGenerationBackend

__all__ = ["TextGenerationBackend", "TransformersTextGenerationBackend"]

