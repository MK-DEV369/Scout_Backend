import json
from pathlib import Path

from datasets import Dataset
from transformers import AutoModelForSequenceClassification, AutoTokenizer, Trainer, TrainingArguments

LABELS = ["Geopolitical", "Logistics", "Environmental", "Economic"]
LABEL_TO_ID = {label: idx for idx, label in enumerate(LABELS)}


def load_jsonl(path: Path) -> Dataset:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        rows.append({"text": row["text"], "label": LABEL_TO_ID[row["label"]]})
    return Dataset.from_list(rows)


def train(data_path: str, output_dir: str) -> None:
    tokenizer = AutoTokenizer.from_pretrained("distilbert-base-uncased")
    model = AutoModelForSequenceClassification.from_pretrained(
        "distilbert-base-uncased",
        num_labels=len(LABELS),
        id2label={i: label for i, label in enumerate(LABELS)},
        label2id=LABEL_TO_ID,
    )

    dataset = load_jsonl(Path(data_path))
    split = dataset.train_test_split(test_size=0.15, seed=42)

    def tokenize(batch):
        return tokenizer(batch["text"], truncation=True, padding="max_length", max_length=256)

    train_ds = split["train"].map(tokenize, batched=True)
    eval_ds = split["test"].map(tokenize, batched=True)

    args = TrainingArguments(
        output_dir=output_dir,
        learning_rate=2e-5,
        per_device_train_batch_size=16,
        per_device_eval_batch_size=16,
        num_train_epochs=3,
        weight_decay=0.01,
        evaluation_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        fp16=True,
    )

    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=train_ds,
        eval_dataset=eval_ds,
    )
    trainer.train()
    trainer.save_model(output_dir)
    tokenizer.save_pretrained(output_dir)


if __name__ == "__main__":
    train(data_path="data/event_train.jsonl", output_dir="artifacts/event_classifier")
