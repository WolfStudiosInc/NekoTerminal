#!/usr/bin/env python3
"""
Neko Terminal v2.0 - A hacker-style custom terminal with SSH, code editor, AI, and full customization.
"""

APP_VERSION = "2.0.1"
GITHUB_OWNER = "WolfStudiosInc"
GITHUB_REPO = "NekoTerminal"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"

import tkinter as tk
from tkinter import ttk, colorchooser, filedialog, messagebox, scrolledtext, font, simpledialog
import subprocess
import threading
import os
import sys
import json
import queue
import signal
import time
import re
import urllib.request
import urllib.error

# Try importing paramiko for SSH
try:
    import paramiko
    HAS_PARAMIKO = True
except ImportError:
    HAS_PARAMIKO = False

# Try importing cryptography for AES-256-GCM encryption
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False



# ─── Config ──────────────────────────────────────────────────────────────────

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(APP_DIR, "neko_config.json")
HISTORY_FILE = os.path.join(APP_DIR, "neko_history.json")
AI_HISTORY_FILE = os.path.join(APP_DIR, "neko_ai_history.json")
KEY_FILE = os.path.join(APP_DIR, ".neko_key")

# When running as a compiled exe, no files are written to disk
IS_FROZEN = getattr(sys, 'frozen', False)

# Global encryption key (loaded automatically from key file)
_ENCRYPTION_KEY = None


def _init_encryption():
    """Initialize encryption: load or generate the AES-256 key file automatically.
    In frozen/exe mode, key is memory-only (never written to disk)."""
    global _ENCRYPTION_KEY
    if not HAS_CRYPTO:
        return False
    if IS_FROZEN:
        # Exe mode: ephemeral key, nothing touches disk
        _ENCRYPTION_KEY = os.urandom(32)
        return True
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, "rb") as f:
            _ENCRYPTION_KEY = f.read()
        if len(_ENCRYPTION_KEY) != 32:
            _ENCRYPTION_KEY = None
            return False
        return True
    else:
        # First run — generate a random 256-bit key
        _ENCRYPTION_KEY = os.urandom(32)
        with open(KEY_FILE, "wb") as f:
            f.write(_ENCRYPTION_KEY)
        # Hide the key file on Windows
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.kernel32.SetFileAttributesW(KEY_FILE, 0x02)
            except Exception:
                pass
        return True


def _encrypt_data(data: bytes) -> bytes:
    """Encrypt data with AES-256-GCM. Returns nonce (12 bytes) + ciphertext."""
    aesgcm = AESGCM(_ENCRYPTION_KEY)
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, data, None)
    return nonce + ct


def _decrypt_data(blob: bytes) -> bytes:
    """Decrypt AES-256-GCM data. Input is nonce (12 bytes) + ciphertext."""
    aesgcm = AESGCM(_ENCRYPTION_KEY)
    nonce = blob[:12]
    ct = blob[12:]
    return aesgcm.decrypt(nonce, ct, None)


def _save_encrypted_file(filepath: str, data):
    """Encrypt and save JSON-serializable data to a file.
    Skipped entirely in exe mode (no files written to disk)."""
    if IS_FROZEN:
        return
    try:
        raw = json.dumps(data, indent=2).encode("utf-8")
        encrypted = _encrypt_data(raw)
        with open(filepath, "wb") as f:
            f.write(encrypted)
    except Exception:
        pass


def _load_encrypted_file(filepath: str):
    """Load and decrypt a JSON file. Returns None on failure.
    In exe mode, always returns None (no persistent files)."""
    if IS_FROZEN:
        return None
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, "rb") as f:
            blob = f.read()
        raw = _decrypt_data(blob)
        return json.loads(raw.decode("utf-8"))
    except Exception:
        # Might be legacy plaintext JSON — try loading directly
        try:
            with open(filepath, "r") as f:
                return json.load(f)
        except Exception:
            return None


def _migrate_plaintext_files():
    """Re-encrypt any existing plaintext JSON files into encrypted format."""
    for filepath in [CONFIG_FILE, HISTORY_FILE, AI_HISTORY_FILE]:
        if not os.path.exists(filepath):
            continue
        try:
            with open(filepath, "r") as f:
                data = json.load(f)
            # It was plaintext — re-save encrypted
            _save_encrypted_file(filepath, data)
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass  # Already encrypted or corrupted
        except Exception:
            pass

DEFAULT_CONFIG = {
    "bg_color": "#0a0a0a",
    "fg_color": "#00ff41",
    "prompt_color": "#00ff41",
    "cursor_color": "#00ff41",
    "selection_bg": "#264f2a",
    "font_family": "Consolas",
    "font_size": 13,
    "opacity": 0.95,
    "window_width": 1100,
    "window_height": 700,
    "ssh_history": [],
    "editor_bg": "#0d0d0d",
    "editor_fg": "#00ff41",
    "editor_line_bg": "#1a1a1a",
    "editor_line_fg": "#555555",
    "last_cwd": "",
    "last_editor_file": "",
    "show_ssh_tab": True,
    "show_editor_tab": True,
    "show_ai_tab": True,
    "ai_provider": "ollama",
    "ai_api_key": "",
    "ai_model": "llama3",
    "ai_base_url": "http://localhost:11434",
}

THEME_PRESETS = {
    "Matrix Green": {"bg_color": "#0a0a0a", "fg_color": "#00ff41", "prompt_color": "#00ff41", "cursor_color": "#00ff41"},
    "Cyber Blue": {"bg_color": "#0a0a1a", "fg_color": "#00d4ff", "prompt_color": "#00d4ff", "cursor_color": "#00d4ff"},
    "Blood Red": {"bg_color": "#0a0000", "fg_color": "#ff3333", "prompt_color": "#ff3333", "cursor_color": "#ff3333"},
    "Amber Retro": {"bg_color": "#0a0800", "fg_color": "#ffb000", "prompt_color": "#ffb000", "cursor_color": "#ffb000"},
    "Purple Haze": {"bg_color": "#0a0012", "fg_color": "#bf5fff", "prompt_color": "#bf5fff", "cursor_color": "#bf5fff"},
    "Ghost White": {"bg_color": "#1a1a2e", "fg_color": "#e0e0e0", "prompt_color": "#e0e0e0", "cursor_color": "#e0e0e0"},
    "Neon Pink": {"bg_color": "#0d0010", "fg_color": "#ff00ff", "prompt_color": "#ff00ff", "cursor_color": "#ff00ff"},
}


def load_config():
    if _ENCRYPTION_KEY and os.path.exists(CONFIG_FILE):
        saved = _load_encrypted_file(CONFIG_FILE)
        if saved and isinstance(saved, dict):
            return {**DEFAULT_CONFIG, **saved}
    return dict(DEFAULT_CONFIG)


def save_config(cfg):
    if _ENCRYPTION_KEY:
        _save_encrypted_file(CONFIG_FILE, cfg)


def load_history():
    if _ENCRYPTION_KEY and os.path.exists(HISTORY_FILE):
        data = _load_encrypted_file(HISTORY_FILE)
        if isinstance(data, list):
            return data
    return []


def save_history(history):
    if _ENCRYPTION_KEY:
        _save_encrypted_file(HISTORY_FILE, history[-1000:])


def load_ai_history():
    if _ENCRYPTION_KEY and os.path.exists(AI_HISTORY_FILE):
        data = _load_encrypted_file(AI_HISTORY_FILE)
        if isinstance(data, list):
            return data
    return []


def save_ai_history(history):
    if _ENCRYPTION_KEY:
        _save_encrypted_file(AI_HISTORY_FILE, history[-200:])


# ─── Shared AI Engine ────────────────────────────────────────────────────────

class AIEngine:
    """Shared AI engine that any tab can call."""

    def __init__(self, config):
        self.config = config

    def call(self, message, context_messages=None):
        provider = self.config.get("ai_provider", "ollama")
        model = self.config.get("ai_model", "llama3")
        base_url = self.config.get("ai_base_url", "http://localhost:11434").rstrip("/")
        api_key = self.config.get("ai_api_key", "")

        messages = []
        messages.append({
            "role": "system",
            "content": "You are Neko AI, a helpful hacker-style AI assistant built into Neko Terminal. "
                       "Be concise, technical, and helpful. Use a slightly edgy hacker tone."
        })
        if context_messages:
            for msg in context_messages[-20:]:
                messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": message})

        if provider == "ollama":
            url = f"{base_url}/api/chat"
            payload = json.dumps({
                "model": model,
                "messages": messages,
                "stream": False,
            }).encode("utf-8")
            req = urllib.request.Request(url, data=payload, method="POST")
            req.add_header("Content-Type", "application/json")
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data.get("message", {}).get("content", "No response received.")

        elif provider in ("openai", "lmstudio", "custom"):
            url = f"{base_url}/chat/completions"
            if provider == "lmstudio":
                url = f"{base_url}/v1/chat/completions"
            payload = json.dumps({
                "model": model,
                "messages": messages,
                "max_tokens": 2048,
                "temperature": 0.7,
            }).encode("utf-8")
            req = urllib.request.Request(url, data=payload, method="POST")
            req.add_header("Content-Type", "application/json")
            if api_key:
                req.add_header("Authorization", f"Bearer {api_key}")
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            choices = data.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "No response.")
            return "No response received."

        return "Unknown AI provider. Configure in Settings or AI tab."


# ─── Updater ─────────────────────────────────────────────────────────────────

class Updater:
    """GitHub Releases-based auto-updater for Neko Terminal."""

    def __init__(self):
        self.latest_version = None
        self.latest_tag = None
        self.download_url = None
        self.release_notes = None
        self.release_page_url = None

    @staticmethod
    def _parse_version(tag):
        """Parse a version tag like 'v2.1.0' or '2.1.0' into a tuple of ints."""
        tag = tag.lstrip("vV").strip()
        parts = []
        for p in tag.split("."):
            try:
                parts.append(int(p))
            except ValueError:
                parts.append(0)
        # Pad to at least 3 parts
        while len(parts) < 3:
            parts.append(0)
        return tuple(parts)

    def check_for_updates(self):
        """Check GitHub Releases for a newer version.
        Returns: (has_update: bool, latest_tag: str, release_notes: str)
        Raises on network/API errors."""
        req = urllib.request.Request(GITHUB_API_URL, method="GET")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("User-Agent", f"NekoTerminal/{APP_VERSION}")

        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        self.latest_tag = data.get("tag_name", "")
        self.release_notes = data.get("body", "No release notes.")
        self.release_page_url = data.get("html_url", "")
        self.latest_version = self._parse_version(self.latest_tag)
        current_version = self._parse_version(APP_VERSION)

        # Determine what asset to look for based on run mode
        self.download_url = None
        if IS_FROZEN:
            # Running as compiled exe — look for .exe asset
            for asset in data.get("assets", []):
                name = asset.get("name", "").lower()
                if name.endswith(".exe") and "neko" in name:
                    self.download_url = asset.get("browser_download_url")
                    break
        else:
            # Running as .py script — look for neko_terminal.py asset
            for asset in data.get("assets", []):
                name = asset.get("name", "").lower()
                if name == "neko_terminal.py":
                    self.download_url = asset.get("browser_download_url")
                    break

        has_update = self.latest_version > current_version
        return has_update, self.latest_tag, self.release_notes

    def download_and_apply(self, progress_callback=None):
        """Download the update and apply it.
        - In .py mode: replaces neko_terminal.py directly with a .bak backup.
        - In .exe mode: downloads new exe next to the current one, creates a
          small batch script that swaps them after the app exits, then the app
          restarts itself.
        Creates a .bak backup first. Returns True on success."""
        if not self.download_url:
            raise RuntimeError("No download URL available. Check for updates first.")

        if progress_callback:
            progress_callback("Downloading update...")

        req = urllib.request.Request(self.download_url, method="GET")
        req.add_header("User-Agent", f"NekoTerminal/{APP_VERSION}")

        with urllib.request.urlopen(req, timeout=120) as resp:
            new_content = resp.read()

        if len(new_content) < 1000:
            raise RuntimeError("Downloaded file seems too small — aborting to be safe.")

        if IS_FROZEN:
            return self._apply_exe_update(new_content, progress_callback)
        else:
            return self._apply_py_update(new_content, progress_callback)

    def _apply_py_update(self, new_content, progress_callback=None):
        """Replace the running .py script with the downloaded version."""
        current_file = os.path.abspath(__file__)
        backup_file = current_file + ".bak"

        if progress_callback:
            progress_callback("Creating backup...")

        import shutil
        try:
            shutil.copy2(current_file, backup_file)
        except Exception as e:
            raise RuntimeError(f"Failed to create backup: {e}")

        if progress_callback:
            progress_callback("Installing update...")

        try:
            with open(current_file, "wb") as f:
                f.write(new_content)
        except Exception as e:
            try:
                shutil.copy2(backup_file, current_file)
            except Exception:
                pass
            raise RuntimeError(f"Failed to write update (backup restored): {e}")

        if progress_callback:
            progress_callback("Update installed!")
        return True

    def _apply_exe_update(self, new_content, progress_callback=None):
        """Apply update when running as a compiled .exe.
        Since a running exe can't overwrite itself on Windows, we:
        1. Save the new exe as NekoTerminal_new.exe
        2. Create an updater.bat that waits, swaps files, and relaunches
        The batch script runs after the app exits."""
        current_exe = sys.executable
        exe_dir = os.path.dirname(current_exe)
        exe_name = os.path.basename(current_exe)
        new_exe = os.path.join(exe_dir, "NekoTerminal_new.exe")
        backup_exe = os.path.join(exe_dir, exe_name + ".bak")
        updater_bat = os.path.join(exe_dir, "_neko_update.bat")

        if progress_callback:
            progress_callback("Saving new version...")

        try:
            with open(new_exe, "wb") as f:
                f.write(new_content)
        except Exception as e:
            raise RuntimeError(f"Failed to save new exe: {e}")

        if progress_callback:
            progress_callback("Preparing updater...")

        # Create a batch script that:
        # 1. Waits for the current exe to close
        # 2. Backs up the old exe
        # 3. Renames the new exe to the original name
        # 4. Relaunches the app
        # 5. Cleans up the batch script itself
        batch_content = f"""@echo off
title Neko Terminal Updater
echo Updating Neko Terminal...
timeout /t 2 /nobreak >nul
if exist "{current_exe}" (
    if exist "{backup_exe}" del /f "{backup_exe}"
    rename "{current_exe}" "{exe_name}.bak"
)
rename "{new_exe}" "{exe_name}"
echo Update complete! Restarting...
start "" "{current_exe}"
del /f "%~f0"
"""
        try:
            with open(updater_bat, "w") as f:
                f.write(batch_content)
        except Exception as e:
            # Clean up downloaded exe
            try:
                os.remove(new_exe)
            except Exception:
                pass
            raise RuntimeError(f"Failed to create updater script: {e}")

        # Store the batch path so the restart handler can launch it
        self._updater_bat = updater_bat

        if progress_callback:
            progress_callback("Update ready! Restart to apply.")
        return True


