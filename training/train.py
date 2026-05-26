import os
import yaml
import logging
import mlflow
import torch
from pathlib import Path
from datasets import load_dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainingArguments,
    BitsAndBytesConfig,
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from trl import SFTTrainer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def load_config(config_path: str = "training/config/qlora_config.yaml") -> dict:
    with open(config_path) as f:
        return yaml.safe_load(f)

def setup_quantization(cfg: dict) -> BitsAndBytesConfig:
    """
    BitsAndBytesConfig controls how the base model is loaded.
    
    double_quant: quantizes the quantization constants themselves
    saving ~0.4GB extra VRAM with negligible quality impact.
    compute_dtype=BF16: even though weights are 4-bit, matrix
    multiplications happen in BF16 for numerical stability.
    """
    q = cfg["quantization"]
    return BitsAndBytesConfig(
        load_in_4bit=q["load_in_4bit"],
        bnb_4bit_quant_type=q["bnb_4bit_quant_type"],
        bnb_4bit_compute_dtype=getattr(torch, q["bnb_4bit_compute_dtype"]),
        bnb_4bit_use_double_quant=q["bnb_4bit_use_double_quant"],
    )

def setup_lora(cfg: dict) -> LoraConfig:
    """
    LoraConfig defines where adapters are injected and their capacity.
    
    target_modules includes both attention (q/k/v/o) and FFN (gate/up/down).
    Including FFN is critical for domain adaptation — attention handles
    token relationships, FFN stores factual knowledge.
    """
    l = cfg["lora"]
    return LoraConfig(
        r=l["r"],
        lora_alpha=l["lora_alpha"],
        lora_dropout=l["lora_dropout"],
        bias=l["bias"],
        task_type=l["task_type"],
        target_modules=l["target_modules"],
    )

def setup_training_args(cfg: dict) -> TrainingArguments:
    t = cfg["training"]
    return TrainingArguments(
        output_dir=t["output_dir"],
        num_train_epochs=t["num_train_epochs"],
        per_device_train_batch_size=t["per_device_train_batch_size"],
        gradient_accumulation_steps=t["gradient_accumulation_steps"],
        learning_rate=t["learning_rate"],
        lr_scheduler_type=t["lr_scheduler_type"],
        warmup_ratio=t["warmup_ratio"],
        max_grad_norm=t["max_grad_norm"],
        weight_decay=t["weight_decay"],
        bf16=t["bf16"],
        tf32=t.get("tf32", False),
        logging_steps=10,
        eval_strategy="steps",
        eval_steps=100,
        save_strategy="steps",
        save_steps=100,
        save_total_limit=3,           # Keep only last 3 checkpoints
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        report_to="mlflow",           # Auto-log to MLflow
        run_name=cfg["mlflow"]["run_name"],
    )

def train(config_path: str = "training/config/qlora_config.yaml"):
    cfg = load_config(config_path)

    # MLflow experiment tracking
    mlflow.set_experiment(cfg["mlflow"]["experiment_name"])

    with mlflow.start_run(run_name=cfg["mlflow"]["run_name"]):

        # Log all hyperparameters
        mlflow.log_params({
            "model": cfg["model"]["name"],
            "lora_r": cfg["lora"]["r"],
            "lora_alpha": cfg["lora"]["lora_alpha"],
            "learning_rate": cfg["training"]["learning_rate"],
            "epochs": cfg["training"]["num_train_epochs"],
            "batch_size": cfg["training"]["per_device_train_batch_size"],
            "grad_accum": cfg["training"]["gradient_accumulation_steps"],
        })

        # 1. Load tokenizer
        logger.info(f"Loading tokenizer: {cfg['model']['name']}")
        tokenizer = AutoTokenizer.from_pretrained(
            cfg["model"]["name"],
            trust_remote_code=True,
            token=os.environ["HF_TOKEN"]
        )
        tokenizer.pad_token = tokenizer.eos_token
        tokenizer.padding_side = "right"  # Required for causal LM training

        # 2. Load quantized base model
        logger.info("Loading 4-bit quantized base model...")
        bnb_config = setup_quantization(cfg)
        model = AutoModelForCausalLM.from_pretrained(
            cfg["model"]["name"],
            quantization_config=bnb_config,
            device_map="auto",           # Distribute across available GPUs
            trust_remote_code=True,
            token=os.environ["HF_TOKEN"]
        )

        # 3. Prepare model for k-bit training
        # This casts layer norms to FP32 for training stability
        # and enables gradient checkpointing to reduce activation memory
        model = prepare_model_for_kbit_training(model)
        model.config.use_cache = False   # Disable KV cache during training

        # 4. Inject LoRA adapters
        lora_config = setup_lora(cfg)
        model = get_peft_model(model, lora_config)
        model.print_trainable_parameters()
        # Output: trainable params: 8,388,608 || all params: 7,249,096,704 || trainable%: 0.1157

        # 5. Load dataset
        logger.info("Loading training dataset...")
        t = cfg["training"]
        dataset = load_dataset(
            "json",
            data_files={
                "train": t["train_path"],
                "validation": t["val_path"]
            }
        )

        # 6. SFTTrainer — handles tokenization, packing, and training loop
        training_args = setup_training_args(cfg)
        trainer = SFTTrainer(
            model=model,
            tokenizer=tokenizer,
            args=training_args,
            train_dataset=dataset["train"],
            eval_dataset=dataset["validation"],
            dataset_text_field="text",          # Column in JSONL with formatted text
            max_seq_length=t["max_seq_length"],
            packing=t["packing"],               # Pack multiple samples per sequence
        )

        # 7. Train
        logger.info("Starting training...")
        trainer_stats = trainer.train()

        # 8. Log final metrics to MLflow
        mlflow.log_metrics({
            "train_loss":       trainer_stats.training_loss,
            "train_runtime_s":  trainer_stats.metrics["train_runtime"],
            "samples_per_sec":  trainer_stats.metrics["train_samples_per_second"],
        })

        # 9. Save LoRA adapter weights
        adapter_path = os.path.join(t["output_dir"], "lora-adapter")
        trainer.model.save_pretrained(adapter_path)
        tokenizer.save_pretrained(adapter_path)
        logger.info(f"LoRA adapter saved to {adapter_path}")

        # 10. Log adapter as MLflow artifact
        mlflow.log_artifacts(adapter_path, artifact_path="lora-adapter")
        mlflow.log_param("adapter_path", adapter_path)

        logger.info("Training complete.")

if __name__ == "__main__":
    train()