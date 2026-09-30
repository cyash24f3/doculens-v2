"""Pinned MiniLM ONNX inference without importing Torch or Transformers.

The quantized artifact has a distinct pipeline fingerprint. No silent input truncation
is enabled here; Models enforces the encoder and cross-encoder limits before inference.
"""

from typing import Any

import numpy as np
from huggingface_hub import hf_hub_download
from tokenizers import Tokenizer


class OffsetTokenizer:
    is_fast = True

    def __init__(self, path: str):
        self.raw = Tokenizer.from_file(path)
        self.raw.no_truncation()
        self.raw.no_padding()

    def __call__(self, text: str, pair: str | None = None, **kwargs) -> dict:
        encoded = self.raw.encode(
            text, pair, add_special_tokens=kwargs.get("add_special_tokens", True)
        )
        return {"input_ids": encoded.ids, "offset_mapping": encoded.offsets}


def mean_pool(hidden: np.ndarray, mask: np.ndarray) -> np.ndarray:
    weights = mask[..., None].astype(np.float32)
    pooled = (hidden * weights).sum(axis=1) / np.maximum(weights.sum(axis=1), 1e-9)
    return pooled / np.maximum(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-9)


class OnnxModel:
    def __init__(self, model: str, revision: str, filename: str, threads: int):
        import onnxruntime as ort

        tokenizer_path = hf_hub_download(model, "tokenizer.json", revision=revision)
        model_path = hf_hub_download(model, filename, revision=revision)
        self.tokenizer = OffsetTokenizer(tokenizer_path)
        self.batch_tokenizer = Tokenizer.from_file(tokenizer_path)
        self.batch_tokenizer.no_truncation()
        self.batch_tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        options.enable_cpu_mem_arena = False
        options.enable_mem_pattern = False
        self.session = ort.InferenceSession(
            model_path, sess_options=options, providers=["CPUExecutionProvider"]
        )
        self.inputs = {value.name for value in self.session.get_inputs()}

    def run(self, texts: list[Any]) -> tuple[np.ndarray, np.ndarray]:
        batch = self.batch_tokenizer.encode_batch(texts)
        values = {
            "input_ids": np.array([item.ids for item in batch], dtype=np.int64),
            "attention_mask": np.array([item.attention_mask for item in batch], dtype=np.int64),
            "token_type_ids": np.array([item.type_ids for item in batch], dtype=np.int64),
        }
        output = self.session.run(None, {k: v for k, v in values.items() if k in self.inputs})[0]
        return output, values["attention_mask"]


class OnnxEncoder(OnnxModel):
    max_seq_length = 256

    def get_embedding_dimension(self):
        return self.session.get_outputs()[0].shape[-1]

    def encode(self, texts: list[str], **kwargs) -> np.ndarray:
        if not texts:
            return np.empty((0, 384), dtype=np.float32)
        matrices = []
        for start in range(0, len(texts), 4):
            hidden, mask = self.run(texts[start : start + 4])
            matrices.append(mean_pool(hidden, mask))
        return np.concatenate(matrices).astype(np.float32)


class OnnxReranker(OnnxModel):
    max_length = 512

    def predict(self, pairs: list[tuple[str, str]], **kwargs) -> np.ndarray:
        scores = []
        for start in range(0, len(pairs), 4):
            logits, _ = self.run(pairs[start : start + 4])
            # This model's single-label classifier uses sigmoid in CrossEncoder.
            scores.extend(1 / (1 + np.exp(-np.clip(logits.reshape(-1), -80, 80))))
        return np.asarray(scores, dtype=np.float32)