# ─── Terminal Tab ────────────────────────────────────────────────────────────

class TerminalTab(tk.Frame):
    """Local command terminal with persistent history and inline AI."""

    # Known built-in commands for syntax coloring
    BUILTIN_COMMANDS = {"cd", "clear", "cls", "exit", "quit", "help", "neofetch",
                        "sysinfo", "history", "pwd", "ai"}
    # Common system commands for syntax coloring
    KNOWN_COMMANDS = {"dir", "ls", "cat", "type", "echo", "ping", "python", "pip",
                      "git", "node", "npm", "docker", "curl", "wget", "ssh", "scp",
                      "mkdir", "rmdir", "del", "rm", "cp", "mv", "copy", "move",
                      "find", "grep", "head", "tail", "more", "less", "code",
                      "powershell", "cmd", "ipconfig", "ifconfig", "netstat",
                      "tasklist", "taskkill", "systeminfo", "whoami", "hostname",
                      "java", "javac", "gcc", "g++", "make", "cmake", "cargo",
                      "rustc", "go", "dotnet", "npm", "yarn", "pnpm"}

    def __init__(self, parent, config, status_callback=None, ai_engine=None):
        super().__init__(parent)
        self.config = config
        self.status_callback = status_callback
        self.ai_engine = ai_engine
        self.output_queue = queue.Queue()
        self.process = None
        # Always start at home directory
        self.cwd = os.path.expanduser("~")
        self.command_history = load_history()
        self.history_index = len(self.command_history)

        self._build_ui()
        self._print_banner()
        self._print_prompt()
        self._poll_output()

    def _build_ui(self):
        self.configure(bg=self.config["bg_color"])

        self.text = tk.Text(
            self,
            bg=self.config["bg_color"],
            fg=self.config["fg_color"],
            insertbackground=self.config["cursor_color"],
            selectbackground=self.config["selection_bg"],
            font=(self.config["font_family"], self.config["font_size"]),
            wrap=tk.WORD,
            borderwidth=0,
            highlightthickness=0,
            padx=8,
            pady=8,
        )
        self.text.place(relx=0, rely=0, relwidth=1, relheight=1)

        self.text.tag_configure("prompt", foreground=self.config["prompt_color"])
        self.text.tag_configure("error", foreground="#ff4444")
        self.text.tag_configure("info", foreground="#888888")
        self.text.tag_configure("success", foreground="#44ff44")
        self.text.tag_configure("ai_response", foreground="#ff00ff")
        self.text.tag_configure("ai_label", foreground="#ff00ff")
        # Command syntax coloring
        self.text.tag_configure("cmd_builtin", foreground="#00ffff")   # cyan for built-in cmds
        self.text.tag_configure("cmd_system", foreground="#ff6600")    # orange for system cmds
        self.text.tag_configure("cmd_path", foreground="#ffff00")      # yellow for directories/paths
        self.text.tag_configure("cmd_flag", foreground="#bf5fff")      # purple for flags like --help
        self.text.tag_configure("cmd_string", foreground="#ffd866")    # gold for quoted strings
        # Banner color tags - hacker style
        self.text.tag_configure("cat_red", foreground="#ff0000")
        self.text.tag_configure("cat_green", foreground="#00ff41")
        self.text.tag_configure("cat_cyan", foreground="#00ffff")
        self.text.tag_configure("cat_magenta", foreground="#ff00ff")
        self.text.tag_configure("cat_yellow", foreground="#ffff00")
        self.text.tag_configure("cat_white", foreground="#ffffff")
        self.text.tag_configure("cat_lime", foreground="#39ff14")
        self.text.tag_configure("cat_electric", foreground="#0aff0a")
        self.text.tag_configure("cat_darkgreen", foreground="#006600")
        self.text.tag_configure("cat_neon", foreground="#00ff80")

        self.text.bind("<Return>", self._on_enter)
        self.text.bind("<Up>", self._on_up)
        self.text.bind("<Down>", self._on_down)
        self.text.bind("<BackSpace>", self._on_backspace)
        self.text.bind("<Key>", self._on_key)
        self.text.bind("<Control-c>", self._on_ctrl_c)
        self.text.bind("<Control-l>", self._on_ctrl_l)
        self.text.bind("<Tab>", self._on_tab)
        self.text.bind("<MouseWheel>", self._on_mousewheel)

        self.bind("<Configure>", self._on_resize)

        self.prompt_pos = "1.0"

        # Auto-focus so user can type immediately
        self.after(50, lambda: self.text.focus_set())

    def _on_mousewheel(self, event):
        self.text.yview_scroll(int(-5 * (event.delta / 120)), "units")
        return "break"

    def _on_resize(self, event=None):
        pass

    def _print_banner(self):
        # Side-by-side layout: Cat on left, NEKO block letters on right
        # Cat art lines (4 lines tall) sit next to NEKO (6 lines tall)
        # We'll merge them line by line

        # Line 1: cat line 1 + NEKO line 1
        self.text.insert(tk.END, "\n")
        self.text.insert(tk.END, "   ╱|、", "cat_lime")
        self.text.insert(tk.END, "      ")
        self.text.insert(tk.END, "███╗   ██╗", "cat_lime")
        self.text.insert(tk.END, "███████╗", "cat_electric")
        self.text.insert(tk.END, "██╗  ██╗", "cat_neon")
        self.text.insert(tk.END, " ██████╗ ", "cat_green")
        self.text.insert(tk.END, "\n")

        # Line 2: cat line 2 (eyes) + NEKO line 2
        self.text.insert(tk.END, "  (˚", "cat_lime")
        self.text.insert(tk.END, "ˑ ", "cat_red")
        self.text.insert(tk.END, "7", "cat_lime")
        self.text.insert(tk.END, "      ")
        self.text.insert(tk.END, "████╗  ██║", "cat_lime")
        self.text.insert(tk.END, "██╔════╝", "cat_electric")
        self.text.insert(tk.END, "██║ ██╔╝", "cat_neon")
        self.text.insert(tk.END, "██╔═══██╗", "cat_green")
        self.text.insert(tk.END, "\n")

        # Line 3: cat line 3 + NEKO line 3
        self.text.insert(tk.END, "   |、", "cat_lime")
        self.text.insert(tk.END, "˜〵", "cat_neon")
        self.text.insert(tk.END, "     ")
        self.text.insert(tk.END, "██╔██╗ ██║", "cat_lime")
        self.text.insert(tk.END, "█████╗  ", "cat_electric")
        self.text.insert(tk.END, "█████╔╝ ", "cat_neon")
        self.text.insert(tk.END, "██║   ██║", "cat_green")
        self.text.insert(tk.END, "\n")

        # Line 4: cat line 4 + NEKO line 4
        self.text.insert(tk.END, "   じしˍ,)ノ", "cat_lime")
        self.text.insert(tk.END, "   ")
        self.text.insert(tk.END, "██║╚██╗██║", "cat_lime")
        self.text.insert(tk.END, "██╔══╝  ", "cat_electric")
        self.text.insert(tk.END, "██╔═██╗ ", "cat_neon")
        self.text.insert(tk.END, "██║   ██║", "cat_green")
        self.text.insert(tk.END, "\n")

        # Line 5: padding + NEKO line 5
        self.text.insert(tk.END, "              ")
        self.text.insert(tk.END, "██║ ╚████║", "cat_lime")
        self.text.insert(tk.END, "███████╗", "cat_electric")
        self.text.insert(tk.END, "██║  ██╗", "cat_neon")
        self.text.insert(tk.END, "╚██████╔╝", "cat_green")
        self.text.insert(tk.END, "\n")

        # Line 6: padding + NEKO line 6
        self.text.insert(tk.END, "              ")
        self.text.insert(tk.END, "╚═╝  ╚═══╝", "cat_lime")
        self.text.insert(tk.END, "╚══════╝", "cat_electric")
        self.text.insert(tk.END, "╚═╝  ╚═╝", "cat_neon")
        self.text.insert(tk.END, " ╚═════╝ ", "cat_green")
        self.text.insert(tk.END, "\n")

        # Subtitle - hacker style, underneath
        subtitle_parts = [
            ("\n       ", None),
            ("T", "cat_lime"), ("E", "cat_electric"), ("R", "cat_neon"), ("M", "cat_green"),
            ("I", "cat_lime"), ("N", "cat_electric"), ("A", "cat_neon"), ("L", "cat_green"),
            (" ", None),
            ("v", "cat_darkgreen"), ("2", "cat_lime"), (".", "cat_darkgreen"), ("0", "cat_lime"),
            ("  ", None),
            ("─", "cat_electric"), ("─", "cat_neon"), ("─", "cat_lime"),
            ("  ", None),
            ("H", "cat_lime"), ("a", "cat_electric"), ("c", "cat_neon"), ("k", "cat_green"),
            (" ", None),
            ("T", "cat_lime"), ("h", "cat_electric"), ("e", "cat_neon"),
            (" ", None),
            ("P", "cat_lime"), ("l", "cat_electric"), ("a", "cat_neon"),
            ("n", "cat_green"), ("e", "cat_lime"), ("t", "cat_electric"),
            (" 🐱", "cat_green"),
            ("\n\n", None),
        ]
        for text, tag in subtitle_parts:
            if tag:
                self.text.insert(tk.END, text, tag)
            else:
                self.text.insert(tk.END, text)

        self.text.insert(tk.END, "  Type 'help' for commands. 'ai <question>' for AI. Happy hacking!\n\n", "info")

    def _get_prompt_text(self):
        short_cwd = self.cwd.replace(os.path.expanduser("~"), "~")
        return f"neko@terminal:{short_cwd}$ "

    def _print_prompt(self):
        prompt = self._get_prompt_text()
        self.text.insert(tk.END, prompt, "prompt")
        self.prompt_pos = self.text.index(tk.END + " - 1 chars")
        self.text.see(tk.END)
        self.text.mark_set(tk.INSERT, tk.END)

    def _on_key(self, event):
        cursor = self.text.index(tk.INSERT)
        if self.text.compare(cursor, "<", self.prompt_pos):
            self.text.mark_set(tk.INSERT, tk.END)
            return

    def _on_backspace(self, event):
        cursor = self.text.index(tk.INSERT)
        if self.text.compare(cursor, "<=", self.prompt_pos):
            return "break"

    def _on_enter(self, event):
        line = self.text.get(self.prompt_pos, "end-1c").strip()
        # Color the typed command before executing
        if line:
            self._colorize_input(line)
        self.text.insert(tk.END, "\n")

        if line:
            self.command_history.append(line)
            self.history_index = len(self.command_history)
            save_history(self.command_history)
            self._execute_command(line)
        else:
            self._print_prompt()

        return "break"

    def _colorize_input(self, line):
        """Apply syntax coloring to the command that was just typed."""
        try:
            start = self.prompt_pos
            # Remove any default tags in the input region
            for tag in ("cmd_builtin", "cmd_system", "cmd_path", "cmd_flag", "cmd_string"):
                self.text.tag_remove(tag, start, "end-1c")

            parts = line.split()
            if not parts:
                return

            # Find the command word position
            cmd_word = parts[0]
            cmd_lower = cmd_word.lower()
            cmd_start = start
            cmd_end = f"{start}+{len(cmd_word)}c"

            # Color the command itself
            if cmd_lower in self.BUILTIN_COMMANDS:
                self.text.tag_add("cmd_builtin", cmd_start, cmd_end)
            elif cmd_lower in self.KNOWN_COMMANDS:
                self.text.tag_add("cmd_system", cmd_start, cmd_end)
            else:
                self.text.tag_add("cmd_system", cmd_start, cmd_end)

            # Color arguments: paths, flags, strings
            pos = len(cmd_word)
            for part in parts[1:]:
                # Find this part in the line
                idx = line.find(part, pos)
                if idx < 0:
                    continue
                p_start = f"{start}+{idx}c"
                p_end = f"{start}+{idx + len(part)}c"

                if part.startswith(("-", "--")):
                    self.text.tag_add("cmd_flag", p_start, p_end)
                elif part.startswith(('"', "'")):
                    self.text.tag_add("cmd_string", p_start, p_end)
                elif os.sep in part or part.startswith((".", "~", "/")) or "." in part:
                    self.text.tag_add("cmd_path", p_start, p_end)
                elif os.path.exists(os.path.join(self.cwd, part)):
                    self.text.tag_add("cmd_path", p_start, p_end)

                pos = idx + len(part)
        except Exception:
            pass  # Don't break terminal over coloring errors

    def _on_up(self, event):
        if self.command_history and self.history_index > 0:
            self.history_index -= 1
            self._replace_input(self.command_history[self.history_index])
        return "break"

    def _on_down(self, event):
        if self.history_index < len(self.command_history) - 1:
            self.history_index += 1
            self._replace_input(self.command_history[self.history_index])
        else:
            self.history_index = len(self.command_history)
            self._replace_input("")
        return "break"

    def _replace_input(self, text):
        self.text.delete(self.prompt_pos, tk.END)
        self.text.insert(self.prompt_pos, text)

    def _on_ctrl_c(self, event):
        if self.process:
            try:
                self.process.terminate()
            except Exception:
                pass
            self.text.insert(tk.END, "\n^C\n", "error")
            self.process = None
            self._print_prompt()
        return "break"

    def _on_ctrl_l(self, event):
        self.text.delete("1.0", tk.END)
        self._print_banner()
        self._print_prompt()
        return "break"

    def _on_tab(self, event):
        partial = self.text.get(self.prompt_pos, tk.END).strip()
        if partial:
            try:
                items = os.listdir(self.cwd)
                matches = [i for i in items if i.lower().startswith(partial.split()[-1].lower())]
                if len(matches) == 1:
                    parts = partial.split()
                    parts[-1] = matches[0]
                    self._replace_input(" ".join(parts))
                elif matches:
                    self.text.insert(tk.END, "\n")
                    self.text.insert(tk.END, "  ".join(matches) + "\n", "info")
                    self._print_prompt()
                    self._replace_input(partial)
            except Exception:
                pass
        return "break"

    def _execute_command(self, cmd):
        parts = cmd.strip().split()
        if not parts:
            self._print_prompt()
            return

        builtin = parts[0].lower()

        if builtin == "cd":
            self._cmd_cd(parts)
            return
        elif builtin == "clear" or builtin == "cls":
            self.text.delete("1.0", tk.END)
            self._print_banner()
            self._print_prompt()
            return
        elif builtin == "exit" or builtin == "quit":
            self._save_state()
            self.winfo_toplevel().destroy()
            return
        elif builtin == "help":
            self._cmd_help()
            return
        elif builtin == "neofetch" or builtin == "sysinfo":
            self._cmd_sysinfo()
            return
        elif builtin == "history":
            for i, c in enumerate(self.command_history):
                self.text.insert(tk.END, f"  {i+1}  {c}\n", "info")
            self._print_prompt()
            return
        elif builtin == "pwd":
            self.text.insert(tk.END, self.cwd + "\n")
            self._print_prompt()
            return
        elif builtin == "ai":
            question = cmd[len("ai"):].strip()
            if question:
                self._cmd_ai(question)
            else:
                self.text.insert(tk.END, "Usage: ai <your question>\n", "info")
                self._print_prompt()
            return

        self._run_external(cmd)

    def _cmd_ai(self, question):
        """Ask AI directly from the terminal."""
        if not self.ai_engine:
            self.text.insert(tk.END, "[AI] AI engine not available.\n", "error")
            self._print_prompt()
            return

        self.text.insert(tk.END, "🤖 Thinking...\n", "ai_label")
        self.text.see(tk.END)

        def _worker():
            try:
                response = self.ai_engine.call(question)
                self.output_queue.put(("ai_response", response))
            except Exception as e:
                self.output_queue.put(("ai_error", str(e)))

        threading.Thread(target=_worker, daemon=True).start()

    def _cmd_cd(self, parts):
        if len(parts) < 2:
            target = os.path.expanduser("~")
        else:
            target = os.path.expandvars(os.path.expanduser(parts[1]))

        if not os.path.isabs(target):
            target = os.path.join(self.cwd, target)
        target = os.path.normpath(target)

        if os.path.isdir(target):
            self.cwd = target
            os.chdir(self.cwd)
            if self.status_callback:
                self.status_callback(f"DIR: {self.cwd}")
        else:
            self.text.insert(tk.END, f"cd: no such directory: {parts[1]}\n", "error")
        self._print_prompt()

    def _cmd_help(self):
        """Display comprehensive Neko Help - all bright red for readability."""
        r = "error"  # bright red tag
        self.text.insert(tk.END, "\n")
        self.text.insert(tk.END, "  ╔══════════════════════════════════════════════════════════════════════╗\n", r)
        self.text.insert(tk.END, "  ║                    🐱  N E K O   H E L P  v2.0                      ║\n", r)
        self.text.insert(tk.END, "  ╠══════════════════════════════════════════════════════════════════════╣\n", r)
        self.text.insert(tk.END, "  ║                                                                      ║\n", r)
        self.text.insert(tk.END, "  ║  ── NAVIGATION ──────────────────────────────────────────────────     ║\n", r)
        self.text.insert(tk.END, "  ║                                                                      ║\n", r)
        self.text.insert(tk.END, "  ║    cd <directory>   Change to a directory                             ║\n", r)
        self.text.insert(tk.END, "  ║                     Examples:  cd Documents                          ║\n", r)
        self.text.insert(tk.END, "  ║                                cd ..          (go up one level)       ║\n", r)
        self.text.insert(tk.END, "  ║                                cd ~           (go to home)            ║\n", r)
        self.text.insert(tk.END, "  ║                                cd C:\\Users    (absolute path)         ║\n", r)
        self.text.insert(tk.END, "  ║    pwd              Print current working directory                   ║\n", r)
        self.text.insert(tk.END, "  ║                                                                      ║\n", r)
        self.text.insert(tk.END, "  ║  ── TERMINAL ───────────────────────────────────────────────────      ║\n", r)
        self.text.insert(tk.END, "  ║                                                                      ║\n", r)
        self.text.insert(tk.END, "  ║    clear / cls      Clear the terminal screen                        ║\n", r)
        self.text.insert(tk.END, "  ║    history          Show all saved command history                    ║\n", r)
        self.text.insert(tk.END, "  ║                     History persists between sessions!                ║\n", r)
        self.text.insert(tk.END, "  ║    sysinfo          Show system info (OS, Python, user, etc.)         ║\n", r)
        self.text.insert(tk.END, "  ║    exit / quit      Close Neko Terminal                               ║\n", r)
        self.text.insert(tk.END, "  ║                                                                      ║\n", r)
        self.text.insert(tk.END, "  ║  ── SYSTEM COMMANDS ────────────────────────────────────────────      ║\n", r)
        self.text.insert(tk.END, "  ║                                                                      ║\n", r)
        self.text.insert(tk.END, "  ║    You can run ANY system command directly:                           ║\n", r)
        self.text.insert(tk.END, "  ║      dir            List files in current directory (Windows)         ║\n", r)
        self.text.insert(tk.END, "  ║      ls             List files (Linux/Mac)                            ║\n", r)
        self.text.insert(tk.END, "  ║      ping google.com   Test network connection                       ║\n", r)
        self.text.insert(tk.END, "  ║      python script.py  Run a Python script                           ║\n", r)
        self.text.insert(tk.END, "  ║      git status        Check git status                              ║\n", r)
        self.text.insert(tk.END, "  ║      pip install X     Install Python packages                       ║\n", r)
        self.text.insert(tk.END, "  ║      ipconfig          Show network config (Windows)                 ║\n", r)
        self.text.insert(tk.END, "  ║      whoami            Show current user                             ║\n", r)
        self.text.insert(tk.END, "  ║                                                                      ║\n", r)
        self.text.insert(tk.END, "  ║  ── AI ASSISTANT ───────────────────────────────────────────────      ║\n", r)
        self.text.insert(tk.END, "  ║                                                                      ║\n", r)
        self.text.insert(tk.END, "  ║    ai <question>    Ask AI anything from the terminal                 ║\n", r)
        self.text.insert(tk.END, "  ║                     Examples:  ai how do I list files                 ║\n", r)
        self.text.insert(tk.END, "  ║                                ai explain recursion                  ║\n", r)
        self.text.insert(tk.END, "  ║                                ai write a python hello world          ║\n", r)
        self.text.insert(tk.END, "  ║                                                                      ║\n", r)
        self.text.insert(tk.END, "  ║    Use the 🤖 AI Tab for full persistent chat sessions.               ║\n", r)
        self.text.insert(tk.END, "  ║    Supports: Ollama (local), OpenAI, or any custom API.              ║\n", r)
        self.text.insert(tk.END, "  ║    Configure provider in the AI tab dropdown or Settings.            ║\n", r)
        self.text.insert(tk.END, "  ║                                                                      ║\n", r)
        self.text.insert(tk.END, "  ║  ── TABS ───────────────────────────────────────────────────────      ║\n", r)
        self.text.insert(tk.END, "  ║                                                                      ║\n", r)
        self.text.insert(tk.END, "  ║    ⌨ Terminal      Main command-line terminal                        ║\n", r)
        self.text.insert(tk.END, "  ║    🔗 SSH           Connect to remote servers via SSH                 ║\n", r)
        self.text.insert(tk.END, "  ║    📝 Editor        Code editor with syntax highlighting              ║\n", r)
        self.text.insert(tk.END, "  ║    🤖 AI            Full AI chat with history                         ║\n", r)
        self.text.insert(tk.END, "  ║    + New Tab        Open additional terminal tabs                     ║\n", r)
        self.text.insert(tk.END, "  ║    ✕ Close Tab      Close extra tabs (core tabs can't close)          ║\n", r)
        self.text.insert(tk.END, "  ║                                                                      ║\n", r)
        self.text.insert(tk.END, "  ║  ── EDITOR ──────────────────────────────────────────────────────     ║\n", r)
        self.text.insert(tk.END, "  ║                                                                      ║\n", r)
        self.text.insert(tk.END, "  ║    📂 Open          Open any file to edit                             ║\n", r)
        self.text.insert(tk.END, "  ║    💾 Save          Save current file (Ctrl+S)                        ║\n", r)
        self.text.insert(tk.END, "  ║    📄 Save As       Save with a new filename                          ║\n", r)
        self.text.insert(tk.END, "  ║    🆕 New           Create a new blank file                           ║\n", r)
        self.text.insert(tk.END, "  ║    ▶ Run           Execute the file (Python, JS, etc.)               ║\n", r)
        self.text.insert(tk.END, "  ║    🤖 AI Explain    Ask AI to explain selected code                   ║\n", r)
        self.text.insert(tk.END, "  ║                                                                      ║\n", r)
        self.text.insert(tk.END, "  ║  ── SSH ──────────────────────────────────────────────────────────    ║\n", r)
        self.text.insert(tk.END, "  ║                                                                      ║\n", r)
        self.text.insert(tk.END, "  ║    Enter Host, Port, User, Pass in the connection bar.               ║\n", r)
        self.text.insert(tk.END, "  ║    Click ⚡ Connect to start an SSH session.                          ║\n", r)
        self.text.insert(tk.END, "  ║    Click ✕ Disconnect to end the session.                             ║\n", r)
        self.text.insert(tk.END, "  ║    Requires: pip install paramiko                                    ║\n", r)
        self.text.insert(tk.END, "  ║                                                                      ║\n", r)
        self.text.insert(tk.END, "  ║  ── KEYBOARD SHORTCUTS ─────────────────────────────────────────     ║\n", r)
        self.text.insert(tk.END, "  ║                                                                      ║\n", r)
        self.text.insert(tk.END, "  ║    Ctrl+C           Cancel/kill running command                      ║\n", r)
        self.text.insert(tk.END, "  ║    Ctrl+L           Clear terminal screen                            ║\n", r)
        self.text.insert(tk.END, "  ║    Tab              Auto-complete file and folder names               ║\n", r)
        self.text.insert(tk.END, "  ║    ↑ / ↓            Navigate through command history                  ║\n", r)
        self.text.insert(tk.END, "  ║    Ctrl+S           Save file in the Editor tab                      ║\n", r)
        self.text.insert(tk.END, "  ║    Ctrl+O           Open file in the Editor tab                      ║\n", r)
        self.text.insert(tk.END, "  ║    Enter             Execute command / Send AI message                ║\n", r)
        self.text.insert(tk.END, "  ║    Shift+Enter       New line in AI chat input                       ║\n", r)
        self.text.insert(tk.END, "  ║                                                                      ║\n", r)
        self.text.insert(tk.END, "  ║  ── SETTINGS ────────────────────────────────────────────────────    ║\n", r)
        self.text.insert(tk.END, "  ║                                                                      ║\n", r)
        self.text.insert(tk.END, "  ║    Click ⚙ Settings in the menu bar to customize:                    ║\n", r)
        self.text.insert(tk.END, "  ║      • Theme presets (Matrix, Cyber Blue, Blood Red, etc.)           ║\n", r)
        self.text.insert(tk.END, "  ║      • All terminal colors (bg, text, prompt, cursor, etc.)         ║\n", r)
        self.text.insert(tk.END, "  ║      • Font family and size                                         ║\n", r)
        self.text.insert(tk.END, "  ║                                                                      ║\n", r)
        self.text.insert(tk.END, "  ║  ── COLOR CODING ────────────────────────────────────────────────    ║\n", r)
        self.text.insert(tk.END, "  ║                                                                      ║\n", r)
        self.text.insert(tk.END, "  ║    Commands you type are automatically color-coded:                  ║\n", r)
        self.text.insert(tk.END, "  ║      • Cyan       = Built-in commands (cd, help, ai, etc.)           ║\n", r)
        self.text.insert(tk.END, "  ║      • Orange     = System commands (git, python, pip, etc.)         ║\n", r)
        self.text.insert(tk.END, "  ║      • Yellow     = File paths and directories                       ║\n", r)
        self.text.insert(tk.END, "  ║      • Purple     = Flags (--help, -r, etc.)                         ║\n", r)
        self.text.insert(tk.END, "  ║      • Green      = Normal text                                      ║\n", r)
        self.text.insert(tk.END, "  ║                                                                      ║\n", r)
        self.text.insert(tk.END, "  ╚══════════════════════════════════════════════════════════════════════╝\n\n", r)
        self._print_prompt()

    def _cmd_sysinfo(self):
        info_lines = []
        info_lines.append(f"  OS       : {sys.platform}")
        info_lines.append(f"  Python   : {sys.version.split()[0]}")
        info_lines.append(f"  User     : {os.getenv('USERNAME', os.getenv('USER', 'unknown'))}")
        info_lines.append(f"  Home     : {os.path.expanduser('~')}")
        info_lines.append(f"  CWD      : {self.cwd}")
        info_lines.append(f"  Terminal : Neko Terminal v2.0")
        info_lines.append(f"  History  : {len(self.command_history)} commands saved")
        info_lines.append(f"  AI       : {self.config.get('ai_provider', 'none')} / {self.config.get('ai_model', 'none')}")
        self.text.insert(tk.END, "\n".join(info_lines) + "\n\n")
        self._print_prompt()

    def _run_external(self, cmd):
        if self.status_callback:
            self.status_callback(f"Running: {cmd}")

        def _worker():
            try:
                self.process = subprocess.Popen(
                    cmd, shell=True,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    cwd=self.cwd, text=True, bufsize=1,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                )
                for line in iter(self.process.stdout.readline, ""):
                    self.output_queue.put(("output", line))
                self.process.stdout.close()
                self.process.wait()
                self.output_queue.put(("done", self.process.returncode))
            except Exception as e:
                self.output_queue.put(("error", str(e)))
            finally:
                self.process = None

        threading.Thread(target=_worker, daemon=True).start()

    def _poll_output(self):
        try:
            while True:
                msg_type, data = self.output_queue.get_nowait()
                if msg_type == "output":
                    self.text.insert(tk.END, data)
                    self.text.see(tk.END)
                elif msg_type == "error":
                    self.text.insert(tk.END, f"Error: {data}\n", "error")
                    self._print_prompt()
                elif msg_type == "done":
                    if data != 0:
                        self.text.insert(tk.END, f"[exit code: {data}]\n", "error")
                    self._print_prompt()
                    if self.status_callback:
                        self.status_callback(f"DIR: {self.cwd}")
                elif msg_type == "ai_response":
                    self.text.insert(tk.END, f"🤖 ", "ai_label")
                    self.text.insert(tk.END, f"{data}\n\n", "ai_response")
                    self.text.see(tk.END)
                    self._print_prompt()
                elif msg_type == "ai_error":
                    self.text.insert(tk.END, f"[AI Error] {data}\n\n", "error")
                    self._print_prompt()
        except queue.Empty:
            pass
        self.after(50, self._poll_output)

    def _save_state(self):
        # Don't persist cwd - always start fresh at home
        self.config["last_cwd"] = ""
        save_config(self.config)
        save_history(self.command_history)

    def apply_theme(self, config):
        self.config = config
        self.text.configure(
            fg=config["fg_color"],
            insertbackground=config["cursor_color"],
            selectbackground=config["selection_bg"],
            font=(config["font_family"], config["font_size"]),
        )
        self.text.tag_configure("prompt", foreground=config["prompt_color"])
        self.configure(bg=config["bg_color"])


