"""Shared environment utilities for MCP child processes.

Provides common Chrome path discovery and clean environment setup
logic used by mcp_client.py, execute.py, and verify.py child
processes. Eliminates duplication of proxy clearing and conda lib
path configuration across these modules.
"""

from __future__ import annotations

import os
import shutil


def find_chrome_path() -> str | None:
    """Discover Chrome/Chromium executable path.

    Dynamically scans the Playwright cache for any chromium-* directory,
    avoiding hardcoded version-specific paths that break when Playwright
    updates. Falls back to system Chrome via shutil.which().

    Returns:
        Path to Chrome executable, or None if not found.
    """
    playwright_cache = os.path.expanduser("~/.cache/ms-playwright")
    if os.path.isdir(playwright_cache):
        for entry in os.listdir(playwright_cache):
            if entry.startswith("chromium"):
                full_path = os.path.join(playwright_cache, entry)
                # Check for chrome-linux64 or chrome-linux naming patterns
                for subdir in ["chrome-linux64", "chrome-linux"]:
                    candidate = os.path.join(full_path, subdir, "chrome")
                    if os.path.isfile(candidate):
                        return candidate
    # Fallback to system Chrome
    for cmd in ["google-chrome", "chrome", "chromium", "chromium-browser"]:
        path = shutil.which(cmd)
        if path:
            return path
    return None


def build_child_env() -> dict[str, str]:
    """Build clean environment dict for child processes.

    Clears proxy vars (all_proxy, http_proxy, etc.) to prevent
    Playwright browser from going through SOCKS proxy, adds conda
    lib paths to LD_LIBRARY_PATH for Chrome/Chromium dependencies
    (libatk, libgbm, etc.), and sets PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH.
    Also ensures npx/node are in PATH so MCP servers can launch.

    Returns:
        Cleaned environment dict suitable for MCP child processes.
    """
    clean_env = dict(os.environ)
    # Clear proxy vars to avoid Playwright browser using SOCKS proxy
    for key in list(clean_env.keys()):
        if "proxy" in key.lower():
            del clean_env[key]

    # Ensure npx/node are in PATH (MCP servers need npx to launch Playwright MCP)
    npx_path = shutil.which("npx")
    if npx_path:
        npx_dir = os.path.dirname(npx_path)
        current_path = clean_env.get("PATH", "")
        if npx_dir not in current_path:
            clean_env["PATH"] = f"{npx_dir}:{current_path}"

    # Add conda lib path so Chrome/Chromium finds libatk/libgbm etc.
    conda_lib = os.path.join(
        os.path.dirname(os.path.dirname(shutil.which("python") or "")), "lib"
    )
    if os.path.isdir(conda_lib):
        existing_ld = clean_env.get("LD_LIBRARY_PATH", "")
        if conda_lib not in existing_ld:
            clean_env["LD_LIBRARY_PATH"] = f"{conda_lib}:{existing_ld}"
    # Dynamically discover Playwright Chrome path
    chrome_path = find_chrome_path()
    if chrome_path and os.path.isfile(chrome_path):
        clean_env["PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH"] = chrome_path
    return clean_env