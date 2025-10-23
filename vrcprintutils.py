#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import math
import shutil
from typing import Tuple, Literal, List, Iterable, Set, Union

from PIL import Image, ImageOps

# cross-platform color
try:
    from colorama import init as colorama_init, Fore, Style
    colorama_init(autoreset=True)
except Exception:
    class _S: RESET_ALL = ""; BRIGHT = ""
    class _F: GREEN=""; CYAN=""; YELLOW=""; RED=""
    Style, Fore = _S(), _F()

try:
    from InquirerPy import inquirer
except ImportError:
    print("Missing dependency: InquirerPy. Install with: pip install InquirerPy")
    sys.exit(1)

# geometry
ORIG_W, ORIG_H = 2048, 1440
SIDE_BORDER, TOP_BORDER, BOTTOM_TEXT = 64, 69, 291
INNER_W, INNER_H = ORIG_W - 2 * SIDE_BORDER, ORIG_H - TOP_BORDER - BOTTOM_TEXT

SCALE = 1080 / 1920.0
SIDE_SCALED = int(round(SIDE_BORDER * SCALE))
TOP_SCALED = int(round(TOP_BORDER * SCALE))
BOTTOM_TEXT_SCALED = int(round(BOTTOM_TEXT * SCALE))

PORT_W = 1080 + 2 * SIDE_SCALED
PORT_H = 1920 + TOP_SCALED + BOTTOM_TEXT_SCALED

Fmt = Literal["landscape", "portrait"]

# console helpers
def B(s: str) -> str: return f"{Style.BRIGHT}{s}{Style.RESET_ALL}"
def G(s: str) -> str: return f"{Fore.GREEN}{s}{Fore.RESET}"
def C(s: str) -> str: return f"{Fore.CYAN}{s}{Fore.RESET}"
def Y(s: str) -> str: return f"{Fore.YELLOW}{s}{Fore.RESET}"
def R(s: str) -> str: return f"{Fore.RED}{s}{Fore.RESET}"

# banner
BANNER = r"""
  _   _____  _____  ___  ___  _____  ________  __________  ____  __   ____
 | | / / _ \/ ___/ / _ \/ _ \/  _/ |/ /_  __/ /_  __/ __ \/ __ \/ /  / __/
 | |/ / , _/ /__  / ___/ , _// //    / / /     / / / /_/ / /_/ / /___\ \  
 |___/_/|_|\___/ /_/  /_/|_/___/_/|_/ /_/     /_/  \____/\____/____/___/  
                                                                           
===========================[  by GuusDeKroon  ]===========================
"""

SMALL_BANNER = "VRC Print Tools — by GuusDeKroon"

def print_banner() -> None:
    width = shutil.get_terminal_size(fallback=(80, 24)).columns
    need = max(len(line) for line in BANNER.splitlines() if line.strip()) or 0
    if width >= need:
        print(B(BANNER))
    else:
        print(B(SMALL_BANNER))
        print("=" * min(width, len(SMALL_BANNER)))

# ---- core helpers ----
def detect_format(im: Image.Image) -> Fmt:
    w, h = im.size
    if (w, h) == (ORIG_W, ORIG_H):
        return "landscape"
    if (w, h) == (PORT_W, PORT_H):
        return "portrait"
    raise ValueError(f"Unsupported size {w}x{h}. Expected {ORIG_W}x{ORIG_H} or {PORT_W}x{PORT_H}.")

def picture_rect(fmt: Fmt) -> Tuple[int, int, int, int]:
    if fmt == "landscape":
        return (SIDE_BORDER, TOP_BORDER, SIDE_BORDER + INNER_W, TOP_BORDER + INNER_H)
    return (SIDE_SCALED, TOP_SCALED, SIDE_SCALED + 1080, TOP_SCALED + 1920)

def extract_inner(im: Image.Image, fmt: Fmt) -> Image.Image:
    return im.crop(picture_rect(fmt))

def frame_is_light(im: Image.Image) -> bool:
    r, g, b = im.convert("RGB").getpixel((1, 1))
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return lum > 127

