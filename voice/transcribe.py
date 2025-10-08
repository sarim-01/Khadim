# import os
# import random
# import pandas as pd
# import torch
# import soundfile as sf
# import librosa
# from tqdm import tqdm
# from transformers import WhisperForConditionalGeneration, WhisperProcessor
# import evaluate

# # ====== PATHS ======
# MODEL_PATH = r"C:\Users\zaina\OneDrive\Desktop\Khadim-Whisper\whisper_urdu_final"
# TSV_FILE = r"C:\Users\zaina\OneDrive\Desktop\Khadim-Whisper\urdu_dataset\final_main_dataset.tsv"
# AUDIO_DIR = r"C:\Users\zaina\OneDrive\Desktop\Khadim-Whisper\urdu_dataset\limited_wav_files"

# # ====== LOAD MODEL + PROCESSOR ======
# device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
# print(f"Using device: {device}")

# model = WhisperForConditionalGeneration.from_pretrained(MODEL_PATH).to(device)
# processor = WhisperProcessor.from_pretrained(MODEL_PATH)

# # ====== LOAD TSV METADATA ======
# df = pd.read_csv(TSV_FILE, sep="\t")

# if "path" not in df.columns or "sentence" not in df.columns:
#     raise ValueError("TSV file must contain 'path' and 'sentence' columns!")

# # Build absolute .wav paths (replace .mp3 → .wav)
# df["full_path"] = df["path"].apply(
#     lambda x: os.path.join(AUDIO_DIR, os.path.basename(x).replace(".mp3", ".wav"))
# )

# # Keep only existing files
# df = df[df["full_path"].apply(os.path.exists)]
# print(f"Found {len(df)} valid audio-transcript pairs.")

# # ====== RANDOMLY SAMPLE 20 FILES ======
# sample_df = df.sample(n=min(20, len(df)), random_state=42).reset_index(drop=True)

# # ====== METRIC ======
# wer_metric = evaluate.load("wer")

# pred_texts, ref_texts = [], []

# # ====== INFERENCE LOOP ======
# for i, row in tqdm(sample_df.iterrows(), total=len(sample_df), desc="Evaluating"):
#     audio_path = row["full_path"]
#     reference = str(row["sentence"]).strip()

#     try:
#         # Load and resample to 16kHz if needed
#         audio, sr = sf.read(audio_path)
#         if sr != 16000:
#             audio = librosa.resample(audio, orig_sr=sr, target_sr=16000)

#         # Preprocess for Whisper
#         input_features = processor(audio, sampling_rate=16000, return_tensors="pt").input_features.to(device)

#         # Predict
#         with torch.no_grad():
#             predicted_ids = model.generate(input_features)

#         transcription = processor.batch_decode(predicted_ids, skip_special_tokens=True)[0].strip()

#         pred_texts.append(transcription)
#         ref_texts.append(reference)

#         print(f"\n{os.path.basename(audio_path)}")
#         print(f"Reference: {reference}")
#         print(f"Predicted: {transcription}")

#     except Exception as e:
#         print(f"Error processing {audio_path}: {e}")

# # ====== COMPUTE WER ======
# if pred_texts:
#     wer_score = wer_metric.compute(predictions=pred_texts, references=ref_texts)
#     print("\n=======================================")
#     print(f"Evaluated {len(pred_texts)} samples")
#     print(f"Word Error Rate (WER): {wer_score:.4f}")
#     print("=======================================")
# else:
#     print("No successful transcriptions — please check file paths!")

# import torch
# import librosa
# from transformers import WhisperProcessor, WhisperForConditionalGeneration

# # -----------------------------
# # Paths
# # -----------------------------
# MODEL_PATH = r"C:\Users\zaina\OneDrive\Desktop\Khadim-Whisper\whisper_urdu_final"
# AUDIO_PATH = r"C:\Users\zaina\OneDrive\Desktop\Khadim-Whisper\Recording.wav"  # <-- your Urdu audio file

# # -----------------------------
# # Device setup
# # -----------------------------
# device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
# print(f"Using device: {device}")
# if device.type == "cuda":
#     print(f"GPU: {torch.cuda.get_device_name(0)}")