# ─── SSH Tab ─────────────────────────────────────────────────────────────────

class SSHTab(tk.Frame):
    """SSH remote terminal using paramiko."""

    def __init__(self, parent, config, status_callback=None):
        super().__init__(parent)
        self.config = config
        self.status_callback = status_callback
        self.ssh_client = None
        self.ssh_channel = None
        self.connected = False
        self.ssh_history = config.get("ssh_history", [])
        self._build_ui()

    def _build_ui(self):
        self.configure(bg=self.config["bg_color"])

        conn_frame = tk.Frame(self, bg="#111111")
        conn_frame.pack(fill=tk.X, padx=2, pady=2)

        # Connection dropdown
        tk.Label(conn_frame, text="Connection:", bg="#111111", fg=self.config["fg_color"],
                 font=("Consolas", 10)).pack(side=tk.LEFT, padx=(4, 2))
        self.connection_var = tk.StringVar()
        self.connection_combo = ttk.Combobox(conn_frame, textvariable=self.connection_var,
                                             width=18, state="readonly")
        self.connection_combo.pack(side=tk.LEFT, padx=2)
        self.connection_combo.bind("<<ComboboxSelected>>", self._on_connection_select)

        tk.Label(conn_frame, text="Host:", bg="#111111", fg=self.config["fg_color"],
                 font=("Consolas", 10)).pack(side=tk.LEFT, padx=(10, 2))
        self.host_entry = tk.Entry(conn_frame, bg="#1a1a1a", fg=self.config["fg_color"],
                                   insertbackground=self.config["fg_color"],
                                   font=("Consolas", 10), width=15)
        self.host_entry.pack(side=tk.LEFT, padx=2)

        tk.Label(conn_frame, text="Port:", bg="#111111", fg=self.config["fg_color"],
                 font=("Consolas", 10)).pack(side=tk.LEFT, padx=(10, 2))
        self.port_entry = tk.Entry(conn_frame, bg="#1a1a1a", fg=self.config["fg_color"],
                                   insertbackground=self.config["fg_color"],
                                   font=("Consolas", 10), width=5)
        self.port_entry.insert(0, "22")
        self.port_entry.pack(side=tk.LEFT, padx=2)

        tk.Label(conn_frame, text="User:", bg="#111111", fg=self.config["fg_color"],
                 font=("Consolas", 10)).pack(side=tk.LEFT, padx=(10, 2))
        self.user_entry = tk.Entry(conn_frame, bg="#1a1a1a", fg=self.config["fg_color"],
                                   insertbackground=self.config["fg_color"],
                                   font=("Consolas", 10), width=12)
        self.user_entry.pack(side=tk.LEFT, padx=2)

        tk.Label(conn_frame, text="Pass:", bg="#111111", fg=self.config["fg_color"],
                 font=("Consolas", 10)).pack(side=tk.LEFT, padx=(10, 2))
        self.pass_entry = tk.Entry(conn_frame, bg="#1a1a1a", fg=self.config["fg_color"],
                                   insertbackground=self.config["fg_color"],
                                   font=("Consolas", 10), width=12, show="•")
        self.pass_entry.pack(side=tk.LEFT, padx=2)

        # Save connection button
        self.save_conn_btn = tk.Button(conn_frame, text="💾 Save", bg="#003300", fg=self.config["fg_color"],
                                       font=("Consolas", 9, "bold"), relief=tk.FLAT,
                                       activebackground="#005500", command=self._save_connection)
        self.save_conn_btn.pack(side=tk.LEFT, padx=6)

        self.connect_btn = tk.Button(conn_frame, text="⚡ Connect", bg="#003300", fg=self.config["fg_color"],
                                     font=("Consolas", 10, "bold"), relief=tk.FLAT,
                                     activebackground="#005500", command=self._connect)
        self.connect_btn.pack(side=tk.LEFT, padx=6)

        self.disconnect_btn = tk.Button(conn_frame, text="✕ Disconnect", bg="#330000", fg="#ff4444",
                                        font=("Consolas", 10, "bold"), relief=tk.FLAT,
                                        activebackground="#550000", command=self._disconnect,
                                        state=tk.DISABLED)
        self.disconnect_btn.pack(side=tk.LEFT, padx=2)

        self.text = tk.Text(
            self, bg=self.config["bg_color"], fg=self.config["fg_color"],
            insertbackground=self.config["cursor_color"],
            selectbackground=self.config["selection_bg"],
            font=(self.config["font_family"], self.config["font_size"]),
            wrap=tk.WORD, borderwidth=0, highlightthickness=0, padx=8, pady=8,
        )
        self.text.pack(fill=tk.BOTH, expand=True)
        self.text.tag_configure("error", foreground="#ff4444")
        self.text.tag_configure("info", foreground="#888888")
        self.text.tag_configure("success", foreground="#44ff44")
        self.text.tag_configure("prompt", foreground=self.config["prompt_color"])

        if not HAS_PARAMIKO:
            self.text.insert(tk.END, "[!] paramiko not installed. Install with: pip install paramiko\n", "error")
            self.text.insert(tk.END, "    SSH functionality is disabled.\n\n", "info")
        else:
            self.text.insert(tk.END, "[SSH] Ready to connect. Enter credentials above.\n\n", "info")

        # Send keystrokes directly to SSH channel (real terminal behavior)
        self.text.bind("<Key>", self._on_key)
        self.text.bind("<Return>", self._on_enter)
        self.text.bind("<BackSpace>", self._on_backspace)
        self.text.bind("<Control-c>", self._on_ctrl_c)
        self.text.bind("<Control-v>", self._on_paste)
        self.text.bind("<Control-a>", self._on_select_all)
        self.text.bind("<Up>", lambda e: self._send_escape("[A"))
        self.text.bind("<Down>", lambda e: self._send_escape("[B"))
        self.text.bind("<Right>", lambda e: self._send_escape("[C"))
        self.text.bind("<Left>", lambda e: self._send_escape("[D"))
        self.text.bind("<Home>", lambda e: self._send_escape("[H"))
        self.text.bind("<End>", lambda e: self._send_escape("[F"))
        self.text.bind("<Delete>", lambda e: self._send_escape("[3~"))
        self.text.bind("<Tab>", self._on_tab)
        self.text.bind("<MouseWheel>", self._on_mousewheel)

        self.output_queue = queue.Queue()
        self._poll_output()
        # Now that all widgets exist, populate dropdown and load last connection
        self._update_connection_dropdown()
        self._load_last_connection()

    def _update_connection_dropdown(self):
        """Update the connection dropdown with saved connections."""
        connection_names = [conn.get("name", f"{conn.get('host', '')}:{conn.get('port', '')}") 
                           for conn in self.ssh_history]
        self.connection_combo['values'] = connection_names
        if connection_names:
            self.connection_combo.current(0)  # Select first item by default
            self._on_connection_select()  # Load the first connection

    def _on_connection_select(self, event=None):
        """Load selected connection into the fields."""
        selection = self.connection_var.get()
        if not selection:
            return
            
        # Find the connection with matching name
        for conn in self.ssh_history:
            conn_name = conn.get("name", f"{conn.get('host', '')}:{conn.get('port', '')}")
            if conn_name == selection:
                self.host_entry.delete(0, tk.END)
                self.host_entry.insert(0, conn.get("host", ""))
                self.port_entry.delete(0, tk.END)
                self.port_entry.insert(0, str(conn.get("port", 22)))
                self.user_entry.delete(0, tk.END)
                self.user_entry.insert(0, conn.get("user", ""))
                # Load saved password (encrypted on disk)
                self.pass_entry.delete(0, tk.END)
                if conn.get("password"):
                    self.pass_entry.insert(0, conn.get("password", ""))
                break

    def _save_connection(self):
        """Save current connection to history (all data encrypted on disk)."""
        host = self.host_entry.get().strip()
        port = self.port_entry.get().strip()
        user = self.user_entry.get().strip()
        password = self.pass_entry.get().strip()
        if not host or not user:
            messagebox.showwarning("SSH", "Host and username are required to save connection.")
            return
            
        try:
            port_int = int(port) if port else 22
        except ValueError:
            messagebox.showwarning("SSH", "Port must be a valid number.")
            return
            
        # Ask for connection name
        name = tk.simpledialog.askstring("Save Connection", "Enter a name for this connection:")
        if not name:
            name = f"{host}:{port_int}"
            
        # Check if connection with this name already exists
        existing_index = None
        for i, conn in enumerate(self.ssh_history):
            existing_name = conn.get("name", f"{conn.get('host', '')}:{conn.get('port', '')}")
            if existing_name == name:
                existing_index = i
                break
                
        new_conn = {
            "name": name,
            "host": host,
            "port": port_int,
            "user": user,
            "password": password  # Safe: entire config is AES-256-GCM encrypted on disk
        }
        
        if existing_index is not None:
            self.ssh_history[existing_index] = new_conn
        else:
            self.ssh_history.append(new_conn)
            
        # Save to config
        self.config["ssh_history"] = self.ssh_history
        save_config(self.config)
        
        # Update dropdown
        self._update_connection_dropdown()
        messagebox.showinfo("SSH", f"Connection '{name}' saved successfully!")

    def _load_last_connection(self):
        """Load the last used connection on startup."""
        if self.ssh_history:
            # Load the most recent connection (last in list)
            last_conn = self.ssh_history[-1]
            self.host_entry.delete(0, tk.END)
            self.host_entry.insert(0, last_conn.get("host", ""))
            self.port_entry.delete(0, tk.END)
            self.port_entry.insert(0, str(last_conn.get("port", 22)))
            self.user_entry.delete(0, tk.END)
            self.user_entry.insert(0, last_conn.get("user", ""))
            # Load saved password
            self.pass_entry.delete(0, tk.END)
            if last_conn.get("password"):
                self.pass_entry.insert(0, last_conn.get("password", ""))
            # Update dropdown selection
            conn_name = last_conn.get("name", f"{last_conn.get('host', '')}:{last_conn.get('port', '')}")
            self.connection_var.set(conn_name)

    def _connect(self):
        if not HAS_PARAMIKO:
            messagebox.showerror("SSH Error", "paramiko is not installed.\nRun: pip install paramiko")
            return
        host = self.host_entry.get().strip()
        port = self.port_entry.get().strip()
        user = self.user_entry.get().strip()
        password = self.pass_entry.get().strip()
        if not host or not user:
            messagebox.showwarning("SSH", "Host and username are required.")
            return
        try:
            port = int(port)
        except ValueError:
            port = 22
        self.text.insert(tk.END, f"[SSH] Connecting to {user}@{host}:{port}...\n", "info")

        def _worker():
            try:
                self.ssh_client = paramiko.SSHClient()
                self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                self.ssh_client.connect(host, port=port, username=user, password=password, timeout=10)
                self.ssh_channel = self.ssh_client.invoke_shell(term="xterm", width=120, height=40)
                self.connected = True
                self.output_queue.put(("connected", f"Connected to {host}"))
                while self.connected and self.ssh_channel:
                    if self.ssh_channel.recv_ready():
                        data = self.ssh_channel.recv(4096).decode("utf-8", errors="replace")
                        # Strip ANSI escape sequences comprehensively
                        clean = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', data)       # CSI sequences
                        clean = re.sub(r'\x1b\[\?[0-9;]*[a-zA-Z]', '', clean)    # Private mode (e.g. ?2004h)
                        clean = re.sub(r'\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)', '', clean)  # OSC sequences (title etc.)
                        clean = re.sub(r'\x1b\([A-Z0-9]', '', clean)             # Character set selection
                        clean = re.sub(r'\x1b[=>]', '', clean)                    # Keypad mode
                        clean = re.sub(r'\x1b\[[0-9;]*~', '', clean)             # Function keys
                        clean = clean.replace('\r\n', '\n').replace('\r', '\n')   # Normalize line endings
                        if clean:
                            self.output_queue.put(("output", clean))
                    else:
                        time.sleep(0.05)
            except Exception as e:
                self.output_queue.put(("error", str(e)))
                self.connected = False
        threading.Thread(target=_worker, daemon=True).start()

    def _disconnect(self):
        self.connected = False
        if self.ssh_channel:
            try: self.ssh_channel.close()
            except: pass
        if self.ssh_client:
            try: self.ssh_client.close()
            except: pass
        self.ssh_client = None
        self.ssh_channel = None
        self.connect_btn.configure(state=tk.NORMAL)
        self.disconnect_btn.configure(state=tk.DISABLED)
        self.text.insert(tk.END, "\n[SSH] Disconnected.\n", "info")
        self.text.see(tk.END)
        if self.status_callback:
            self.status_callback("SSH: Disconnected")

    def _on_key(self, event):
        """Send printable keystrokes directly to SSH channel."""
        if not self.connected or not self.ssh_channel:
            return "break"
        # Allow Ctrl combos to pass through (copy/paste/select handled separately)
        if event.state & 0x4:  # Control key held
            return "break"
        # Ignore modifier-only keys and special keys handled by other bindings
        if event.keysym in ("Shift_L", "Shift_R", "Control_L", "Control_R",
                            "Alt_L", "Alt_R", "Caps_Lock", "Escape",
                            "Return", "BackSpace", "Tab",
                            "Up", "Down", "Left", "Right", "Home", "End",
                            "Delete", "Insert", "Prior", "Next",
                            "F1", "F2", "F3", "F4", "F5", "F6",
                            "F7", "F8", "F9", "F10", "F11", "F12"):
            return "break"
        if event.char:
            try:
                self.ssh_channel.send(event.char)
            except Exception:
                pass
        return "break"

    def _on_enter(self, event):
        if not self.connected or not self.ssh_channel:
            return "break"
        try:
            self.ssh_channel.send("\n")
        except Exception as e:
            self.text.insert(tk.END, f"[SSH Error] {e}\n", "error")
        return "break"

    def _on_backspace(self, event):
        if self.connected and self.ssh_channel:
            try:
                self.ssh_channel.send("\x7f")
            except Exception:
                pass
        return "break"

    def _on_tab(self, event):
        if self.connected and self.ssh_channel:
            try:
                self.ssh_channel.send("\t")
            except Exception:
                pass
        return "break"

    def _send_escape(self, seq):
        if self.connected and self.ssh_channel:
            try:
                self.ssh_channel.send(f"\x1b{seq}")
            except Exception:
                pass
        return "break"

    def _on_ctrl_c(self, event):
        # If text is selected, copy to clipboard; otherwise send interrupt
        if self.text.tag_ranges(tk.SEL):
            try:
                selected = self.text.get(tk.SEL_FIRST, tk.SEL_LAST)
                self.clipboard_clear()
                self.clipboard_append(selected)
            except tk.TclError:
                pass
        elif self.connected and self.ssh_channel:
            try:
                self.ssh_channel.send("\x03")
            except Exception:
                pass
        return "break"

    def _on_paste(self, event):
        """Paste clipboard text to SSH channel."""
        if not self.connected or not self.ssh_channel:
            return "break"
        try:
            text = self.clipboard_get()
            if text:
                self.ssh_channel.send(text)
        except (tk.TclError, Exception):
            pass
        return "break"

    def _on_select_all(self, event):
        self.text.tag_add(tk.SEL, "1.0", tk.END)
        return "break"

    def _on_mousewheel(self, event):
        self.text.yview_scroll(int(-5 * (event.delta / 120)), "units")
        return "break"

    def _insert_ssh_output(self, data):
        """Insert SSH output, handling backspace characters by deleting from widget."""
        i = 0
        buf = []
        while i < len(data):
            ch = data[i]
            if ch == '\x08':
                # Flush any buffered text first
                if buf:
                    self.text.insert(tk.END, ''.join(buf))
                    buf = []
                # Delete the previous character in the text widget
                pos = self.text.index("end-2c")
                if self.text.compare(pos, ">", "1.0"):
                    self.text.delete(pos)
            elif ch == '\x7f':
                # DEL character - same as backspace
                if buf:
                    self.text.insert(tk.END, ''.join(buf))
                    buf = []
                pos = self.text.index("end-2c")
                if self.text.compare(pos, ">", "1.0"):
                    self.text.delete(pos)
            else:
                buf.append(ch)
            i += 1
        # Flush remaining text
        if buf:
            self.text.insert(tk.END, ''.join(buf))

    def _poll_output(self):
        try:
            while True:
                msg_type, data = self.output_queue.get_nowait()
                if msg_type == "output":
                    self._insert_ssh_output(data)
                    self.text.see(tk.END)
                elif msg_type == "connected":
                    self.text.insert(tk.END, f"[SSH] {data}\n", "success")
                    self.connect_btn.configure(state=tk.DISABLED)
                    self.disconnect_btn.configure(state=tk.NORMAL)
                    if self.status_callback:
                        self.status_callback(f"SSH: {data}")
                elif msg_type == "error":
                    self.text.insert(tk.END, f"[SSH Error] {data}\n", "error")
                    self.text.see(tk.END)
        except queue.Empty:
            pass
        self.after(50, self._poll_output)

    def apply_theme(self, config):
        self.config = config
        self.text.configure(
            bg=config["bg_color"], fg=config["fg_color"],
            insertbackground=config["cursor_color"],
            font=(config["font_family"], config["font_size"]),
        )
        self.configure(bg=config["bg_color"])