# ---- orientation rebuilds (standardize bottom bar to match white canvas) ----
def build_landscape(pic_1920x1080: Image.Image, source_frame: Image.Image) -> Image.Image:
    canvas = Image.new("RGB", (ORIG_W, ORIG_H), (255, 255, 255))  # sides/top are white
    canvas.paste(pic_1920x1080.convert("RGB"), (SIDE_BORDER, TOP_BORDER))

    sw, sh = source_frame.size
    src_bottom_h = BOTTOM_TEXT if (sw, sh) == (ORIG_W, ORIG_H) else BOTTOM_TEXT_SCALED
    bottom_src = source_frame.crop((0, sh - src_bottom_h, sw, sh))

    # If the SOURCE frame was dark, invert the strip so it also becomes light
    if not frame_is_light(source_frame):
        bottom_src = ImageOps.invert(bottom_src.convert("RGB"))

    bottom_resized = bottom_src.resize((ORIG_W, BOTTOM_TEXT), Image.BICUBIC)
    canvas.paste(bottom_resized, (0, ORIG_H - BOTTOM_TEXT))
    return canvas

def build_portrait(pic_1080x1920: Image.Image, source_frame: Image.Image) -> Image.Image:
    canvas = Image.new("RGB", (PORT_W, PORT_H), (255, 255, 255))  # sides/top are white
    canvas.paste(pic_1080x1920.convert("RGB"), (SIDE_SCALED, TOP_SCALED))

    sw, sh = source_frame.size
    src_bottom_h = BOTTOM_TEXT if (sw, sh) == (ORIG_W, ORIG_H) else BOTTOM_TEXT_SCALED
    bottom_src = source_frame.crop((0, sh - src_bottom_h, sw, sh))

    if not frame_is_light(source_frame):
        bottom_src = ImageOps.invert(bottom_src.convert("RGB"))

    bottom_resized = bottom_src.resize((PORT_W, BOTTOM_TEXT_SCALED), Image.BICUBIC)
    canvas.paste(bottom_resized, (0, PORT_H - BOTTOM_TEXT_SCALED))
    return canvas

def rotate_orientation(im: Image.Image, fmt: Fmt, direction: Literal["clockwise", "counterclockwise"]) -> Image.Image:
    pic = extract_inner(im, fmt)
    pic_rot = pic.transpose(Image.ROTATE_270) if direction == "clockwise" else pic.transpose(Image.ROTATE_90)
    return build_portrait(pic_rot, im) if fmt == "landscape" else build_landscape(pic_rot, im)

# ---- precise frame mask (covers left+right+top+bottom; inner photo stays 0) ----
def build_frame_mask_precise(im: Image.Image) -> Image.Image:
    w, h = im.size
    fmt = "landscape" if (w, h) == (ORIG_W, ORIG_H) else "portrait"
    if fmt == "landscape":
        inner_w, inner_h = 1920, 1080
        top_share = TOP_BORDER / (TOP_BORDER + BOTTOM_TEXT)      # ~0.1917
    else:
        inner_w, inner_h = 1080, 1920
        top_share = TOP_SCALED / (TOP_SCALED + BOTTOM_TEXT_SCALED)  # ~0.1921

    pad_w = max(0, w - inner_w)
    pad_h = max(0, h - inner_h)

    left_w  = math.floor(pad_w / 2)
    right_w = pad_w - left_w

    top_h    = int(round(pad_h * top_share))
    bottom_h = pad_h - top_h

    mask = Image.new("L", (w, h), 0)
    if left_w   > 0: mask.paste(255, (0, 0, left_w, h))
    if right_w  > 0: mask.paste(255, (w - right_w, 0, w, h))
    if top_h    > 0: mask.paste(255, (0, 0, w, top_h))
    if bottom_h > 0: mask.paste(255, (0, h - bottom_h, w, h))
    return mask

def toggle_frame_only(im: Image.Image) -> tuple[Image.Image, str]:
    rgb = im.convert("RGB")
    r, g, b = rgb.getpixel((1, 1))
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    suffix = "-darkmode" if lum > 127 else "-lightmode"

    inv = ImageOps.invert(rgb)
    mask = build_frame_mask_precise(rgb)
    out = Image.composite(inv, rgb, mask)
    return out, suffix

def save_with_suffix(src_path: str, tokens: List[str], image: Image.Image) -> str:
    base, ext = os.path.splitext(src_path)
    suffix = "".join(f"-{t}" for t in tokens) if tokens else "-out"
    out_path = f"{base}{suffix}{ext or '.png'}"
    image.save(out_path)
    return out_path

# InquirerPy transformers (display only)
def actions_transformer(v):
    label_by_value = {"orientation": "🔄 Orientation", "mode": "🌓 Light/Dark"}
    label_by_name  = {"🔄 Change orientation": "🔄 Orientation",
                      "🌓 Change light/dark mode": "🌓 Light/Dark"}
    if v is None:
        return ""
    if not isinstance(v, (list, tuple)):
        v = [v]
    labels = []
    for item in v:
        val = getattr(item, "value", None)
        name = getattr(item, "name", None)
        if isinstance(item, dict):
            val = item.get("value", val); name = item.get("name", name)
        if val in label_by_value: labels.append(label_by_value[val]); continue
        if name in label_by_name: labels.append(label_by_name[name]); continue
        if isinstance(item, str): labels.append(label_by_value.get(item, label_by_name.get(item, item))); continue
        labels.append(str(item))
    return ", ".join(labels)

