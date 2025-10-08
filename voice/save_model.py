from transformers import WhisperForConditionalGeneration, WhisperProcessor
import torch
import shutil
import os

checkpoint_path = r"C:\Users\zaina\OneDrive\Desktop\Khadim-Whisper\whisper_urdu_finetuned\checkpoint-4050"
final_model_path = r"C:\Users\zaina\OneDrive\Desktop\Khadim-Whisper\whisper_urdu_final"

model = WhisperForConditionalGeneration.from_pretrained(checkpoint_path)

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model.to(device)

processor = WhisperProcessor.from_pretrained("openai/whisper-small")

os.makedirs(final_model_path, exist_ok=True)

model.save_pretrained(final_model_path)
processor.save_pretrained(final_model_path)

print(f"Final model and processor saved to: {final_model_path}")
