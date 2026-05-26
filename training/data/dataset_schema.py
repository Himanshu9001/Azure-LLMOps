"""
Pydantic schemas for training and evaluation datasets.

Enforces data quality at ingestion time — bad samples
are caught before they corrupt training.
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional
import re


class TrainingSample(BaseModel):
    """
    Single training sample in Mistral instruct format.
    
    text field contains the fully formatted prompt+response:
    <s>[INST] {context}\n\nQuestion: {question} [/INST] {answer}</s>
    """
    text: str = Field(..., min_length=50)

    @field_validator("text")
    @classmethod
    def must_have_inst_tags(cls, v: str) -> str:
        """Ensure sample is properly formatted for Mistral instruct."""
        if "[INST]" not in v or "[/INST]" not in v:
            raise ValueError("Training sample must contain [INST] and [/INST] tags")
        if not v.startswith("<s>"):
            raise ValueError("Training sample must start with <s> token")
        if not v.endswith("</s>"):
            raise ValueError("Training sample must end with </s> token")
        return v

    @field_validator("text")
    @classmethod
    def minimum_response_length(cls, v: str) -> str:
        """Response (after [/INST]) must be at least 20 chars."""
        parts = v.split("[/INST]")
        if len(parts) < 2:
            raise ValueError("Missing [/INST] separator")
        response = parts[1].replace("</s>", "").strip()
        if len(response) < 20:
            raise ValueError(f"Response too short: {len(response)} chars")
        return v


class EvalSample(BaseModel):
    """
    Single evaluation sample for RAGAS scoring.
    Must have ground truth for recall measurement.
    """
    question:     str            = Field(..., min_length=10)
    contexts:     list[str]      = Field(..., min_items=1)
    ground_truth: str            = Field(..., min_length=10)
    answer:       Optional[str]  = None   # Filled by model at eval time

    @field_validator("contexts")
    @classmethod
    def contexts_not_empty(cls, v: list[str]) -> list[str]:
        for ctx in v:
            if len(ctx.strip()) < 20:
                raise ValueError("Context chunk too short — likely garbage")
        return v

    @field_validator("question")
    @classmethod
    def question_ends_with_mark(cls, v: str) -> str:
        """Questions should end with ? for clarity."""
        if not v.strip().endswith("?"):
            v = v.strip() + "?"
        return v


class DatasetStats(BaseModel):
    """Summary statistics logged to MLflow after dataset preparation."""
    total_samples:     int
    train_samples:     int
    val_samples:       int
    avg_text_length:   float
    min_text_length:   int
    max_text_length:   int
    source_documents:  int
    failed_chunks:     int
    generation_model:  str = "gpt-4o"

    def log_to_mlflow(self, mlflow_client) -> None:
        import mlflow
        mlflow.log_params({
            "dataset_total_samples":    self.total_samples,
            "dataset_train_samples":    self.train_samples,
            "dataset_val_samples":      self.val_samples,
            "dataset_avg_text_length":  self.avg_text_length,
            "dataset_source_documents": self.source_documents,
            "dataset_generation_model": self.generation_model,
        })