def direction_transformer(v):
    key = getattr(v, "value", v)
    if isinstance(v, dict):
        key = v.get("value", v.get("name", v))
    if isinstance(key, str):
        if key.lower().startswith("clockwise") or key.startswith("↻"): return "↻ Clockwise"
        if key.lower().startswith("counter")  or key.startswith("↺"): return "↺ Counter-clockwise"
    return str(key)

def normalize_actions(actions: Iterable[Union[str, dict, object]]) -> Set[str]:
    result: Set[str] = set()
    for a in actions:
        val = getattr(a, "value", None); name = getattr(a, "name", None)
        if isinstance(a, dict): val = a.get("value", val); name = a.get("name", name)
        s = (val if isinstance(val, str) else "") + " " + (name if isinstance(name, str) else "")
        s = s.lower()
        if "orientation" in s: result.add("orientation")
        if "mode" in s or "light" in s or "dark" in s: result.add("mode")
        if isinstance(a, str):
            s2 = a.lower()
            if "orientation" in s2: result.add("orientation")
            if "mode" in s2 or "light" in s2 or "dark" in s2: result.add("mode")
    return result

# ---- cli ----
def main() -> None:
    print_banner()
    print(C("Select what you want to do:"))
    print()

    actions_raw = inquirer.checkbox(
        message="Choose one or more:",
        choices=[
            {"name": "🔄 Change orientation", "value": "orientation"},
            {"name": "🌓 Change light/dark mode", "value": "mode"},
        ],
        pointer="❯",
        transformer=actions_transformer,
    ).execute()

    actions = normalize_actions(actions_raw)
    if not actions:
        print(Y("No actions selected."))
        sys.exit(0)

    in_path = inquirer.text(
        message="Input image path (e.g., C:\\Users\\YourName\\Pictures\\VRchat\\VRChat_2025-10-22_21-52-27.451_2048x1440.png):",
        validate=lambda s: os.path.isfile(os.path.expanduser(s.strip().strip('"').strip("'"))),
        invalid_message="File not found. Paste a valid path.",
        filter=lambda s: os.path.expanduser(s.strip().strip('"').strip("'")),
    ).execute()

    try:
        im = Image.open(in_path)
    except Exception as e:
        print(R(f"Failed to open image: {e}")); sys.exit(1)

    try:
        fmt = detect_format(im)
    except Exception as e:
        print(R(str(e))); sys.exit(1)

    print(C(f"Detected: {fmt.upper()}  ({im.size[0]}x{im.size[1]})"))

    suffix_tokens: List[str] = []
    current = im

    # 1) Orientation (standardizes bottom to light so frame is uniform post-rotate)
    if "orientation" in actions:
        direction_raw = inquirer.select(
            message="Rotate 90°:",
            choices=[
                {"name": "↻ Clockwise",         "value": "clockwise"},
                {"name": "↺ Counter-clockwise", "value": "counterclockwise"},
            ],
            pointer="❯",
            default="clockwise",
            transformer=direction_transformer,
        ).execute()
        direction = getattr(direction_raw, "value", direction_raw)
        if isinstance(direction, dict): direction = direction.get("value", direction.get("name", "clockwise"))
        direction = "clockwise" if str(direction).lower().startswith(("↻","clockwise")) else "counterclockwise"

        current = rotate_orientation(current, fmt, direction)
        suffix_tokens.append("orientation")
        fmt = "portrait" if fmt == "landscape" else "landscape"
        print(G(f"Orientation applied → {current.size[0]}x{current.size[1]} ({fmt.upper()})"))

    # 2) Frame toggle (now frame is uniform, so sides & bottom flip together)
    if "mode" in actions:
        current, mode_suffix = toggle_frame_only(current)
        suffix_tokens.append(mode_suffix.lstrip("-"))
        print(G(f"Frame toggled → {mode_suffix.lstrip('-').upper()}"))

    try:
        out_path = save_with_suffix(in_path, suffix_tokens, current.convert("RGB"))
    except Exception as e:
        print(R(f"Failed to save: {e}")); sys.exit(1)

    print()
    print(B("Done!") + " Saved → " + G(out_path))
    print()

if __name__ == "__main__":
    main()