# ─── Code Editor Tab ────────────────────────────────────────────────────────

class EditorTab(tk.Frame):
    """Code editor with line numbers, syntax highlighting, and inline AI."""

    def __init__(self, parent, config, status_callback=None, ai_engine=None):
        super().__init__(parent)
        self.config = config
        self.status_callback = status_callback
        self.ai_engine = ai_engine
        self.current_file = None
        self.modified = False
        self._build_ui()
        last_file = config.get("last_editor_file", "")
        if last_file and os.path.isfile(last_file):
            self._load_file(last_file)

    def _build_ui(self):
        self.configure(bg=self.config["bg_color"])

        toolbar = tk.Frame(self, bg="#111111")
        toolbar.pack(fill=tk.X, padx=2, pady=2)

        btn_style = {"bg": "#1a1a1a", "fg": self.config["fg_color"], "font": ("Consolas", 10, "bold"),
                     "relief": tk.FLAT, "activebackground": "#333333", "padx": 8}

        tk.Button(toolbar, text="📂 Open", command=self._open_file, **btn_style).pack(side=tk.LEFT, padx=2)
        tk.Button(toolbar, text="💾 Save", command=self._save_file, **btn_style).pack(side=tk.LEFT, padx=2)
        tk.Button(toolbar, text="📄 Save As", command=self._save_as, **btn_style).pack(side=tk.LEFT, padx=2)
        tk.Button(toolbar, text="🆕 New", command=self._new_file, **btn_style).pack(side=tk.LEFT, padx=2)
        tk.Button(toolbar, text="▶ Run", command=self._run_file, **btn_style).pack(side=tk.LEFT, padx=2)
        tk.Button(toolbar, text="🤖 AI Explain", command=self._ai_explain, **btn_style).pack(side=tk.LEFT, padx=2)

        self.file_label = tk.Label(toolbar, text="  No file open", bg="#111111",
                                   fg="#888888", font=("Consolas", 10))
        self.file_label.pack(side=tk.LEFT, padx=10)

        editor_frame = tk.Frame(self, bg=self.config["bg_color"])
        editor_frame.pack(fill=tk.BOTH, expand=True)

        self.line_numbers = tk.Text(
            editor_frame, width=5,
            bg=self.config.get("editor_line_bg", "#1a1a1a"),
            fg=self.config.get("editor_line_fg", "#555555"),
            font=(self.config["font_family"], self.config["font_size"]),
            borderwidth=0, highlightthickness=0, padx=4, pady=8,
            state=tk.DISABLED, takefocus=0,
        )
        self.line_numbers.pack(side=tk.LEFT, fill=tk.Y)

        self.editor = tk.Text(
            editor_frame,
            bg=self.config.get("editor_bg", "#0d0d0d"),
            fg=self.config.get("editor_fg", self.config["fg_color"]),
            insertbackground=self.config["cursor_color"],
            selectbackground=self.config["selection_bg"],
            font=(self.config["font_family"], self.config["font_size"]),
            wrap=tk.NONE, borderwidth=0, highlightthickness=0,
            padx=8, pady=8, undo=True, autoseparators=True, tabs=("4c",),
        )
        self.editor.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar_y = tk.Scrollbar(editor_frame, command=self._on_scroll_y)
        scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.editor.config(yscrollcommand=scrollbar_y.set)

        scrollbar_x = tk.Scrollbar(self, orient=tk.HORIZONTAL, command=self.editor.xview)
        scrollbar_x.pack(fill=tk.X)
        self.editor.config(xscrollcommand=scrollbar_x.set)

        self.editor.tag_configure("keyword", foreground="#ff6188")
        self.editor.tag_configure("string", foreground="#ffd866")
        self.editor.tag_configure("comment", foreground="#555555")
        self.editor.tag_configure("number", foreground="#ab9df2")
        self.editor.tag_configure("builtin", foreground="#78dce8")
        self.editor.tag_configure("decorator", foreground="#ff9800")

        self.editor.bind("<KeyRelease>", self._on_key_release)
        self.editor.bind("<Control-s>", lambda e: self._save_file())
        self.editor.bind("<Control-o>", lambda e: self._open_file())
        self.editor.bind("<Tab>", self._on_tab)

        self.run_output = tk.Text(
            self, height=8, bg="#080808", fg=self.config["fg_color"],
            font=(self.config["font_family"], self.config["font_size"] - 1),
            borderwidth=0, highlightthickness=0, padx=8, pady=4,
        )
        self.run_output.pack(fill=tk.X, padx=2, pady=(2, 0))
        self.run_output.tag_configure("ai_out", foreground="#ff00ff")
        self.run_output.insert(tk.END, "[Output] Run a file to see output here. Use 🤖 AI Explain for code help.\n")
        self.run_output.configure(state=tk.DISABLED)
        self._update_line_numbers()

    def _ai_explain(self):
        """Send selected code or full file to AI for explanation."""
        if not self.ai_engine:
            return
        try:
            selected = self.editor.get(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            selected = self.editor.get("1.0", "end-1c")
        if not selected.strip():
            return

        self.run_output.configure(state=tk.NORMAL)
        self.run_output.delete("1.0", tk.END)
        self.run_output.insert(tk.END, "[AI] Analyzing code...\n")
        self.run_output.configure(state=tk.DISABLED)

        def _worker():
            try:
                prompt = f"Explain this code concisely:\n```\n{selected[:3000]}\n```"
                response = self.ai_engine.call(prompt)
                self.after(0, lambda: self._show_ai_output(response))
            except Exception as e:
                self.after(0, lambda: self._show_ai_output(f"[Error] {e}"))

        threading.Thread(target=_worker, daemon=True).start()

    def _show_ai_output(self, text):
        self.run_output.configure(state=tk.NORMAL)
        self.run_output.delete("1.0", tk.END)
        self.run_output.insert(tk.END, "🤖 AI Explanation:\n", "ai_out")
        self.run_output.insert(tk.END, text + "\n")
        self.run_output.see(tk.END)
        self.run_output.configure(state=tk.DISABLED)

    def _on_scroll_y(self, *args):
        self.editor.yview(*args)
        self.line_numbers.yview(*args)

    def _on_tab(self, event):
        self.editor.insert(tk.INSERT, "    ")
        return "break"

    def _on_key_release(self, event):
        self._update_line_numbers()
        self._syntax_highlight()
        self.modified = True

    def _update_line_numbers(self):
        self.line_numbers.configure(state=tk.NORMAL)
        self.line_numbers.delete("1.0", tk.END)
        line_count = int(self.editor.index("end-1c").split(".")[0])
        line_nums = "\n".join(str(i) for i in range(1, line_count + 1))
        self.line_numbers.insert("1.0", line_nums)
        self.line_numbers.configure(state=tk.DISABLED)

    def _syntax_highlight(self):
        content = self.editor.get("1.0", tk.END)
        for tag in ("keyword", "string", "comment", "number", "builtin", "decorator"):
            self.editor.tag_remove(tag, "1.0", tk.END)
        keywords = r'\b(def|class|import|from|return|if|elif|else|for|while|try|except|finally|with|as|yield|lambda|pass|break|continue|and|or|not|in|is|True|False|None|raise|global|nonlocal|async|await|del|assert)\b'
        builtins_re = r'\b(print|len|range|int|str|float|list|dict|set|tuple|type|isinstance|super|open|input|map|filter|zip|enumerate|sorted|reversed|any|all|min|max|sum|abs|round|format|id|hex|oct|bin|chr|ord)\b'
        patterns = [
            (keywords, "keyword"), (builtins_re, "builtin"),
            (r'#[^\n]*', "comment"), (r'"(?:[^"\\]|\\.)*"', "string"),
            (r"'(?:[^'\\]|\\.)*'", "string"), (r'\b\d+\.?\d*\b', "number"),
            (r'@\w+', "decorator"),
        ]
        for pattern, tag in patterns:
            for match in re.finditer(pattern, content):
                start = f"1.0+{match.start()}c"
                end = f"1.0+{match.end()}c"
                self.editor.tag_add(tag, start, end)

    def _load_file(self, filepath):
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            self.editor.delete("1.0", tk.END)
            self.editor.insert("1.0", content)
            self.current_file = filepath
            self.file_label.configure(text=f"  {os.path.basename(filepath)}")
            self.modified = False
            self._update_line_numbers()
            self._syntax_highlight()
            self.config["last_editor_file"] = filepath
            save_config(self.config)
            if self.status_callback:
                self.status_callback(f"Editing: {filepath}")
        except Exception:
            pass

    def _open_file(self):
        filepath = filedialog.askopenfilename(
            filetypes=[("All Files", "*.*"), ("Python", "*.py"), ("Text", "*.txt"),
                       ("JavaScript", "*.js"), ("HTML", "*.html"), ("CSS", "*.css"),
                       ("JSON", "*.json"), ("YAML", "*.yml;*.yaml"), ("Markdown", "*.md")]
        )
        if filepath:
            self._load_file(filepath)

    def _save_file(self):
        if self.current_file:
            try:
                content = self.editor.get("1.0", "end-1c")
                with open(self.current_file, "w", encoding="utf-8") as f:
                    f.write(content)
                self.modified = False
                if self.status_callback:
                    self.status_callback(f"Saved: {self.current_file}")
            except Exception as e:
                messagebox.showerror("Error", f"Could not save file:\n{e}")
        else:
            self._save_as()

    def _save_as(self):
        filepath = filedialog.asksaveasfilename(
            defaultextension=".py",
            filetypes=[("Python", "*.py"), ("Text", "*.txt"), ("All Files", "*.*")]
        )
        if filepath:
            self.current_file = filepath
            self.file_label.configure(text=f"  {os.path.basename(filepath)}")
            self.config["last_editor_file"] = filepath
            save_config(self.config)
            self._save_file()

    def _new_file(self):
        if self.modified:
            if messagebox.askyesno("Unsaved Changes", "Save current file?"):
                self._save_file()
        self.editor.delete("1.0", tk.END)
        self.current_file = None
        self.file_label.configure(text="  New File")
        self.modified = False
        self._update_line_numbers()

    def _run_file(self):
        if not self.current_file:
            self._save_as()
        if not self.current_file:
            return
        self._save_file()
        self.run_output.configure(state=tk.NORMAL)
        self.run_output.delete("1.0", tk.END)
        self.run_output.insert(tk.END, f"[Running] {self.current_file}\n")

        def _worker():
            try:
                ext = os.path.splitext(self.current_file)[1].lower()
                if ext == ".py":
                    cmd = [sys.executable, self.current_file]
                elif ext == ".js":
                    cmd = ["node", self.current_file]
                elif ext in (".bat", ".cmd"):
                    cmd = [self.current_file]
                elif ext == ".ps1":
                    cmd = ["powershell", "-File", self.current_file]
                else:
                    cmd = [self.current_file]
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=30,
                    cwd=os.path.dirname(self.current_file),
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                )
                output = result.stdout + result.stderr
                self.after(0, lambda: self._show_run_output(output, result.returncode))
            except subprocess.TimeoutExpired:
                self.after(0, lambda: self._show_run_output("[Timeout] Script exceeded 30 seconds.", 1))
            except Exception as e:
                self.after(0, lambda: self._show_run_output(f"[Error] {e}", 1))
        threading.Thread(target=_worker, daemon=True).start()

    def _show_run_output(self, output, code):
        self.run_output.configure(state=tk.NORMAL)
        self.run_output.insert(tk.END, output + "\n")
        self.run_output.insert(tk.END, f"[Done] Exit code: {code}\n")
        self.run_output.see(tk.END)
        self.run_output.configure(state=tk.DISABLED)

    def apply_theme(self, config):
        self.config = config
        self.editor.configure(
            bg=config.get("editor_bg", config["bg_color"]),
            fg=config.get("editor_fg", config["fg_color"]),
            insertbackground=config["cursor_color"],
            font=(config["font_family"], config["font_size"]),
        )
        self.line_numbers.configure(
            bg=config.get("editor_line_bg", "#1a1a1a"),
            fg=config.get("editor_line_fg", "#555555"),
            font=(config["font_family"], config["font_size"]),
        )
        self.configure(bg=config["bg_color"])
        self._syntax_highlight()


