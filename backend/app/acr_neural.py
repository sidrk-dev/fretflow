from __future__ import annotations

import os
import threading
import urllib.request
from pathlib import Path
from typing import Optional

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from .acr_fast import frames_to_smoothed_events
from .audio import AudioFeatures
from .guitar_theory import compute_capo_options, estimate_key_label
from .schemas import ChordsPayload

# Bound intra-op CPU threads so concurrent requests don't thrash cores
torch.set_num_threads(max(1, (os.cpu_count() or 4) // 2))

CHECKPOINT_PATH = Path(__file__).resolve().parent.parent / "models" / "btc_model_best.pth"
CHECKPOINT_URL = (
    "https://raw.githubusercontent.com/ptnghia-j/ChordMini/main/checkpoints/btc_model_best.pth"
)


def _gen_bias_mask(max_length: int) -> torch.Tensor:
    np_mask = np.triu(np.full([max_length, max_length], -np.inf), 1)
    return torch.from_numpy(np_mask).float().unsqueeze(0).unsqueeze(1)


def _gen_timing_signal(
    max_length: int, channels: int, min_timescale: float = 1.0, max_timescale: float = 1.0e4
) -> torch.Tensor:
    position = np.arange(max_length)
    num_timescales = channels // 2
    log_inc = np.log(float(max_timescale) / float(min_timescale)) / max(float(num_timescales) - 1, 1)
    inv = min_timescale * np.exp(np.arange(num_timescales).astype(np.float64) * -log_inc)
    scaled = np.expand_dims(position, 1) * np.expand_dims(inv, 0)
    signal = np.concatenate([np.sin(scaled), np.cos(scaled)], axis=1)
    signal = np.pad(signal, [[0, 0], [0, channels % 2]], "constant")
    return torch.from_numpy(signal.reshape([1, max_length, channels])).float()


class LayerNorm(nn.Module):
    def __init__(self, features: int, eps: float = 1e-6):
        super().__init__()
        self.gamma = nn.Parameter(torch.ones(features))
        self.beta = nn.Parameter(torch.zeros(features))
        self.eps = eps

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        mean = x.mean(-1, keepdim=True)
        std = x.std(-1, keepdim=True)
        return self.gamma * (x - mean) / (std + self.eps) + self.beta


class SoftmaxOutputLayer(nn.Module):
    def __init__(self, hidden_size: int, output_size: int):
        super().__init__()
        self.output_size = output_size
        self.output_projection = nn.Linear(hidden_size, output_size)
        self.lstm = nn.LSTM(
            input_size=hidden_size,
            hidden_size=hidden_size // 2,
            batch_first=True,
            bidirectional=True,
        )

    def forward(self, hidden: torch.Tensor) -> torch.Tensor:
        return self.output_projection(hidden)


class MultiHeadAttention(nn.Module):
    def __init__(
        self,
        input_depth: int,
        total_key_depth: int,
        total_value_depth: int,
        output_depth: int,
        num_heads: int,
        bias_mask: Optional[torch.Tensor] = None,
        dropout: float = 0.0,
        attention_map: bool = False,
    ):
        super().__init__()
        self.attention_map = attention_map
        self.num_heads = num_heads
        self.query_scale = (total_key_depth // num_heads) ** -0.5
        self.bias_mask = bias_mask
        self.query_linear = nn.Linear(input_depth, total_key_depth, bias=False)
        self.key_linear = nn.Linear(input_depth, total_key_depth, bias=False)
        self.value_linear = nn.Linear(input_depth, total_value_depth, bias=False)
        self.output_linear = nn.Linear(total_value_depth, output_depth, bias=False)
        self.dropout = nn.Dropout(dropout)

    def _split_heads(self, x: torch.Tensor) -> torch.Tensor:
        b, l, d = x.shape
        return x.view(b, l, self.num_heads, d // self.num_heads).permute(0, 2, 1, 3)

    def _merge_heads(self, x: torch.Tensor) -> torch.Tensor:
        b, h, l, d = x.shape
        return x.permute(0, 2, 1, 3).contiguous().view(b, l, h * d)

    def forward(self, queries: torch.Tensor, keys: torch.Tensor, values: torch.Tensor):
        queries = self._split_heads(self.query_linear(queries)) * self.query_scale
        keys = self._split_heads(self.key_linear(keys))
        values = self._split_heads(self.value_linear(values))
        logits = torch.matmul(queries, keys.permute(0, 1, 3, 2))
        if self.bias_mask is not None:
            logits = logits + self.bias_mask[:, :, : logits.shape[-2], : logits.shape[-1]].type_as(logits)
        weights = self.dropout(F.softmax(logits, dim=-1))
        contexts = self._merge_heads(torch.matmul(weights, values))
        outputs = self.output_linear(contexts)
        return (outputs, weights) if self.attention_map else outputs


class Conv(nn.Module):
    def __init__(self, input_size: int, output_size: int, kernel_size: int, pad_type: str):
        super().__init__()
        padding = (
            (kernel_size - 1, 0)
            if pad_type == "left"
            else (kernel_size // 2, (kernel_size - 1) // 2)
        )
        self.pad = nn.ConstantPad1d(padding, 0)
        self.conv = nn.Conv1d(input_size, output_size, kernel_size=kernel_size, padding=0)

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        return self.conv(self.pad(inputs.permute(0, 2, 1))).permute(0, 2, 1)


class PositionwiseFeedForward(nn.Module):
    def __init__(
        self,
        input_depth: int,
        filter_size: int,
        output_depth: int,
        layer_config: str = "ll",
        padding: str = "left",
        dropout: float = 0.0,
    ):
        super().__init__()
        sizes = (
            [(input_depth, filter_size)]
            + [(filter_size, filter_size)] * (len(layer_config) - 2)
            + [(filter_size, output_depth)]
        )
        self.layers = nn.ModuleList(
            [
                nn.Linear(*s) if lc == "l" else Conv(*s, kernel_size=3, pad_type=padding)
                for lc, s in zip(list(layer_config), sizes)
            ]
        )
        self.relu = nn.ReLU()
        self.dropout = nn.Dropout(dropout)

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        x = inputs
        for i, layer in enumerate(self.layers):
            x = layer(x)
            if i < len(self.layers):
                x = self.dropout(self.relu(x))
        return x


class _SelfAttentionBlock(nn.Module):
    def __init__(
        self,
        hidden_size: int,
        total_key_depth: int,
        total_value_depth: int,
        filter_size: int,
        num_heads: int,
        bias_mask: Optional[torch.Tensor] = None,
        layer_dropout: float = 0.0,
        attention_dropout: float = 0.0,
        relu_dropout: float = 0.0,
        attention_map: bool = False,
    ):
        super().__init__()
        self.attention_map = attention_map
        self.multi_head_attention = MultiHeadAttention(
            hidden_size,
            total_key_depth,
            total_value_depth,
            hidden_size,
            num_heads,
            bias_mask,
            attention_dropout,
            attention_map,
        )
        self.positionwise_convolution = PositionwiseFeedForward(
            hidden_size,
            filter_size,
            hidden_size,
            layer_config="cc",
            padding="both",
            dropout=relu_dropout,
        )
        self.dropout = nn.Dropout(layer_dropout)
        self.layer_norm_mha = LayerNorm(hidden_size)
        self.layer_norm_ffn = LayerNorm(hidden_size)

    def forward(self, inputs: torch.Tensor):
        x = inputs
        x_norm = self.layer_norm_mha(x)
        if self.attention_map:
            y, weights = self.multi_head_attention(x_norm, x_norm, x_norm)
        else:
            y = self.multi_head_attention(x_norm, x_norm, x_norm)
            weights = None
        x = self.dropout(x + y)
        y = self.positionwise_convolution(self.layer_norm_ffn(x))
        y = self.dropout(x + y)
        return (y, weights) if self.attention_map else y


class _BiDirSelfAttention(nn.Module):
    def __init__(
        self,
        hidden_size: int,
        total_key_depth: int,
        total_value_depth: int,
        filter_size: int,
        num_heads: int,
        max_length: int,
        layer_dropout: float = 0.0,
        attention_dropout: float = 0.0,
        relu_dropout: float = 0.0,
    ):
        super().__init__()
        self.attn_block = _SelfAttentionBlock(
            hidden_size,
            total_key_depth,
            total_value_depth,
            filter_size,
            num_heads,
            _gen_bias_mask(max_length),
            layer_dropout,
            attention_dropout,
            relu_dropout,
            True,
        )
        self.backward_attn_block = _SelfAttentionBlock(
            hidden_size,
            total_key_depth,
            total_value_depth,
            filter_size,
            num_heads,
            torch.transpose(_gen_bias_mask(max_length), dim0=2, dim1=3),
            layer_dropout,
            attention_dropout,
            relu_dropout,
            True,
        )
        self.linear = nn.Linear(hidden_size * 2, hidden_size)

    def forward(self, inputs):
        x, attn_list = inputs
        fwd_out, fwd_w = self.attn_block(x)
        bwd_out, bwd_w = self.backward_attn_block(x)
        y = self.linear(torch.cat((fwd_out, bwd_out), dim=2))
        return y, [*attn_list, fwd_w, bwd_w]


class _BiDirSelfAttentionLayers(nn.Module):
    def __init__(
        self,
        embedding_size: int = 144,
        hidden_size: int = 128,
        num_layers: int = 8,
        num_heads: int = 4,
        total_key_depth: int = 128,
        total_value_depth: int = 128,
        filter_size: int = 128,
        max_length: int = 108,
    ):
        super().__init__()
        self.timing_signal = _gen_timing_signal(max_length, hidden_size)
        self.embedding_proj = nn.Linear(embedding_size, hidden_size, bias=False)
        self.self_attn_layers = nn.Sequential(
            *[
                _BiDirSelfAttention(
                    hidden_size,
                    total_key_depth,
                    total_value_depth,
                    filter_size,
                    num_heads,
                    max_length,
                )
                for _ in range(num_layers)
            ]
        )
        self.layer_norm = LayerNorm(hidden_size)
        self.input_dropout = nn.Dropout(0.0)

    def forward(self, inputs: torch.Tensor):
        x = self.embedding_proj(self.input_dropout(inputs))
        x = x + self.timing_signal[:, : x.shape[1], :].type_as(x)
        y, w = self.self_attn_layers((x, []))
        return self.layer_norm(y), w


class BTCModel(nn.Module):
    """Bi-directional Transformer for 170-Chord Recognition (adapted from MIT ChordMini)."""

    def __init__(self, seq_len: int = 108, num_chords: int = 170):
        super().__init__()
        self.timestep = seq_len
        self.self_attn_layers = _BiDirSelfAttentionLayers(max_length=seq_len)
        self.output_layer = SoftmaxOutputLayer(hidden_size=128, output_size=num_chords)
        self.n_classes = num_chords

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        attn_out, _ = self.self_attn_layers(x)
        return self.output_layer(attn_out)


class _NeuralChordBundle:
    def __init__(self, model: BTCModel, idx_to_chord: dict[int, str], mean: float, std: float):
        self.model = model
        self.idx_to_chord = idx_to_chord
        self.mean = mean
        self.std = std


_bundle: Optional[_NeuralChordBundle] = None
_bundle_lock = threading.Lock()


def _ensure_checkpoint_file() -> Path:
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if CHECKPOINT_PATH.is_file() and CHECKPOINT_PATH.stat().st_size > 1_000_000:
        return CHECKPOINT_PATH
    tmp_path = CHECKPOINT_PATH.with_suffix(".pth.tmp")
    urllib.request.urlretrieve(CHECKPOINT_URL, str(tmp_path))
    tmp_path.replace(CHECKPOINT_PATH)
    return CHECKPOINT_PATH


def _load_bundle() -> _NeuralChordBundle:
    global _bundle
    if _bundle is not None:
        return _bundle
    with _bundle_lock:
        if _bundle is not None:
            return _bundle
        ckpt_file = _ensure_checkpoint_file()
        ckpt = torch.load(str(ckpt_file), map_location="cpu", weights_only=False)
        state_dict = ckpt.get("model_state_dict", ckpt.get("model", ckpt))
        if state_dict and next(iter(state_dict)).startswith("module."):
            state_dict = {k.replace("module.", ""): v for k, v in state_dict.items()}

        idx_raw = ckpt.get("idx_to_chord") or {}
        idx_to_chord = {int(k): str(v) for k, v in idx_raw.items()}
        num_chords = max(len(idx_to_chord), 170)

        norm = ckpt.get("normalization") or {}
        mean = float(norm.get("mean", -2.3698))
        std = float(norm.get("std", 1.9627))

        model = BTCModel(seq_len=108, num_chords=num_chords)
        model.load_state_dict(state_dict, strict=True)
        model.eval()
        _bundle = _NeuralChordBundle(model=model, idx_to_chord=idx_to_chord, mean=mean, std=std)
        return _bundle


def _gaussian_smooth_logits(logits: torch.Tensor, kernel_size: int = 9) -> torch.Tensor:
    padding = kernel_size // 2
    sigma = kernel_size / 6.0
    x = torch.arange(kernel_size, dtype=logits.dtype, device=logits.device) - padding
    kernel = torch.exp(-0.5 * (x / sigma) ** 2)
    kernel = (kernel / kernel.sum()).view(1, 1, -1)
    n_classes = logits.shape[-1]
    kernel = kernel.expand(n_classes, 1, -1)
    logits_t = logits.transpose(1, 2)
    smoothed = F.conv1d(F.pad(logits_t, (padding, padding), mode="replicate"), kernel, groups=n_classes)
    return smoothed.transpose(1, 2)


def _majority_filter(indices: np.ndarray, kernel_size: int = 7) -> np.ndarray:
    if indices.size < kernel_size:
        return indices
    pad = kernel_size // 2
    padded = np.pad(indices, (pad, pad), mode="edge")
    out = np.empty_like(indices)
    for i in range(indices.size):
        win = padded[i : i + kernel_size]
        vals, counts = np.unique(win, return_counts=True)
        cands = vals[counts == counts.max()]
        out[i] = indices[i] if indices[i] in cands else int(cands[0])
    return out


def run_neural_chord_recognition(
    features: AudioFeatures, bpm: float, beats_ms: list[int]
) -> ChordsPayload:
    bundle = _load_bundle()
    feat = features.log_cqt_frames
    orig_len = int(feat.shape[0])
    if orig_len == 0:
        capo_opts, rec_capo = compute_capo_options([])
        return ChordsPayload(
            engine="neural_btc_170",
            bpm=bpm,
            beatsMs=beats_ms,
            detectedKey="C Major",
            events=[],
            capoOptions=capo_opts,
            recommendedCapo=rec_capo,
            uniqueChords=[],
        )

    seq_len = 108
    stride = 54

    rem = orig_len % seq_len
    padded = np.pad(feat, ((0, 0 if rem == 0 else seq_len - rem), (0, 0)), mode="constant")
    padded_len = int(padded.shape[0])

    starts = list(range(0, max(1, padded_len - seq_len + 1), stride))
    if starts[-1] + seq_len < padded_len:
        starts.append(padded_len - seq_len)

    prob_acc = np.zeros((orig_len, bundle.model.n_classes), dtype=np.float32)
    counts = np.zeros(orig_len, dtype=np.float32)

    windows = np.stack([padded[s : s + seq_len] for s in starts], axis=0)
    norm_windows = (windows - bundle.mean) / (bundle.std + 1e-8)

    batch_size = 32
    with torch.no_grad():
        for b_start in range(0, len(starts), batch_size):
            batch_np = norm_windows[b_start : b_start + batch_size]
            tensor = torch.from_numpy(batch_np).float()
            logits = bundle.model(tensor)
            logits = _gaussian_smooth_logits(logits, kernel_size=9)
            probs = torch.softmax(logits, dim=-1).cpu().numpy()

            for local_i, s_frame in enumerate(starts[b_start : b_start + batch_size]):
                valid = min(seq_len, max(0, orig_len - s_frame))
                if valid > 0:
                    prob_acc[s_frame : s_frame + valid] += probs[local_i, :valid]
                    counts[s_frame : s_frame + valid] += 1.0

    avg_probs = prob_acc / np.maximum(counts[:, None], 1.0)
    pred_idx = np.argmax(avg_probs, axis=1)
    pred_idx = _majority_filter(pred_idx, kernel_size=7)
    confs = avg_probs[np.arange(orig_len), pred_idx]

    frame_labels = [bundle.idx_to_chord.get(int(idx), "N") for idx in pred_idx]
    events = frames_to_smoothed_events(
        frame_labels=frame_labels,
        frame_confidences=confs,
        frame_duration=features.frame_duration,
        beats_ms=beats_ms,
        min_segment_sec=0.45,
    )
    capo_options, recommended_capo = compute_capo_options(events)
    detected_key = estimate_key_label(events)
    unique_chords = list(dict.fromkeys(ev.display for ev in events))

    return ChordsPayload(
        engine="neural_btc_170",
        bpm=bpm,
        beatsMs=beats_ms,
        detectedKey=detected_key,
        events=events,
        capoOptions=capo_options,
        recommendedCapo=recommended_capo,
        uniqueChords=unique_chords,
    )
