"""
Merge LoRA adapters back into base model weights for serving.

Why merge?
  During training: base model (4-bit frozen) + adapter weights (BF16)
  During serving:  merged model — no adapter overhead, faster inference

Merge operation:
  W_merged = W_base + (A × B) × (lora_alpha / r)
  
After merge, load as standard model — vLLM doesn't need PEFT library.
"""
import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer
import mlflow
import os

def merge_and_push(
    base_model_name: str,
    adapter_path: str,
    output_path: str,
    hf_token: str
):
    print("Loading base model in BF16 for merge (not 4-bit)...")
    # Load in BF16 for merge — 4-bit cannot be merged directly
    base_model = AutoModelForCausalLM.from_pretrained(
        base_model_name,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        token=hf_token
    )

    tokenizer = AutoTokenizer.from_pretrained(adapter_path)

    print("Loading LoRA adapter...")
    model = PeftModel.from_pretrained(base_model, adapter_path)

    print("Merging adapter into base model weights...")
    # merge_and_unload() performs W_merged = W + A×B and removes adapter layers
    merged_model = model.merge_and_unload()

    print(f"Saving merged model to {output_path}...")
    merged_model.save_pretrained(output_path, safe_serialization=True)
    tokenizer.save_pretrained(output_path)

    # Log merged model to MLflow registry
    mlflow.transformers.log_model(
        transformers_model={"model": merged_model, "tokenizer": tokenizer},
        artifact_path="merged-model",
        registered_model_name="mistral-7b-docqa",
        # Starts in "None" stage — eval gate promotes to "Staging"
    )
    print("Merged model registered in MLflow.")

if __name__ == "__main__":
    merge_and_push(
        base_model_name="mistralai/Mistral-7B-Instruct-v0.3",
        adapter_path="./outputs/lora-adapter",
        output_path="./outputs/merged-model",
        hf_token=os.environ["HF_TOKEN"]
    )