# ─── AI Chat Tab ─────────────────────────────────────────────────────────────

class AITab(tk.Frame):
    """AI assistant chat tab with support for Ollama and OpenAI-compatible APIs."""

    def __init__(self, parent, config, status_callback=None, ai_engine=None):
        super().__init__(parent)
        self.config = config
        self.status_callback = status_callback
        self.ai_engine = ai_engine
        self.chat_history = load_ai_history()
        self.is_generating = False
        self._build_ui()
        self._restore_chat()

    def _build_ui(self):
        self.configure(bg=self.config["bg_color"])

        # Top bar with AI settings
        top_bar = tk.Frame(self, bg="#111111")
        top_bar.pack(fill=tk.X, padx=2, pady=2)

        tk.Label(top_bar, text="🤖 AI Chat", bg="#111111", fg=self.config["fg_color"],
                 font=("Consolas", 11, "bold")).pack(side=tk.LEFT, padx=8)

        tk.Label(top_bar, text="Provider:", bg="#111111", fg="#888888",
                 font=("Consolas", 9)).pack(side=tk.LEFT, padx=(20, 4))
        self.provider_var = tk.StringVar(value=self.config.get("ai_provider", "ollama"))
        self.provider_menu = ttk.Combobox(top_bar, textvariable=self.provider_var,
                                          values=["ollama", "openai", "lmstudio", "custom"], width=10, state="readonly")
        self.provider_menu.pack(side=tk.LEFT, padx=2)

        # Model lists per provider
        self._model_lists = {
            "ollama": ["llama3", "llama3.1", "llama3.2", "llama3.3", "llama2",
                       "codellama", "mistral", "mixtral", "phi3", "phi4",
                       "gemma", "gemma2", "qwen2.5", "deepseek-r1", "deepseek-coder-v2",
                       "command-r", "starcoder2", "neural-chat", "vicuna"],
            "openai": ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano",
                       "gpt-4-turbo", "gpt-4", "gpt-3.5-turbo",
                       "o1", "o1-mini", "o1-preview", "o3", "o3-mini", "o4-mini",
                       "chatgpt-4o-latest"],
            "lmstudio": [],
            "custom": [],
        }
        self._url_lists = {
            "ollama": ["http://localhost:11434"],
            "openai": ["https://api.openai.com/v1"],
            "lmstudio": ["http://localhost:1234"],
            "custom": ["http://localhost:11434", "https://api.openai.com/v1",
                       "https://api.anthropic.com/v1", "https://openrouter.ai/api/v1",
                       "https://api.groq.com/openai/v1", "https://api.together.xyz/v1",
                       "https://api.mistral.ai/v1", "https://api.deepseek.com/v1"],
        }

        tk.Label(top_bar, text="Model:", bg="#111111", fg="#888888",
                 font=("Consolas", 9)).pack(side=tk.LEFT, padx=(10, 4))
        self.model_var = tk.StringVar(value=self.config.get("ai_model", "llama3"))
        provider = self.config.get("ai_provider", "ollama")
        self.model_entry = ttk.Combobox(top_bar, textvariable=self.model_var,
                                        values=self._model_lists.get(provider, []),
                                        width=20)
        self.model_entry.pack(side=tk.LEFT, padx=2)

        tk.Label(top_bar, text="URL:", bg="#111111", fg="#888888",
                 font=("Consolas", 9)).pack(side=tk.LEFT, padx=(10, 4))
        self.url_var = tk.StringVar(value=self.config.get("ai_base_url", "http://localhost:11434"))
        self.url_entry = ttk.Combobox(top_bar, textvariable=self.url_var,
                                      values=self._url_lists.get(provider, []),
                                      width=32)
        self.url_entry.pack(side=tk.LEFT, padx=2)

        tk.Button(top_bar, text="💾 Save AI Config", bg="#003300", fg="#00ff41",
                  font=("Consolas", 9, "bold"), relief=tk.FLAT,
                  command=self._save_ai_config).pack(side=tk.RIGHT, padx=4)

        tk.Button(top_bar, text="� Detect", bg="#1a1a3a", fg="#8888ff",
                  font=("Consolas", 9, "bold"), relief=tk.FLAT,
                  command=self._auto_detect_models).pack(side=tk.RIGHT, padx=4)

        tk.Button(top_bar, text="�🗑 Clear", bg="#330000", fg="#ff4444",
                  font=("Consolas", 9, "bold"), relief=tk.FLAT,
                  command=self._clear_chat).pack(side=tk.RIGHT, padx=4)

        # API key row
        self.key_frame = tk.Frame(self, bg="#111111")
        tk.Label(self.key_frame, text="API Key:", bg="#111111", fg="#888888",
                 font=("Consolas", 9)).pack(side=tk.LEFT, padx=(8, 4))
        self.key_var = tk.StringVar(value=self.config.get("ai_api_key", ""))
        self.key_entry = tk.Entry(self.key_frame, textvariable=self.key_var, bg="#1a1a1a",
                                  fg=self.config["fg_color"], insertbackground=self.config["fg_color"],
                                  font=("Consolas", 9), width=50, show="•")
        self.key_entry.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)

        self.provider_menu.bind("<<ComboboxSelected>>", self._on_provider_change)
        # Also bind model/url changes to auto-save
        self.model_entry.bind("<<ComboboxSelected>>", lambda e: self._save_ai_config())
        self.model_entry.bind("<FocusOut>", lambda e: self._save_ai_config())
        self.url_entry.bind("<<ComboboxSelected>>", lambda e: self._save_ai_config())
        self.url_entry.bind("<FocusOut>", lambda e: self._save_ai_config())
        self.key_entry.bind("<FocusOut>", lambda e: self._save_ai_config())

        # Chat display
        self.chat_display = tk.Text(
            self, bg=self.config["bg_color"], fg=self.config["fg_color"],
            font=(self.config["font_family"], self.config["font_size"]),
            wrap=tk.WORD, borderwidth=0, highlightthickness=0,
            padx=10, pady=10, state=tk.DISABLED,
        )
        self.chat_display.pack(fill=tk.BOTH, expand=True)

        self._update_key_visibility()

        self.chat_display.tag_configure("user_label", foreground="#00ff41",
                                        font=(self.config["font_family"], self.config["font_size"], "bold"))
        self.chat_display.tag_configure("ai_label", foreground="#ff00ff",
                                        font=(self.config["font_family"], self.config["font_size"], "bold"))
        self.chat_display.tag_configure("user_msg", foreground=self.config["fg_color"])
        self.chat_display.tag_configure("ai_msg", foreground="#cccccc")
        self.chat_display.tag_configure("error", foreground="#ff4444")
        self.chat_display.tag_configure("system", foreground="#555555")
        self.chat_display.tag_configure("separator", foreground="#333333")

        # Input area
        input_frame = tk.Frame(self, bg="#111111")
        input_frame.pack(fill=tk.X, padx=2, pady=2)

        self.input_text = tk.Text(
            input_frame, height=3, bg="#1a1a1a", fg=self.config["fg_color"],
            insertbackground=self.config["cursor_color"],
            font=(self.config["font_family"], self.config["font_size"]),
            wrap=tk.WORD, borderwidth=0, highlightthickness=1,
            highlightcolor=self.config["fg_color"], padx=8, pady=6,
        )
        self.input_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(4, 2), pady=4)
        self.input_text.bind("<Return>", self._on_send)
        self.input_text.bind("<Shift-Return>", lambda e: None)

        self.send_btn = tk.Button(
            input_frame, text="  ▶ Send  ", bg="#003300", fg="#00ff41",
            font=("Consolas", 11, "bold"), relief=tk.FLAT,
            activebackground="#005500", command=self._send_message,
        )
        self.send_btn.pack(side=tk.RIGHT, padx=4, pady=4, fill=tk.Y)

    def _update_key_visibility(self):
        provider = self.provider_var.get()
        if provider in ("openai", "custom"):
            self.key_frame.pack(fill=tk.X, padx=2, pady=(0, 2), before=self.chat_display)
        else:
            self.key_frame.pack_forget()

    def _detect_ollama_models(self):
        """Query Ollama API for locally installed models."""
        try:
            req = urllib.request.Request("http://localhost:11434/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            models = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
            return models
        except Exception:
            return []

    def _detect_lmstudio_models(self):
        """Query LM Studio API for loaded models."""
        try:
            req = urllib.request.Request("http://localhost:1234/v1/models", method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            models = [m.get("id", "") for m in data.get("data", []) if m.get("id")]
            return models
        except Exception:
            return []

    def _detect_running_services(self):
        """Check which local AI services are currently running."""
        services = {}
        # Check Ollama
        try:
            req = urllib.request.Request("http://localhost:11434/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            models = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
            if models:
                services["ollama"] = models
        except Exception:
            pass
        # Check LM Studio
        try:
            req = urllib.request.Request("http://localhost:1234/v1/models", method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            models = [m.get("id", "") for m in data.get("data", []) if m.get("id")]
            if models:
                services["lmstudio"] = models
        except Exception:
            pass
        return services

    def _auto_detect_models(self):
        """Auto-detect local AI models in a background thread."""
        provider = self.provider_var.get()

        def _worker():
            if provider == "ollama":
                models = self._detect_ollama_models()
                if models:
                    self.after(0, lambda: self._apply_detected_models("ollama", models))
                else:
                    self.after(0, lambda: messagebox.showinfo("AI Detect",
                        "Ollama not running or no models installed.\n\n"
                        "Install models with: ollama pull llama3"))
            elif provider == "lmstudio":
                models = self._detect_lmstudio_models()
                if models:
                    self.after(0, lambda: self._apply_detected_models("lmstudio", models))
                else:
                    self.after(0, lambda: messagebox.showinfo("AI Detect",
                        "LM Studio not running or no models loaded.\n\n"
                        "Start LM Studio and load a model first."))
            else:
                # Scan all local services
                services = self._detect_running_services()
                self.after(0, lambda: self._show_detected_services(services))

        threading.Thread(target=_worker, daemon=True).start()

    def _apply_detected_models(self, provider, models, silent=False):
        """Apply detected models to the dropdown."""
        self._model_lists[provider] = models
        current_provider = self.provider_var.get()
        if current_provider == provider:
            self.model_entry.configure(values=models)
            if models and self.model_var.get() not in models:
                self.model_var.set(models[0])
            self._save_ai_config()
        if not silent:
            messagebox.showinfo("AI Detect",
                f"Found {len(models)} model(s) for {provider}:\n\n" +
                "\n".join(f"  • {m}" for m in models[:15]) +
                (f"\n  ... and {len(models)-15} more" if len(models) > 15 else ""))

    def _show_detected_services(self, services):
        """Show all detected local AI services and let user pick one."""
        if not services:
            messagebox.showinfo("AI Detect",
                "No local AI services detected.\n\n"
                "Supported services:\n"
                "  • Ollama (localhost:11434)\n"
                "  • LM Studio (localhost:1234)\n\n"
                "Make sure the service is running.")
            return
        msg = "Detected local AI services:\n\n"
        for svc, models in services.items():
            msg += f"▶ {svc} — {len(models)} model(s):\n"
            for m in models[:5]:
                msg += f"    • {m}\n"
            if len(models) > 5:
                msg += f"    ... and {len(models)-5} more\n"
            msg += "\n"
        # Auto-switch to first detected service
        first_svc = list(services.keys())[0]
        first_models = services[first_svc]
        self._model_lists[first_svc] = first_models
        self.provider_var.set(first_svc)
        self._on_provider_change()
        self.model_entry.configure(values=first_models)
        if first_models:
            self.model_var.set(first_models[0])
        self._save_ai_config()
        msg += f"Auto-selected: {first_svc} → {first_models[0] if first_models else 'none'}"
        messagebox.showinfo("AI Detect", msg)

    def _on_provider_change(self, event=None):
        provider = self.provider_var.get()
        self._update_key_visibility()

        # Update dropdowns and defaults based on provider
        self.model_entry.configure(values=self._model_lists.get(provider, []))
        self.url_entry.configure(values=self._url_lists.get(provider, []))

        if provider == "ollama":
            self.url_var.set("http://localhost:11434")
            current_model = self.model_var.get()
            if current_model not in self._model_lists["ollama"]:
                self.model_var.set("llama3")
            # Auto-detect Ollama models in background (silent)
            def _detect_ollama():
                models = self._detect_ollama_models()
                if models:
                    self.after(0, lambda: self._apply_detected_models("ollama", models, silent=True))
            threading.Thread(target=_detect_ollama, daemon=True).start()
        elif provider == "openai":
            self.url_var.set("https://api.openai.com/v1")
            current_model = self.model_var.get()
            if current_model not in self._model_lists["openai"]:
                self.model_var.set("gpt-4o-mini")
        elif provider == "lmstudio":
            self.url_var.set("http://localhost:1234")
            # Auto-detect LM Studio models in background (silent)
            def _detect():
                models = self._detect_lmstudio_models()
                if models:
                    self.after(0, lambda: self._apply_detected_models("lmstudio", models, silent=True))
            threading.Thread(target=_detect, daemon=True).start()
        elif provider == "custom":
            # Don't change URL/model for custom - let user set it
            pass

        self._save_ai_config()

    def _save_ai_config(self):
        """Save AI settings to config and update the shared engine."""
        self.config["ai_provider"] = self.provider_var.get()
        self.config["ai_model"] = self.model_var.get()
        self.config["ai_base_url"] = self.url_var.get()
        self.config["ai_api_key"] = self.key_var.get()
        save_config(self.config)
        # Update the shared AI engine
        if self.ai_engine:
            self.ai_engine.config = self.config

    def _restore_chat(self):
        self.chat_display.configure(state=tk.NORMAL)
        if self.chat_history:
            for msg in self.chat_history:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role == "user":
                    self.chat_display.insert(tk.END, "\n ▶ You:\n", "user_label")
                    self.chat_display.insert(tk.END, f" {content}\n", "user_msg")
                elif role == "assistant":
                    self.chat_display.insert(tk.END, "\n 🤖 Neko AI:\n", "ai_label")
                    self.chat_display.insert(tk.END, f" {content}\n", "ai_msg")
                self.chat_display.insert(tk.END, " ─" * 35 + "\n", "separator")
            self.chat_display.see(tk.END)
        else:
            self.chat_display.insert(tk.END, "\n  🤖 Welcome to Neko AI Chat!\n\n", "ai_label")
            self.chat_display.insert(tk.END, "  Configure your AI provider above, then start chatting.\n", "system")
            self.chat_display.insert(tk.END, "  Supports: Ollama (local), OpenAI API, or any compatible API.\n\n", "system")
            self.chat_display.insert(tk.END, "  For Ollama: Install from ollama.com, run 'ollama pull llama3'\n", "system")
            self.chat_display.insert(tk.END, "  For OpenAI: Select 'openai', set your API key and model.\n", "system")
            self.chat_display.insert(tk.END, "  TIP: Type 'ai <question>' in any Terminal tab for quick AI!\n\n", "system")
        self.chat_display.configure(state=tk.DISABLED)

    def _on_send(self, event):
        if not event.state & 0x1:
            self._send_message()
            return "break"

    def _send_message(self):
        if self.is_generating:
            return
        message = self.input_text.get("1.0", "end-1c").strip()
        if not message:
            return
        self.input_text.delete("1.0", tk.END)

        # Show user message
        self.chat_display.configure(state=tk.NORMAL)
        self.chat_display.insert(tk.END, "\n ▶ You:\n", "user_label")
        self.chat_display.insert(tk.END, f" {message}\n", "user_msg")
        self.chat_display.insert(tk.END, " ─" * 35 + "\n", "separator")
        self.chat_display.see(tk.END)
        self.chat_display.configure(state=tk.DISABLED)

        self.chat_history.append({"role": "user", "content": message})
        self._save_ai_config()

        # Show loading
        self.chat_display.configure(state=tk.NORMAL)
        self.chat_display.insert(tk.END, "\n 🤖 Neko AI:\n", "ai_label")
        loading_mark = self.chat_display.index(tk.END)
        self.chat_display.insert(tk.END, " ⏳ Thinking...\n", "system")
        self.chat_display.see(tk.END)
        self.chat_display.configure(state=tk.DISABLED)

        self.is_generating = True
        self.send_btn.configure(text="  ⏳ ...  ", state=tk.DISABLED)
        if self.status_callback:
            self.status_callback("AI: Generating response...")

        def _worker():
            try:
                response = self.ai_engine.call(message, self.chat_history)
                self.after(0, lambda: self._show_response(response, loading_mark))
            except Exception as e:
                self.after(0, lambda: self._show_response(f"[Error] {e}", loading_mark, is_error=True))
        threading.Thread(target=_worker, daemon=True).start()

    def _show_response(self, response, loading_mark, is_error=False):
        self.chat_display.configure(state=tk.NORMAL)
        # Remove "Thinking..."
        try:
            self.chat_display.delete(loading_mark + " - 1 lines", loading_mark + " lineend + 1c")
        except Exception:
            pass

        if is_error:
            self.chat_display.insert(tk.END, f" {response}\n", "error")
        else:
            self.chat_display.insert(tk.END, f" {response}\n", "ai_msg")
            self.chat_history.append({"role": "assistant", "content": response})
            save_ai_history(self.chat_history)

        self.chat_display.insert(tk.END, " ─" * 35 + "\n", "separator")
        self.chat_display.see(tk.END)
        self.chat_display.configure(state=tk.DISABLED)

        self.is_generating = False
        self.send_btn.configure(text="  ▶ Send  ", state=tk.NORMAL)
        if self.status_callback:
            self.status_callback("AI: Ready")

    def _clear_chat(self):
        if messagebox.askyesno("Clear Chat", "Clear all AI chat history?"):
            self.chat_history = []
            save_ai_history([])
            self.chat_display.configure(state=tk.NORMAL)
            self.chat_display.delete("1.0", tk.END)
            self.chat_display.insert(tk.END, "\n  🤖 Chat cleared. Start fresh!\n\n", "ai_label")
            self.chat_display.configure(state=tk.DISABLED)

    def apply_theme(self, config):
        self.config = config
        self.chat_display.configure(
            bg=config["bg_color"], fg=config["fg_color"],
            font=(config["font_family"], config["font_size"]),
        )
        self.input_text.configure(
            bg="#1a1a1a", fg=config["fg_color"],
            insertbackground=config["cursor_color"],
            font=(config["font_family"], config["font_size"]),
            highlightcolor=config["fg_color"],
        )
        self.chat_display.tag_configure("user_msg", foreground=config["fg_color"])
        self.chat_display.tag_configure("user_label", foreground=config["prompt_color"],
                                        font=(config["font_family"], config["font_size"], "bold"))
        self.configure(bg=config["bg_color"])


# ─── Settings Window ────────────────────────────────────────────────────────

class SettingsWindow(tk.Toplevel):
    """GUI settings dialog for customizing colors, fonts, themes, and backgrounds."""

    CARD_BG = "#181818"
    SECTION_FG = "#00ff41"
    LABEL_FG = "#cccccc"
    SUBTLE_FG = "#777777"
    ACCENT = "#00ff41"
    DANGER = "#ff4444"
    WARN = "#ffaa00"
    BG = "#0d0d0d"

    def __init__(self, parent, config, apply_callback):
        super().__init__(parent)
        self.config = dict(config)
        self.apply_callback = apply_callback
        self.title("⚙ Neko Terminal Settings")
        self.geometry("620x920")
        self.configure(bg=self.BG)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self._build_ui()

    def _section_card(self, parent, title, icon=""):
        """Create a styled section card with title header."""
        card = tk.Frame(parent, bg=self.CARD_BG, highlightbackground="#2a2a2a",
                        highlightthickness=1, padx=12, pady=8)
        card.pack(fill=tk.X, pady=(8, 0), padx=4)
        header = tk.Frame(card, bg=self.CARD_BG)
        header.pack(fill=tk.X, pady=(0, 6))
        tk.Label(header, text=f"{icon}  {title}", bg=self.CARD_BG, fg=self.SECTION_FG,
                 font=("Consolas", 11, "bold")).pack(side=tk.LEFT)
        # Subtle separator line
        sep = tk.Frame(card, bg="#2a2a2a", height=1)
        sep.pack(fill=tk.X, pady=(0, 6))
        return card

    def _styled_btn(self, parent, text, bg_color, fg_color, command, bold=False):
        """Create a hover-effect button."""
        w = "bold" if bold else "normal"
        btn = tk.Button(parent, text=text, bg=bg_color, fg=fg_color,
                        font=("Consolas", 10, w), relief=tk.FLAT, padx=10, pady=4,
                        activebackground=self._lighten(bg_color), cursor="hand2",
                        command=command)
        btn.bind("<Enter>", lambda e: btn.configure(bg=self._lighten(bg_color)))
        btn.bind("<Leave>", lambda e: btn.configure(bg=bg_color))
        return btn

    @staticmethod
    def _lighten(hex_color, amount=30):
        """Lighten a hex color slightly for hover effects."""
        try:
            hex_color = hex_color.lstrip("#")
            r = min(255, int(hex_color[0:2], 16) + amount)
            g = min(255, int(hex_color[2:4], 16) + amount)
            b = min(255, int(hex_color[4:6], 16) + amount)
            return f"#{r:02x}{g:02x}{b:02x}"
        except Exception:
            return "#333333"

    def _build_ui(self):
        # Title bar
        title_bar = tk.Frame(self, bg="#0a0a0a", height=50)
        title_bar.pack(fill=tk.X)
        title_bar.pack_propagate(False)
        tk.Label(title_bar, text="⚙", bg="#0a0a0a", fg=self.ACCENT,
                 font=("Consolas", 22)).pack(side=tk.LEFT, padx=(15, 5))
        tk.Label(title_bar, text="NEKO SETTINGS", bg="#0a0a0a", fg=self.ACCENT,
                 font=("Consolas", 16, "bold")).pack(side=tk.LEFT)
        tk.Label(title_bar, text="  Customize your terminal", bg="#0a0a0a", fg=self.SUBTLE_FG,
                 font=("Consolas", 9)).pack(side=tk.LEFT, padx=(8, 0))

        # Scrollable content area
        canvas = tk.Canvas(self, bg=self.BG, highlightthickness=0)
        scrollbar = tk.Scrollbar(self, orient=tk.VERTICAL, command=canvas.yview,
                                 bg="#1a1a1a", troughcolor=self.BG)
        content = tk.Frame(canvas, bg=self.BG)
        content.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=content, anchor="nw", width=580)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=6)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        self.bind("<Destroy>", lambda e: canvas.unbind_all("<MouseWheel>"))

        # ═══ THEME PRESETS ═══
        card = self._section_card(content, "THEME PRESETS", "🎨")
        presets_frame = tk.Frame(card, bg=self.CARD_BG)
        presets_frame.pack(fill=tk.X, pady=4)
        for i, (name, preset) in enumerate(THEME_PRESETS.items()):
            btn = tk.Button(presets_frame, text=f"● {name}", bg="#222222", fg=preset["fg_color"],
                            font=("Consolas", 9, "bold"), relief=tk.FLAT, padx=8, pady=4,
                            cursor="hand2", activebackground="#3a3a3a",
                            command=lambda p=preset, n=name: self._apply_preset(p, n))
            btn.grid(row=i // 3, column=i % 3, padx=3, pady=3, sticky="ew")
        for c in range(3):
            presets_frame.columnconfigure(c, weight=1)

        # ═══ TABS ═══
        card = self._section_card(content, "VISIBLE TABS", "📑")
        self.tab_vars = {}
        for tab_key, tab_label in [("show_ssh_tab", "🔗 SSH"), ("show_editor_tab", "📝 Editor"), ("show_ai_tab", "🤖 AI")]:
            row = tk.Frame(card, bg=self.CARD_BG)
            row.pack(fill=tk.X, pady=3)
            var = tk.BooleanVar(value=self.config.get(tab_key, True))
            self.tab_vars[tab_key] = var
            cb = tk.Checkbutton(row, text=f"  {tab_label}", variable=var,
                                bg=self.CARD_BG, fg=self.LABEL_FG, selectcolor="#1a1a1a",
                                activebackground=self.CARD_BG, activeforeground=self.ACCENT,
                                font=("Consolas", 10), anchor="w", cursor="hand2")
            cb.pack(side=tk.LEFT, padx=4)

        # ═══ COLORS ═══
        card = self._section_card(content, "COLORS", "🎨")
        color_options = [
            ("Background", "bg_color"), ("Text", "fg_color"),
            ("Prompt", "prompt_color"), ("Cursor", "cursor_color"),
            ("Selection", "selection_bg"), ("Editor BG", "editor_bg"),
            ("Editor Text", "editor_fg"),
        ]
        self.color_previews = {}
        for label_text, key in color_options:
            row = tk.Frame(card, bg=self.CARD_BG)
            row.pack(fill=tk.X, pady=2)
            tk.Label(row, text=label_text, bg=self.CARD_BG, fg=self.LABEL_FG,
                     font=("Consolas", 10), width=14, anchor="w").pack(side=tk.LEFT)
            preview = tk.Frame(row, bg=self.config.get(key, "#000000"), width=60, height=20,
                               highlightbackground="#444444", highlightthickness=1)
            preview.pack(side=tk.LEFT, padx=6)
            preview.pack_propagate(False)
            self.color_previews[key] = preview
            self._styled_btn(row, "Pick", "#222222", self.ACCENT,
                             lambda k=key: self._pick_color(k)).pack(side=tk.LEFT, padx=2)
            # Show hex value
            hex_lbl = tk.Label(row, text=self.config.get(key, ""), bg=self.CARD_BG,
                               fg=self.SUBTLE_FG, font=("Consolas", 8))
            hex_lbl.pack(side=tk.LEFT, padx=4)

        # ═══ FONT ═══
        card = self._section_card(content, "FONT", "🔤")
        font_row = tk.Frame(card, bg=self.CARD_BG)
        font_row.pack(fill=tk.X, pady=4)
        tk.Label(font_row, text="Family", bg=self.CARD_BG, fg=self.LABEL_FG,
                 font=("Consolas", 10), width=14, anchor="w").pack(side=tk.LEFT)
        self.font_var = tk.StringVar(value=self.config["font_family"])
        font_choices = ["Consolas", "Courier New", "Fira Code", "JetBrains Mono",
                        "Source Code Pro", "Cascadia Code", "monospace", "Lucida Console"]
        ttk.Combobox(font_row, textvariable=self.font_var, values=font_choices,
                     width=22, state="readonly").pack(side=tk.LEFT, padx=5)

        size_row = tk.Frame(card, bg=self.CARD_BG)
        size_row.pack(fill=tk.X, pady=4)
        tk.Label(size_row, text="Size", bg=self.CARD_BG, fg=self.LABEL_FG,
                 font=("Consolas", 10), width=14, anchor="w").pack(side=tk.LEFT)
        self.size_var = tk.IntVar(value=self.config["font_size"])
        tk.Spinbox(size_row, from_=8, to=28, textvariable=self.size_var,
                   width=5, bg="#222222", fg=self.ACCENT, font=("Consolas", 10),
                   buttonbackground="#333333", relief=tk.FLAT).pack(side=tk.LEFT, padx=5)
        # Font preview
        preview_row = tk.Frame(card, bg="#222222", padx=10, pady=6)
        preview_row.pack(fill=tk.X, pady=(6, 2))
        tk.Label(preview_row, text="Preview:  neko@terminal:~$  hello world",
                 bg="#222222", fg=self.ACCENT,
                 font=(self.config["font_family"], self.config["font_size"])).pack(anchor="w")

        # ═══ UPDATES ═══
        card = self._section_card(content, "UPDATES", "🔄")

        # Current version display
        ver_row = tk.Frame(card, bg=self.CARD_BG)
        ver_row.pack(fill=tk.X, pady=4)
        tk.Label(ver_row, text="Current Version", bg=self.CARD_BG, fg=self.LABEL_FG,
                 font=("Consolas", 10), width=16, anchor="w").pack(side=tk.LEFT)
        self._ver_badge = tk.Label(ver_row, text=f"  v{APP_VERSION}  ", bg="#003300",
                                   fg="#00ff41", font=("Consolas", 10, "bold"),
                                   padx=8, pady=2)
        self._ver_badge.pack(side=tk.LEFT, padx=4)
        tk.Label(ver_row, text=f"  {GITHUB_OWNER}/{GITHUB_REPO}", bg=self.CARD_BG,
                 fg=self.SUBTLE_FG, font=("Consolas", 8)).pack(side=tk.LEFT, padx=4)

        # Status & buttons row
        update_row = tk.Frame(card, bg=self.CARD_BG)
        update_row.pack(fill=tk.X, pady=4)

        self._update_status = tk.Label(update_row, text="Click to check for updates",
                                       bg=self.CARD_BG, fg=self.SUBTLE_FG,
                                       font=("Consolas", 9), anchor="w")
        self._update_status.pack(side=tk.LEFT, padx=(0, 10), fill=tk.X, expand=True)

        self._download_btn = self._styled_btn(update_row, "⬇ Download & Install",
                                              "#003355", "#00bbff",
                                              self._do_download_update, bold=True)
        # Hidden until update is available
        self._download_btn.pack(side=tk.RIGHT, padx=4)
        self._download_btn.pack_forget()

        self._check_btn = self._styled_btn(update_row, "🔄 Check for Updates",
                                           "#1a1a2e", "#8888ff",
                                           self._do_check_update, bold=True)
        self._check_btn.pack(side=tk.RIGHT, padx=4)

        # Release notes area (hidden by default)
        self._notes_frame = tk.Frame(card, bg="#111111", highlightbackground="#2a2a2a",
                                      highlightthickness=1)
        self._notes_text = tk.Text(self._notes_frame, height=5, bg="#111111",
                                    fg="#aaaaaa", font=("Consolas", 9), wrap=tk.WORD,
                                    borderwidth=0, padx=8, pady=6, state=tk.DISABLED)
        self._notes_text.pack(fill=tk.BOTH, expand=True)
        # _notes_frame is packed only when there are notes to show

        # Store updater instance for this settings window
        self._updater = Updater()

        # ═══ ACTION BUTTONS ═══
        btn_frame = tk.Frame(content, bg=self.BG)
        btn_frame.pack(fill=tk.X, pady=16, padx=4)

        apply_btn = tk.Button(btn_frame, text="  ✓  Apply & Save  ", bg="#003300", fg=self.ACCENT,
                              font=("Consolas", 12, "bold"), relief=tk.FLAT, padx=20, pady=8,
                              activebackground="#005500", cursor="hand2", command=self._apply)
        apply_btn.pack(side=tk.LEFT, padx=6)
        apply_btn.bind("<Enter>", lambda e: apply_btn.configure(bg="#005500"))
        apply_btn.bind("<Leave>", lambda e: apply_btn.configure(bg="#003300"))

        cancel_btn = tk.Button(btn_frame, text="  ✕  Cancel  ", bg="#330000", fg=self.DANGER,
                               font=("Consolas", 12, "bold"), relief=tk.FLAT, padx=20, pady=8,
                               activebackground="#550000", cursor="hand2", command=self.destroy)
        cancel_btn.pack(side=tk.LEFT, padx=6)
        cancel_btn.bind("<Enter>", lambda e: cancel_btn.configure(bg="#550000"))
        cancel_btn.bind("<Leave>", lambda e: cancel_btn.configure(bg="#330000"))

        reset_btn = tk.Button(btn_frame, text="  ↺  Reset  ", bg="#1a1a1a", fg=self.WARN,
                              font=("Consolas", 12, "bold"), relief=tk.FLAT, padx=20, pady=8,
                              activebackground="#333333", cursor="hand2", command=self._reset)
        reset_btn.pack(side=tk.LEFT, padx=6)
        reset_btn.bind("<Enter>", lambda e: reset_btn.configure(bg="#333333"))
        reset_btn.bind("<Leave>", lambda e: reset_btn.configure(bg="#1a1a1a"))

    def _pick_color(self, key):
        color = colorchooser.askcolor(initialcolor=self.config.get(key, "#000000"), title=f"Choose {key}")
        if color[1]:
            self.config[key] = color[1]
            self.color_previews[key].configure(bg=color[1])

    def _apply_preset(self, preset, name):
        for k, v in preset.items():
            self.config[k] = v
            if k in self.color_previews:
                self.color_previews[k].configure(bg=v)

    def _apply(self):
        self.config["font_family"] = self.font_var.get()
        self.config["font_size"] = self.size_var.get()
        for key, var in self.tab_vars.items():
            self.config[key] = var.get()
        self.apply_callback(self.config)
        self.destroy()

    def _reset(self):
        self.config = dict(DEFAULT_CONFIG)
        for k, preview in self.color_previews.items():
            preview.configure(bg=self.config.get(k, "#000000"))
        self.font_var.set(self.config["font_family"])
        self.size_var.set(self.config["font_size"])
        for key, var in self.tab_vars.items():
            var.set(self.config.get(key, True))

    def _do_check_update(self):
        """Check GitHub for updates in a background thread."""
        self._check_btn.configure(state=tk.DISABLED, text="🔄 Checking...")
        self._update_status.configure(text="Contacting GitHub...", fg="#8888ff")
        self._download_btn.pack_forget()
        self._notes_frame.pack_forget()

        def _worker():
            try:
                has_update, tag, notes = self._updater.check_for_updates()
                self.after(0, lambda: self._show_check_result(has_update, tag, notes))
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    self.after(0, lambda: self._show_check_error(
                        "No releases found yet. Publish a release on GitHub first."))
                else:
                    self.after(0, lambda: self._show_check_error(f"GitHub API error: {e}"))
            except Exception as e:
                self.after(0, lambda: self._show_check_error(str(e)))

        threading.Thread(target=_worker, daemon=True).start()

    def _show_check_result(self, has_update, tag, notes):
        """Display the result of the update check."""
        self._check_btn.configure(state=tk.NORMAL, text="🔄 Check for Updates")

        if has_update:
            self._update_status.configure(
                text=f"⬆ Update available: {tag}", fg="#00ff41")
            self._ver_badge.configure(bg="#333300", fg="#ffaa00",
                                      text=f"  v{APP_VERSION} → {tag}  ")
            # Show download button
            self._download_btn.pack(side=tk.RIGHT, padx=4)
            # Show release notes
            if notes:
                self._notes_frame.pack(fill=tk.X, pady=(6, 2))
                self._notes_text.configure(state=tk.NORMAL)
                self._notes_text.delete("1.0", tk.END)
                self._notes_text.insert("1.0", f"📋 Release Notes ({tag}):\n\n{notes}")
                self._notes_text.configure(state=tk.DISABLED)
        else:
            self._update_status.configure(
                text=f"✓ You're up to date! (latest: {tag})", fg="#00ff41")
            self._ver_badge.configure(bg="#003300", fg="#00ff41",
                                      text=f"  v{APP_VERSION} ✓  ")

    def _show_check_error(self, error_msg):
        """Display an error from the update check."""
        self._check_btn.configure(state=tk.NORMAL, text="🔄 Check for Updates")
        self._update_status.configure(text=f"✕ {error_msg}", fg="#ff4444")

    def _do_download_update(self):
        """Download and install the update in a background thread."""
        if not messagebox.askyesno("Update Neko Terminal",
                f"Download and install {self._updater.latest_tag}?\n\n"
                f"A backup of your current version will be created.\n"
                f"You'll need to restart Neko Terminal after the update."):
            return

        self._download_btn.configure(state=tk.DISABLED, text="⬇ Downloading...")
        self._check_btn.configure(state=tk.DISABLED)

        def _progress(msg):
            self.after(0, lambda: self._update_status.configure(
                text=f"⏳ {msg}", fg="#ffaa00"))

        def _worker():
            try:
                self._updater.download_and_apply(progress_callback=_progress)
                self.after(0, self._on_update_success)
            except Exception as e:
                self.after(0, lambda: self._on_update_error(str(e)))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_update_success(self):
        """Handle successful update installation."""
        self._update_status.configure(
            text="✓ Update installed! Restart to apply.", fg="#00ff41")
        self._download_btn.configure(text="✓ Installed", state=tk.DISABLED)
        self._ver_badge.configure(bg="#003300", fg="#00ff41",
                                  text=f"  {self._updater.latest_tag} (restart)  ")

        if IS_FROZEN:
            restart = messagebox.askyesno("Update Complete",
                f"Neko Terminal {self._updater.latest_tag} is ready!\n\n"
                f"The app will close and reopen with the new version.\n"
                f"A backup of the old version will be kept.\n\n"
                f"Restart now?")
            if restart:
                # Launch the batch updater script, then exit
                updater_bat = getattr(self._updater, '_updater_bat', None)
                if updater_bat and os.path.exists(updater_bat):
                    subprocess.Popen(
                        ['cmd', '/c', updater_bat],
                        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
                    )
                self.master.destroy()
        else:
            restart = messagebox.askyesno("Update Complete",
                f"Neko Terminal has been updated to {self._updater.latest_tag}!\n\n"
                f"A backup was saved as neko_terminal.py.bak\n\n"
                f"Restart now to apply the update?")
            if restart:
                python = sys.executable
                script = os.path.abspath(__file__)
                self.master.destroy()
                os.execv(python, [python, script])

    def _on_update_error(self, error_msg):
        """Handle update download/install error."""
        self._update_status.configure(text=f"✕ Update failed", fg="#ff4444")
        self._download_btn.configure(state=tk.NORMAL, text="⬇ Download & Install")
        self._check_btn.configure(state=tk.NORMAL)
        messagebox.showerror("Update Error",
            f"Failed to install update:\n\n{error_msg}")


# ─── Main Application ───────────────────────────────────────────────────────

class NekoTerminal(tk.Tk):
    """Main Neko Terminal application window."""

    def __init__(self):
        super().__init__()
        self.config_data = load_config()
        self.tab_counter = 1

        # Shared AI engine
        self.ai_engine = AIEngine(self.config_data)

        self.title(f"🐱 Neko Terminal v{APP_VERSION}")
        self.geometry(f"{self.config_data['window_width']}x{self.config_data['window_height']}")
        self.configure(bg="#000000")
        self.minsize(800, 500)

        try:
            self.iconbitmap(default="")
        except Exception:
            pass

        self._build_ui()
        self._center_window()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        self.config_data["window_width"] = self.winfo_width()
        self.config_data["window_height"] = self.winfo_height()
        # Clear saved cwd so next launch starts at home
        self.config_data["last_cwd"] = ""
        save_config(self.config_data)
        if hasattr(self, 'terminal_tab'):
            self.terminal_tab._save_state()
        self.destroy()

    def _center_window(self):
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.geometry(f"+{x}+{y}")

    def _build_ui(self):
        # Menu bar
        menu_bar = tk.Frame(self, bg="#0d0d0d", height=32)
        menu_bar.pack(fill=tk.X)
        menu_bar.pack_propagate(False)

        title_lbl = tk.Label(menu_bar, text=f"🐱 NEKO TERMINAL v{APP_VERSION}", bg="#0d0d0d",
                             fg=self.config_data["fg_color"],
                             font=("Consolas", 11, "bold"))
        title_lbl.pack(side=tk.LEFT, padx=10)

        btn_cfg = {"bg": "#0d0d0d", "fg": self.config_data["fg_color"],
                   "font": ("Consolas", 10), "relief": tk.FLAT,
                   "activebackground": "#222222", "padx": 8}

        tk.Button(menu_bar, text="⚙ Settings", command=self._open_settings, **btn_cfg).pack(side=tk.RIGHT, padx=2)
        tk.Button(menu_bar, text="✕ Close Tab", command=self._close_current_tab, **btn_cfg).pack(side=tk.RIGHT, padx=2)
        tk.Button(menu_bar, text="+ New Tab", command=self._add_terminal_tab, **btn_cfg).pack(side=tk.RIGHT, padx=2)

        # Notebook
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Hacker.TNotebook", background="#000000", borderwidth=0)
        style.configure("Hacker.TNotebook.Tab", background="#111111",
                        foreground=self.config_data["fg_color"],
                        font=("Consolas", 10, "bold"), padding=[12, 4])
        style.map("Hacker.TNotebook.Tab",
                  background=[("selected", "#1a1a1a"), ("active", "#222222")],
                  foreground=[("selected", self.config_data["fg_color"])])

        self.notebook = ttk.Notebook(self, style="Hacker.TNotebook")
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # Core tabs
        self.terminal_tab = TerminalTab(self.notebook, self.config_data, self._set_status, self.ai_engine)
        self.notebook.add(self.terminal_tab, text="  ⌨ Terminal  ")

        self.ssh_tab = SSHTab(self.notebook, self.config_data, self._set_status)
        self.editor_tab = EditorTab(self.notebook, self.config_data, self._set_status, self.ai_engine)
        self.ai_tab = AITab(self.notebook, self.config_data, self._set_status, self.ai_engine)

        self._optional_tabs = [
            ("show_ssh_tab", self.ssh_tab, "  🔗 SSH  "),
            ("show_editor_tab", self.editor_tab, "  📝 Editor  "),
            ("show_ai_tab", self.ai_tab, "  🤖 AI  "),
        ]
        for key, tab, label in self._optional_tabs:
            if self.config_data.get(key, True):
                self.notebook.add(tab, text=label)

        self.core_tabs = {self.terminal_tab, self.ssh_tab, self.editor_tab, self.ai_tab}
        self.tab_list = [self.terminal_tab, self.ssh_tab, self.editor_tab, self.ai_tab]

        # Status bar
        self.status_bar = tk.Label(self, text=f"DIR: {os.path.expanduser('~')}",
                                   bg="#0d0d0d", fg="#555555",
                                   font=("Consolas", 9), anchor="w", padx=10)
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)

    def _set_status(self, text):
        self.status_bar.configure(text=text)

    def _open_settings(self):
        SettingsWindow(self, self.config_data, self._apply_settings)

    def _apply_settings(self, new_config):
        self.config_data = new_config
        save_config(new_config)
        # Update shared AI engine
        self.ai_engine.config = new_config

        for tab in self.tab_list:
            tab.apply_theme(new_config)

        # Show/hide optional tabs
        for key, tab, label in self._optional_tabs:
            should_show = new_config.get(key, True)
            try:
                self.notebook.index(tab)
                is_visible = True
            except tk.TclError:
                is_visible = False

            if should_show and not is_visible:
                self.notebook.add(tab, text=label)
            elif not should_show and is_visible:
                self.notebook.forget(tab)

        style = ttk.Style()
        style.configure("Hacker.TNotebook.Tab", foreground=new_config["fg_color"])
        style.map("Hacker.TNotebook.Tab",
                  foreground=[("selected", new_config["fg_color"])])
        self.status_bar.configure(bg="#0d0d0d")

    def _add_terminal_tab(self):
        self.tab_counter += 1
        new_tab = TerminalTab(self.notebook, self.config_data, self._set_status, self.ai_engine)
        self.notebook.add(new_tab, text=f"  ⌨ Term {self.tab_counter}  ")
        self.tab_list.append(new_tab)
        self.notebook.select(new_tab)
        new_tab.after(50, lambda: new_tab.text.focus_set())

    def _close_current_tab(self):
        current = self.notebook.select()
        if not current:
            return
        current_widget = self.nametowidget(current)
        if current_widget in self.core_tabs:
            messagebox.showinfo("Neko Terminal",
                                "Can't close core tabs (Terminal, SSH, Editor, AI).\n"
                                "Only additional terminal tabs can be closed.")
            return
        self.notebook.forget(current)
        if current_widget in self.tab_list:
            self.tab_list.remove(current_widget)
        current_widget.destroy()


# ─── Entry Point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if HAS_CRYPTO:
        if _init_encryption() and not IS_FROZEN:
            _migrate_plaintext_files()
    app = NekoTerminal()
    app.mainloop()