# # -----------------------------
# # Load model and processor
# # -----------------------------
# processor = WhisperProcessor.from_pretrained(MODEL_PATH, language="ur", task="transcribe")
# model = WhisperForConditionalGeneration.from_pretrained(MODEL_PATH).to(device)

# # -----------------------------
# # Load and preprocess audio
# # -----------------------------
# audio, sr = librosa.load(AUDIO_PATH, sr=16000)  # Whisper expects 16kHz mono
# input_features = processor.feature_extractor(audio, sampling_rate=16000, return_tensors="pt").input_features.to(device)

# # -----------------------------
# # Generate transcription
# # -----------------------------
# predicted_ids = model.generate(input_features)
# transcription = processor.batch_decode(predicted_ids, skip_special_tokens=True)[0]

# print("\n==============================")
# print(f"Transcription:\n{transcription}")
# print("==============================\n")

# import torch
# import librosa
# import soundfile as sf
# from transformers import WhisperProcessor, WhisperForConditionalGeneration, AutoTokenizer, SpeechT5ForTextToSpeech

# # -----------------------------
# # Paths
# # -----------------------------
# WHISPER_MODEL_PATH = r"C:\Users\zaina\OneDrive\Desktop\Khadim-Whisper\whisper_urdu_final"
# AUDIO_PATH = r"C:\Users\zaina\OneDrive\Desktop\Khadim-Whisper\Recording.wav"
# OUTPUT_TTS_PATH = r"C:\Users\zaina\OneDrive\Desktop\Khadim-Whisper\urdu_tts_output.wav"

# # -----------------------------
# # Device setup
# # -----------------------------
# device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
# print(f"Using device: {device}")

# # -----------------------------
# # 1️⃣ Load fine-tuned Whisper model
# # -----------------------------
# processor = WhisperProcessor.from_pretrained(WHISPER_MODEL_PATH, language="ur", task="transcribe")
# asr_model = WhisperForConditionalGeneration.from_pretrained(WHISPER_MODEL_PATH).to(device)

# # -----------------------------
# # 2️⃣ Load and preprocess Urdu audio
# # -----------------------------
# audio, sr = librosa.load(AUDIO_PATH, sr=16000)
# input_features = processor.feature_extractor(audio, sampling_rate=16000, return_tensors="pt").input_features.to(device)

# # -----------------------------
# # 3️⃣ Generate Urdu transcription
# # -----------------------------
# predicted_ids = asr_model.generate(input_features)
# urdu_text = processor.batch_decode(predicted_ids, skip_special_tokens=True)[0]

# print("\n==============================")
# print(f"Urdu Transcription:\n{urdu_text}")
# print("==============================\n")

# # -----------------------------
# # 4️⃣ Load Urdu-script TTS model
# # -----------------------------
# tts_model_id = "mahwizzzz/orpheus-urdu-tts"
# tts_tokenizer = AutoTokenizer.from_pretrained(tts_model_id)
# tts_model = SpeechT5ForTextToSpeech.from_pretrained(tts_model_id).to(device)

# # -----------------------------
# # 5️⃣ Generate Urdu speech
# # -----------------------------
# inputs = tts_tokenizer(urdu_text, return_tensors="pt").to(device)

# with torch.no_grad():
#     outputs = tts_model(**inputs)
#     waveform = outputs.waveform[0].cpu().numpy()

# # Save audio
# sf.write(OUTPUT_TTS_PATH, waveform, samplerate=16000)
# print(f"Urdu TTS audio saved to: {OUTPUT_TTS_PATH}")

from gtts import gTTS
import os

# Urdu text from Whisper transcription
urdu_text = "السلام علیکم، مجھے بریانی چاہیے اور ایک پلاؤ چاہیے۔ بریانی آپ نے تھوڑی اسپائسی رکھنی ہے۔"

# Convert to speech
tts = gTTS(text=urdu_text, lang='ur')

# Save as mp3
output_path = r"C:\Users\zaina\OneDrive\Desktop\Khadim-Whisper\urdu_output.mp3"
tts.save(output_path)

print(f"Audio saved at: {output_path}")
os.system(f'start {output_path}')  # plays the file (on Windows)

