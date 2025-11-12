import torch
import librosa
from transformers import WhisperProcessor, WhisperForConditionalGeneration
import noisereduce as nr
import soundfile as sf
import matplotlib.pyplot as plt
import numpy as np
import os

MODEL_PATH = r"D:\FAST\FYP\Khadim\voice\whisper_urdu_final"
AUDIO_PATH = r"D:\FAST\FYP\Khadim\voice\Recording.wav"
OUTPUT_DIR = r"D:\FAST\FYP\Khadim\voice"

print("Loading audio...")
audio, sr = librosa.load(AUDIO_PATH, sr=16000)
print(f"Sample rate: {sr}, Duration: {len(audio)/sr:.2f}s")


print("\nLoading Whisper model...")
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Using device: {device}")
if device.type == "cuda":
    print(f"GPU: {torch.cuda.get_device_name(0)}")

processor = WhisperProcessor.from_pretrained(MODEL_PATH, language="ur", task="transcribe")
model = WhisperForConditionalGeneration.from_pretrained(MODEL_PATH).to(device)

print("\nTranscribing audio...")
input_features = processor.feature_extractor(audio, sampling_rate=16000, return_tensors="pt").input_features.to(device)
predicted_ids = model.generate(input_features)
transcription = processor.batch_decode(predicted_ids, skip_special_tokens=True)[0]

print("\n==============================")
print("Transcription:")
print(transcription)
print("==============================\n")
