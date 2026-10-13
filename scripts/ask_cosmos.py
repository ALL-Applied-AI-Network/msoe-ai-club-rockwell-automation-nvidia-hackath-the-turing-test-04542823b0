"""
scripts/ask_cosmos.py
Sends one or more images (or one video) plus a question to Cosmos 3 Nano
Reasoner and prints its answer. This is the "playground to code" step: the
same request you try on the build.nvidia.com Experience tab, from Python.

Where Cosmos runs:
- By default this script talks to a Cosmos 3 Reasoner NIM container at
  http://127.0.0.1:8000/v1 (on a Brev GPU, reached through `brev port-forward`,
  or on any machine with a big enough NVIDIA GPU). See RUNBOOK.md.
- To use a different server, set COSMOS_BASE_URL (and NVIDIA_API_KEY if that
  server needs a key) in your .env file.

Request format follows NVIDIA's Cosmos 3 Reasoner cookbook: an OpenAI-style
chat request, media first and text last, local files sent as base64 data URIs.

Examples:
    python scripts/ask_cosmos.py vial7.jpg vial9.jpg --prompt "Does image 1 match image 2?"
    python scripts/ask_cosmos.py vial7.jpg --prompt "What color is the liquid?" --think
    python scripts/ask_cosmos.py clip.mp4 --prompt "Describe what happens." --fps 2
"""

import argparse
import base64
import mimetypes
import os
import sys
from pathlib import Path

import openai
from dotenv import load_dotenv

DEFAULT_BASE_URL = "http://127.0.0.1:8000/v1"
DEFAULT_MODEL = "nvidia/cosmos3-nano-reasoner"
DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant."

# Appending this to the question turns on Cosmos's step-by-step reasoning.
# It is the exact wording from NVIDIA's prompt guide and the build.nvidia.com page.
THINK_INSTRUCTIONS = (
    "\n\nAnswer the question using the following format:\n\n"
    "<think>\nYour reasoning.\n</think>\n\n"
    "Write your final answer immediately after the </think> tag."
)

IMAGE_TYPES = {".jpg", ".jpeg", ".png"}
VIDEO_TYPES = {".mp4"}


def file_to_data_uri(path: Path) -> str:
    """Packs a local file into a data URI, because the Cosmos server can't see our disk."""
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def build_media_parts(paths: list[Path]) -> list[dict]:
    """Turns each image or video file into one message part (media goes before text)."""
    parts = []
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        suffix = path.suffix.lower()
        if suffix in IMAGE_TYPES:
            parts.append(
                {"type": "image_url", "image_url": {"url": file_to_data_uri(path)}}
            )
        elif suffix in VIDEO_TYPES:
            parts.append(
                {"type": "video_url", "video_url": {"url": file_to_data_uri(path)}}
            )
        else:
            raise ValueError(
                f"Unsupported file type '{suffix}' for {path.name}. Use .jpg, .jpeg, .png or .mp4."
            )
    return parts


def split_reasoning(text: str) -> tuple[str, str]:
    """Separates the <think> reasoning from the final answer, if reasoning was requested."""
    if "</think>" not in text:
        return "", text.strip()
    reasoning, answer = text.split("</think>", 1)
    return reasoning.replace("<think>", "").strip(), answer.strip()


def ask_cosmos(
    paths: list[Path],
    prompt: str,
    system_prompt: str,
    think: bool,
    fps: float,
    max_tokens: int,
) -> str:
    load_dotenv()
    base_url = os.getenv("COSMOS_BASE_URL", DEFAULT_BASE_URL)
    model = os.getenv("COSMOS_MODEL", DEFAULT_MODEL)
    # A local NIM container ignores the key; a hosted endpoint needs a real one.
    api_key = os.getenv("NVIDIA_API_KEY") or "not-used"

    user_text = prompt + (THINK_INSTRUCTIONS if think else "")
    content = build_media_parts(paths) + [{"type": "text", "text": user_text}]

    # Sampling settings recommended in NVIDIA's Cosmos 3 Reasoner prompt guide.
    if think:
        sampling = {"temperature": 0.6, "top_p": 0.95, "presence_penalty": 0.0}
    else:
        sampling = {"temperature": 0.7, "top_p": 0.8, "presence_penalty": 1.5}
    extra_body = {"top_k": 20, "repetition_penalty": 1.0}
    if any(p.suffix.lower() in VIDEO_TYPES for p in paths):
        extra_body["media_io_kwargs"] = {"video": {"fps": fps}}

    client = openai.OpenAI(api_key=api_key, base_url=base_url, timeout=300)
    print(f"Asking {model} at {base_url} ...")
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content},
        ],
        max_tokens=max_tokens,
        extra_body=extra_body,
        **sampling,
    )
    return response.choices[0].message.content or ""


def main():
    parser = argparse.ArgumentParser(
        description="Ask Cosmos 3 Nano Reasoner a question about images or a video."
    )
    parser.add_argument(
        "files", nargs="+", type=Path, help="Image files (.jpg/.png) or one .mp4 video"
    )
    parser.add_argument("--prompt", required=True, help="Your question for Cosmos")
    parser.add_argument(
        "--system", default=DEFAULT_SYSTEM_PROMPT, help="System prompt (optional)"
    )
    parser.add_argument(
        "--think",
        action="store_true",
        help="Turn on step-by-step reasoning (slower, shows its reasoning)",
    )
    parser.add_argument(
        "--fps", type=float, default=4.0, help="Frames per second to sample from a video"
    )
    parser.add_argument("--max-tokens", type=int, default=4096)
    args = parser.parse_args()

    try:
        text = ask_cosmos(
            args.files, args.prompt, args.system, args.think, args.fps, args.max_tokens
        )
    except openai.APIConnectionError:
        base_url = os.getenv("COSMOS_BASE_URL", DEFAULT_BASE_URL)
        sys.exit(
            f"Could not reach Cosmos at {base_url}.\n"
            "Is the Cosmos NIM container running, and is the port forward open?\n"
            "See 'Cosmos: start the server' in RUNBOOK.md."
        )
    except openai.AuthenticationError:
        sys.exit("Cosmos rejected the API key. Check NVIDIA_API_KEY in your .env file.")
    except openai.APIStatusError as error:
        sys.exit(f"Cosmos returned an error ({error.status_code}): {error.message}")

    reasoning, answer = split_reasoning(text)
    if reasoning:
        print("\n--- Cosmos reasoning ---")
        print(reasoning)
    print("\n--- Cosmos answer ---")
    print(answer)


if __name__ == "__main__":
    main()
