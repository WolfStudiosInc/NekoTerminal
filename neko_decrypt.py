#!/usr/bin/env python3
"""Neko Terminal - Decryption Tool
Decrypts all encrypted data files using the .neko_key file.
Outputs readable JSON files into a 'decrypted' folder.
"""

import os
import sys
import json

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:
    print("[ERROR] cryptography package not installed.")
    print("Run: pip install cryptography")
    input("\nPress Enter to exit...")
    sys.exit(1)

APP_DIR = os.path.dirname(os.path.abspath(__file__))
KEY_FILE = os.path.join(APP_DIR, ".neko_key")
OUTPUT_DIR = os.path.join(APP_DIR, "decrypted")

FILES_TO_DECRYPT = [
    ("neko_config.json", "Configuration (SSH creds, API keys, settings)"),
    ("neko_history.json", "Command history"),
    ("neko_ai_history.json", "AI chat history"),
]


def decrypt_file(filepath, key):
    with open(filepath, "rb") as f:
        blob = f.read()
    aesgcm = AESGCM(key)
    nonce = blob[:12]
    ct = blob[12:]
    raw = aesgcm.decrypt(nonce, ct, None)
    return json.loads(raw.decode("utf-8"))


def main():
    print("=" * 50)
    print("  Neko Terminal - Data Decryption Tool")
    print("=" * 50)
    print()

    if not os.path.exists(KEY_FILE):
        print(f"[ERROR] Key file not found: {KEY_FILE}")
        print("Cannot decrypt without the .neko_key file.")
        input("\nPress Enter to exit...")
        sys.exit(1)

    with open(KEY_FILE, "rb") as f:
        key = f.read()

    if len(key) != 32:
        print("[ERROR] Invalid key file (expected 32 bytes).")
        input("\nPress Enter to exit...")
        sys.exit(1)

    print(f"[OK] Key loaded from {KEY_FILE}")
    print()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    success = 0
    for filename, description in FILES_TO_DECRYPT:
        filepath = os.path.join(APP_DIR, filename)
        outpath = os.path.join(OUTPUT_DIR, filename)

        if not os.path.exists(filepath):
            print(f"[SKIP] {filename} - file not found")
            continue

        try:
            data = decrypt_file(filepath, key)
            with open(outpath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"[OK]   {filename} -> decrypted/{filename}")
            print(f"       ({description})")
            success += 1
        except Exception as e:
            # Maybe it's still plaintext
            try:
                with open(filepath, "r") as f:
                    data = json.load(f)
                with open(outpath, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                print(f"[OK]   {filename} -> decrypted/{filename} (was plaintext)")
                success += 1
            except Exception:
                print(f"[FAIL] {filename} - {e}")

    print()
    print(f"Decrypted {success}/{len(FILES_TO_DECRYPT)} files into: {OUTPUT_DIR}")
    print()
    print("WARNING: The decrypted folder contains sensitive data in plain text.")
    print("         Delete it when you're done inspecting!")
    input("\nPress Enter to exit...")


if __name__ == "__main__":
    main()
