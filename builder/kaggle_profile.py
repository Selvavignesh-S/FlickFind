"""Runs ON Kaggle (GPU T4 x2): bulk mood profiles with vLLM. Pushed by `builder.mood kaggle-push`.

Reads profile_inputs.jsonl + prompt.json from the attached private dataset, writes
/kaggle/working/profiles.jsonl, which `builder.mood kaggle-fetch` downloads and imports.
OFFSET/LIMIT are filled in at push time so each run stays well inside Kaggle's 12-hour session limit.
"""
import glob
import json
import subprocess
import sys
import time

OFFSET, LIMIT = 0, None  # replaced at push time
MODEL = "cyankiwi/Qwen3.8-27B-AWQ-INT4"  # 4-bit Qwen3.8 27B: the same model Groq serves, sized for 2 x T4
CHUNK = 2000  # films per vLLM call; results are appended after every chunk

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "vllm"], check=True)
import torch  # noqa: E402  (vllm's install may replace torch, so import after it)
import vllm  # noqa: E402
from vllm import LLM, SamplingParams  # noqa: E402

print(f"vllm {vllm.__version__}, torch {torch.__version__}", flush=True)

try:  # the structured-output API was renamed across vLLM versions
    from vllm.sampling_params import StructuredOutputsParams
    def structured(schema): return {"structured_outputs": StructuredOutputsParams(json=schema)}
except ImportError:
    from vllm.sampling_params import GuidedDecodingParams
    def structured(schema): return {"guided_decoding": GuidedDecodingParams(json=schema)}

prompt = json.load(open(glob.glob("/kaggle/input/**/prompt.json", recursive=True)[0]))
films = [json.loads(line) for line in open(glob.glob("/kaggle/input/**/profile_inputs.jsonl", recursive=True)[0])]
films = films[OFFSET:None if LIMIT is None else OFFSET + LIMIT]
print(f"{len(films):,} films, offset {OFFSET}, {torch.cuda.device_count()} GPUs", flush=True)

llm = LLM(MODEL, dtype="half", max_model_len=3072, gpu_memory_utilization=0.92,  # T4 has no bfloat16
          tensor_parallel_size=torch.cuda.device_count())
params = SamplingParams(temperature=0.2, max_tokens=256, **structured(prompt["schema"]))

start = time.time()
with open("/kaggle/working/profiles.jsonl", "w") as out:
    for i in range(0, len(films), CHUNK):
        chunk = films[i:i + CHUNK]
        results = llm.chat([[{"role": "system", "content": prompt["system"]},
                             {"role": "user", "content": f["text"]}] for f in chunk], params, use_tqdm=False,
                           chat_template_kwargs={"enable_thinking": False})  # answer directly, no reasoning text
        for f, r in zip(chunk, results):
            text = r.outputs[0].text
            try:
                profile = json.loads(text)
            except json.JSONDecodeError:
                profile = {"raw": text}  # rejected on import; the film stays pending
            out.write(json.dumps({"tmdb_id": f["tmdb_id"], "fingerprint": f["fingerprint"],
                                  "model": MODEL, "profile": profile}) + "\n")
        out.flush()
        done = i + len(chunk)
        print(f"{done:,}/{len(films):,}  {done / (time.time() - start):.1f} films/s", flush=True)
