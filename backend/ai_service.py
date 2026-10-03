import os
from typing import List
from dotenv import load_dotenv
import torch
from transformers import PreTrainedModel

load_dotenv()

# Compatibility patch: transformers >= 4.45 removed get_extended_attention_mask,
# which NomicBERT requires during inference.
def _get_extended_attention_mask_compat(self, attention_mask, input_shape, device=None, dtype=None):
    if dtype is None:
        dtype = self.dtype if hasattr(self, "dtype") else torch.float32
    if attention_mask.dim() == 3:
        extended = attention_mask[:, None, :, :]
    elif attention_mask.dim() == 2:
        extended = attention_mask[:, None, None, :]
    else:
        raise ValueError(f"Unexpected attention_mask shape: {attention_mask.shape}")
    extended = extended.to(dtype=dtype)
    return (1.0 - extended) * torch.finfo(dtype).min

if not hasattr(PreTrainedModel, "get_extended_attention_mask"):
    PreTrainedModel.get_extended_attention_mask = _get_extended_attention_mask_compat


class AIEngine:
    """Generates 768-dimensional semantic embeddings for cinematic search."""

    def __init__(self):
        self.model_name = "nomic-ai/nomic-embed-text-v1.5"
        self.local_model = None
        self.gemini_client = None
        self.use_gemini_fallback = os.getenv("USE_GEMINI_EMBEDDINGS", "false").lower() == "true"

    def load_model(self):
        if self.use_gemini_fallback:
            self._init_gemini()
            print("[AI Engine] Using Gemini Embedding API.")
            return

        try:
            print(f"[AI Engine] Loading local embedding model '{self.model_name}'...")
            from sentence_transformers import SentenceTransformer
            self.local_model = SentenceTransformer(self.model_name, trust_remote_code=True)
            print("[AI Engine] Local model loaded successfully.")
        except Exception as e:
            print(f"[AI Engine] Failed to load local model ({e}). Falling back to Gemini API.")
            self._init_gemini()
            self.use_gemini_fallback = True

    def _init_gemini(self):
        from google import genai
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is missing.")
        self.gemini_client = genai.Client(api_key=api_key)

    def generate_vector(self, text: str) -> List[float]:
        """Encodes text into a normalized 768-dimensional embedding vector."""
        if not self.use_gemini_fallback and self.local_model is not None:
            query = f"search_query: {text}" if not text.startswith("search_query:") else text
            embedding = self.local_model.encode(query)
            return [float(x) for x in embedding]

        if self.gemini_client is None:
            self._init_gemini()

        from google.genai import types as gtypes
        result = self.gemini_client.models.embed_content(
            model="models/gemini-embedding-001",
            contents=text,
            config=gtypes.EmbedContentConfig(output_dimensionality=768),
        )
        return list(result.embeddings[0].values)


ai_engine = AIEngine()