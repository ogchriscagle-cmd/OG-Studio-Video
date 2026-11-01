"""Draft visible appearance details locally; the image never leaves this process."""
import os
from pathlib import Path
import threading
from runtime_paths import DATA_ROOT

MODEL_ID = "Salesforce/blip-vqa-base"
MODEL_REVISION = "787b3d35d57e49572baabd22884b3d5a05acf072"
CACHE = DATA_ROOT / ".models"
MODEL_FILES = ("config.json", "model.safetensors", "preprocessor_config.json",
               "special_tokens_map.json", "tokenizer.json", "tokenizer_config.json", "vocab.txt")
_lock = threading.Lock()
_processor = None
_model = None


def _load():
    global _processor, _model
    if _model is None:
        os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
        os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")
        from huggingface_hub import snapshot_download
        from transformers import BlipProcessor, BlipForQuestionAnswering
        cached = CACHE / "models--Salesforce--blip-vqa-base" / "snapshots" / MODEL_REVISION
        folder = cached if all((cached / name).is_file() for name in MODEL_FILES) else CACHE / "appearance"
        if not all((folder / name).is_file() for name in MODEL_FILES):
            snapshot_download(MODEL_ID, revision=MODEL_REVISION, local_dir=str(folder),
                              token=False, allow_patterns=list(MODEL_FILES))
        processor = BlipProcessor.from_pretrained(str(folder), local_files_only=True, use_fast=False)
        model = BlipForQuestionAnswering.from_pretrained(
            str(folder), local_files_only=True, use_safetensors=True, trust_remote_code=False
        ).eval()
        _processor, _model = processor, model
    return _processor, _model


def describe_appearance(path):
    import torch
    from PIL import Image, ImageOps
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        image.thumbnail((1024, 1024))
    with _lock:
        processor, model = _load()
        def ask(question):
            inputs = processor(image, question, return_tensors="pt")
            with torch.inference_mode():
                output = model.generate(**inputs, max_new_tokens=24, do_sample=False)
            return processor.decode(output[0], skip_special_tokens=True).strip().rstrip(".")
        visible = ask("Is there a person in this picture?")
        if visible.lower() not in ("yes", "1", "one"):
            raise ValueError("No clear person was detected. Choose a clear portrait or describe the character manually.")
        details = []
        for question, label in (
            ("What is the person wearing?", "Clothing"),
            ("What color are the person's clothes?", "Clothing colors"),
            ("What color is the person's hair?", "Hair color"),
            ("What hairstyle does the person have?", "Hair style"),
        ):
            answer = ask(question)
            if answer.lower() not in ("", "unknown", "none", "nothing", "not visible", "unanswerable"):
                details.append(f"{label}: {answer}.")
        if ask("Is the person wearing glasses?").lower() == "yes":
            details.append(f"Accessories: {ask('What kind of glasses is the person wearing?')}.")
        if ask("Is the person wearing a hat?").lower() == "yes":
            details.append(f"Headwear: {ask('What kind of hat is the person wearing?')}.")
        if not details:
            raise ValueError("The photo did not provide clear appearance details. Please enter a description manually.")
        return " ".join(details)
