"""Custom Verify MCP Server.

Provides verification tools for checking test execution results:
- compare_screenshots: compare expected vs actual screenshots
- check_text_content: check if page text contains expected content
- check_element_exists: check if specific DOM element exists

Uses Python MCP SDK with stdio transport.
"""

from __future__ import annotations

import base64
import difflib
import hashlib
import io
import json
import logging
import re
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

# PIL is optional — used for pixel-level screenshot comparison.
# If unavailable, we fall back to size-only comparison.
try:
    from PIL import Image
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False

logger = logging.getLogger(__name__)


def _check_text_content(page_text: str, expected_text: str) -> str:
    """Check if page text contains the expected text content.

    Performs case-insensitive substring matching, fuzzy matching via
    difflib.SequenceMatcher, and supports comma-separated or multiple
    expected texts. Returns detailed results including match percentage,
    matched excerpts, and closest matches.

    Args:
        page_text: The full text content of the page.
        expected_text: The expected text to search for. Supports
            comma-separated alternatives (e.g. "Login, Sign in, Log in").

    Returns:
        JSON-formatted result string with match_percentage, matched_excerpts,
        and closest_matches fields.
    """
    # Parse comma-separated alternatives
    alternatives = [t.strip() for t in expected_text.split(",") if t.strip()]
    if not alternatives:
        alternatives = [expected_text]

    page_lower = page_text.lower()

    best_match_pct = 0.0
    matched_excerpts: list[str] = []
    closest_matches: list[dict[str, Any]] = []

    for alt in alternatives:
        alt_lower = alt.lower()

        # --- Direct substring match ---
        if alt_lower in page_lower:
            idx = page_lower.find(alt_lower)
            context_start = max(0, idx - 80)
            context_end = min(len(page_text), idx + len(alt) + 80)
            excerpt = page_text[context_start:context_end]
            matched_excerpts.append(excerpt)
            best_match_pct = max(best_match_pct, 1.0)
            # Early exit on perfect match
            if best_match_pct == 1.0:
                return json_result(
                    True,
                    f"Found expected text '{alt}' in page. "
                    f"Context: ...{excerpt}...",
                    confidence=1.0,
                    match_percentage=1.0,
                    matched_excerpts=matched_excerpts,
                    closest_matches=closest_matches,
                )
            continue  # keep checking other alternatives for excerpts

        # --- Fuzzy matching with difflib.SequenceMatcher ---
        # Try against the whole page first for short expectations
        if len(alt) < 50:
            full_ratio = difflib.SequenceMatcher(None, alt_lower, page_lower).ratio()
            if full_ratio > 0.6:
                closest_matches.append({
                    "expected": alt,
                    "similarity": round(full_ratio, 3),
                    "match_type": "full_page_fuzzy",
                })
                best_match_pct = max(best_match_pct, full_ratio)

        # Context-aware: extract page sections that contain partial matches
        # Split page into chunks and find the best-matching chunk
        alt_words = alt_lower.split()
        page_words = page_lower.split()

        # Try word-by-word matching (existing logic as fallback)
        if len(alt_words) > 1:
            matching_words = [w for w in alt_words if w in page_lower]
            word_ratio = len(matching_words) / len(alt_words) if alt_words else 0
            if word_ratio >= 0.5:
                closest_matches.append({
                    "expected": alt,
                    "similarity": round(word_ratio, 3),
                    "match_type": "word_overlap",
                    "matching_words": matching_words,
                    "missing_words": [w for w in alt_words if w not in page_lower],
                })
                best_match_pct = max(best_match_pct, word_ratio)

        # Sliding-window chunk matching for context-aware extraction
        # Find the page chunk that best resembles the expected text
        chunk_size = max(10, len(alt_words) * 2)
        best_chunk_ratio = 0.0
        best_chunk_excerpt = ""
        for i in range(0, len(page_words), max(1, chunk_size // 2)):
            chunk = " ".join(page_words[i:i + chunk_size])
            ratio = difflib.SequenceMatcher(None, alt_lower, chunk).ratio()
            if ratio > best_chunk_ratio:
                best_chunk_ratio = ratio
                # Map word indices back to original text positions
                original_start = _word_offset_to_char(page_text, i)
                original_end = _word_offset_to_char(page_text, min(i + chunk_size, len(page_words)))
                best_chunk_excerpt = page_text[original_start:original_end]

        if best_chunk_ratio > 0.4:
            closest_matches.append({
                "expected": alt,
                "similarity": round(best_chunk_ratio, 3),
                "match_type": "chunk_fuzzy",
                "excerpt": best_chunk_excerpt[:300],
            })
            best_match_pct = max(best_match_pct, best_chunk_ratio)

    # Determine pass/fail based on best match quality
    # Threshold: >=0.7 passes with confidence proportional to match quality
    if best_match_pct >= 0.7:
        if matched_excerpts:
            excerpt_msg = f" Excerpts: {matched_excerpts[:3]}"
        else:
            excerpt_msg = f" Closest matches: {closest_matches[:3]}"
        return json_result(
            True,
            f"Match found: {best_match_pct:.0%} similarity. "
            f"Expected: '{expected_text}'."
            + excerpt_msg,
            confidence=round(best_match_pct, 3),
            match_percentage=round(best_match_pct, 3),
            matched_excerpts=matched_excerpts[:5],
            closest_matches=closest_matches[:5],
        )

    if best_match_pct >= 0.5:
        # Borderline — close but not confident enough to pass
        return json_result(
            False,
            f"Close match but below threshold: {best_match_pct:.0%} similarity. "
            f"Expected: '{expected_text}'. "
            f"Closest matches: {closest_matches[:3]}",
            confidence=round(best_match_pct, 3),
            match_percentage=round(best_match_pct, 3),
            matched_excerpts=matched_excerpts[:5],
            closest_matches=closest_matches[:5],
        )

    # No meaningful match found
    snippet = page_text[:200] if len(page_text) > 200 else page_text
    return json_result(
        False,
        f"Expected text '{expected_text}' NOT found in page content. "
        f"Page begins with: '{snippet}'",
        match_percentage=round(best_match_pct, 3),
        closest_matches=closest_matches[:3],
    )


def _word_offset_to_char(text: str, word_idx: int) -> int:
    """Convert a word index to a character offset in the original text."""
    words = text.split()
    if word_idx <= 0:
        return 0
    if word_idx >= len(words):
        return len(text)
    # Find the start position of the word_idx-th word
    pos = 0
    for i, w in enumerate(words):
        if i == word_idx:
            return pos
        # Advance past this word and its separator
        idx = text.find(w, pos)
        if idx >= 0:
            pos = idx + len(w)
        else:
            pos += len(w) + 1
    return len(text)


def _average_hash(image: Image.Image, hash_size: int = 8) -> str:
    """Compute a simple average (perceptual) hash of an image.

    Resizes to hash_size x hash_size, computes mean pixel value,
    then produces a binary hash string where each bit indicates
    whether the pixel is above or below the mean.
    """
    resized = image.resize((hash_size, hash_size), Image.LANCZOS)
    if resized.mode == "RGBA":
        resized = resized.convert("RGB")
    pixels = list(resized.getdata())
    # For RGB images, each pixel is a tuple; use average of channels
    if resized.mode == "RGB":
        values = [sum(p) / 3.0 for p in pixels]
    else:
        values = [float(p) for p in pixels]
    mean_val = sum(values) / len(values)
    bits = "".join("1" if v >= mean_val else "0" for v in values)
    # Convert binary string to hex for compact representation
    hex_hash = hashlib.sha256(bits.encode()).hexdigest()[:16]
    return bits, hex_hash


def _hamming_distance(hash1: str, hash2: str) -> int:
    """Compute Hamming distance between two binary hash strings."""
    if len(hash1) != len(hash2):
        return max(len(hash1), len(hash2))
    return sum(c1 != c2 for c1, c2 in zip(hash1, hash2))


def _compare_screenshots(expected_b64: str, actual_b64: str) -> str:
    """Compare two screenshots using pixel-level, structural, and perceptual analysis.

    When PIL is available, this decodes both images and performs:
    - Dimension comparison
    - Perceptual hashing (average hash) for structural similarity
    - Pixel-block comparison for detailed similarity percentage

    When PIL is unavailable, falls back to size-only comparison.

    For detailed visual analysis, the agent uses Qwen3-VL via the verify node.

    Args:
        expected_b64: Base64-encoded expected screenshot.
        actual_b64: Base64-encoded actual screenshot.

    Returns:
        JSON-formatted comparison result with similarity_percentage,
        dimension comparison, and structural similarity indicator.
    """
    try:
        expected_bytes = base64.b64decode(expected_b64)
        actual_bytes = base64.b64decode(actual_b64)

        expected_size = len(expected_bytes)
        actual_size = len(actual_bytes)

        # Size similarity check
        size_ratio = min(expected_size, actual_size) / max(expected_size, actual_size)

        if expected_bytes == actual_bytes:
            return json_result(True, "Screenshots are identical", confidence=1.0,
                               similarity_percentage=100.0, dimensions_match=True,
                               structural_similarity="identical")

        # --- Enhanced comparison with PIL ---
        if _PIL_AVAILABLE:
            try:
                img_expected = Image.open(io.BytesIO(expected_bytes))
                img_actual = Image.open(io.BytesIO(actual_bytes))
            except Exception as img_err:
                # Image decoding failed — fall back to size-only
                logger.warning("PIL image decoding failed: %s; falling back to size-only", img_err)
                return _compare_screenshots_size_only(expected_size, actual_size, size_ratio)

            # Dimension comparison
            dims_expected = (img_expected.width, img_expected.height)
            dims_actual = (img_actual.width, img_actual.height)
            dimensions_match = dims_expected == dims_actual
            dim_ratio = (min(dims_expected[0], dims_actual[0]) * min(dims_expected[1], dims_actual[1])) / \
                        (max(dims_expected[0], dims_actual[0]) * max(dims_expected[1], dims_actual[1]))

            # Perceptual hashing — structural similarity
            hash_bits_exp, hash_hex_exp = _average_hash(img_expected)
            hash_bits_act, hash_hex_act = _average_hash(img_actual)
            hamming = _hamming_distance(hash_bits_exp, hash_bits_act)
            hash_total_bits = len(hash_bits_exp)
            structural_sim_ratio = 1.0 - (hamming / hash_total_bits) if hash_total_bits else 0.0

            # Determine structural similarity category
            if structural_sim_ratio >= 0.9:
                structural_label = "very_similar"
            elif structural_sim_ratio >= 0.7:
                structural_label = "similar"
            elif structural_sim_ratio >= 0.5:
                structural_label = "different_layout"
            else:
                structural_label = "different_pages"

            # Pixel-level comparison (downsampled for efficiency)
            # Resize both images to a common small size for block comparison
            compare_size = (64, 64)
            img_exp_small = img_expected.resize(compare_size, Image.LANCZOS)
            img_act_small = img_actual.resize(compare_size, Image.LANCZOS)
            if img_exp_small.mode != img_act_small.mode:
                img_exp_small = img_exp_small.convert("RGB")
                img_act_small = img_act_small.convert("RGB")

            pixels_exp = list(img_exp_small.getdata())
            pixels_act = list(img_act_small.getdata())
            total_pixels = len(pixels_exp)

            # Compare pixel values with tolerance for minor rendering differences
            similar_pixels = 0
            tolerance = 30  # per-channel tolerance
            for p_exp, p_act in zip(pixels_exp, pixels_act):
                if isinstance(p_exp, tuple) and isinstance(p_act, tuple):
                    channel_diffs = [abs(a - b) for a, b in zip(p_exp, p_act)]
                    if all(d <= tolerance for d in channel_diffs):
                        similar_pixels += 1
                else:
                    if abs(p_exp - p_act) <= tolerance:
                        similar_pixels += 1

            pixel_similarity = similar_pixels / total_pixels if total_pixels else 0.0

            # Combined similarity: weighted blend of pixel and structural
            combined_similarity = 0.6 * pixel_similarity + 0.4 * structural_sim_ratio

            # Build result based on combined analysis
            reason_parts = [
                f"Dimensions: expected={dims_expected}, actual={dims_actual}",
                f"Structural similarity: {structural_sim_ratio:.1%} ({structural_label})",
                f"Pixel similarity (64x64): {pixel_similarity:.1%}",
                f"Combined similarity: {combined_similarity:.1%}",
            ]

            if combined_similarity >= 0.85:
                return json_result(
                    True,
                    f"Screenshots are visually similar. " + "; ".join(reason_parts),
                    confidence=round(combined_similarity, 3),
                    similarity_percentage=round(combined_similarity * 100, 1),
                    dimensions_match=dimensions_match,
                    structural_similarity=structural_label,
                )

            if combined_similarity >= 0.6:
                return json_result(
                    False,
                    f"Screenshots have noticeable differences. " + "; ".join(reason_parts),
                    confidence=round(combined_similarity, 3),
                    similarity_percentage=round(combined_similarity * 100, 1),
                    dimensions_match=dimensions_match,
                    structural_similarity=structural_label,
                )

            return json_result(
                False,
                f"Screenshots are substantially different. " + "; ".join(reason_parts),
                confidence=round(combined_similarity, 3),
                similarity_percentage=round(combined_similarity * 100, 1),
                dimensions_match=dimensions_match,
                structural_similarity=structural_label,
            )

        # --- Fallback: size-only comparison when PIL is unavailable ---
        return _compare_screenshots_size_only(expected_size, actual_size, size_ratio)

    except Exception as exc:
        return json_result(False, f"Screenshot comparison error: {exc}")


def _compare_screenshots_size_only(expected_size: int, actual_size: int, size_ratio: float) -> str:
    """Fallback size-only screenshot comparison when PIL is unavailable."""
    if size_ratio > 0.9:
        return json_result(
            True,
            f"Screenshots have similar size (expected={expected_size}B, "
            f"actual={actual_size}B, ratio={size_ratio:.2f}). "
            f"Note: pixel-level analysis unavailable (PIL not installed) — "
            f"use visual LLM for detailed analysis.",
            confidence=0.6,
            similarity_percentage=round(size_ratio * 100, 1),
            dimensions_match=None,
            structural_similarity="unknown_pil_unavailable",
        )

    if size_ratio > 0.5:
        return json_result(
            False,
            f"Screenshots differ significantly in size "
            f"(expected={expected_size}B, actual={actual_size}B, "
            f"ratio={size_ratio:.2f}). This likely indicates different "
            f"page content or layout. "
            f"Note: pixel-level analysis unavailable (PIL not installed).",
            confidence=0.4,
            similarity_percentage=round(size_ratio * 100, 1),
            dimensions_match=None,
            structural_similarity="unknown_pil_unavailable",
        )

    return json_result(
        False,
        f"Screenshots are very different in size "
        f"(expected={expected_size}B, actual={actual_size}B). "
        f"Ratio={size_ratio:.2f}. Likely showing different pages. "
        f"Note: pixel-level analysis unavailable (PIL not installed).",
        similarity_percentage=round(size_ratio * 100, 1),
        dimensions_match=None,
        structural_similarity="unknown_pil_unavailable",
    )


def _check_element_exists(selector: str) -> str:
    """Check if a DOM element matching the selector likely exists.

    Since this MCP server doesn't have direct browser access, this
    tool provides heuristic guidance based on the selector pattern.
    It also supports natural-language descriptions (e.g. "button named Login")
    by generating plausible CSS selectors with plausibility scores.

    IMPORTANT: This is heuristic validation without browser access.
    Use browser_snapshot for actual DOM verification.

    Args:
        selector: CSS selector, XPath expression, or natural-language
            element description (e.g. "button named 'Login'", "input for email").

    Returns:
        JSON-formatted result with guidance for the agent, including
        suggested selectors and plausibility scores.
    """
    # Validate selector syntax
    if not selector:
        return json_result(False, "Empty selector provided")

    # Detect if the input is a natural-language description
    description_match = re.match(
        r'^(button|input|link|heading|dropdown|select|textarea|checkbox|radio|nav|menu|modal|dialog|form)\s+'
        r'(named|called|labeled|with text|for|containing|with)\s+["\']?(.+?)["\']?\s*$',
        selector,
        re.IGNORECASE,
    )
    if description_match:
        return _generate_selectors_from_description(
            description_match.group(1).lower(),
            description_match.group(2).lower(),
            description_match.group(3).strip().strip("'\""),
        )

    # Detect selector type and validate syntax
    if selector.startswith("//") or selector.startswith("/"):
        # XPath selector
        return json_result(
            True,
            f"XPath selector '{selector}' recognized. This is heuristic "
            f"validation without browser access — use browser_snapshot "
            f"to verify the element exists on the current page.",
            confidence=0.5,
            suggested_selectors=[selector],
            plausibility_scores=[0.5],
        )

    # CSS selector — basic syntax validation
    # Check for balanced brackets and valid characters
    if not re.match(r'^[a-zA-Z0-9_\-\[\]=":\*\.\s>#,\+:has-text\(\)\'~]+$', selector):
        return json_result(
            False,
            f"CSS selector '{selector}' may contain invalid syntax. "
            f"Please verify the selector format.",
            suggested_selectors=None,
            plausibility_scores=None,
        )

    # Analyze the selector and generate additional plausible alternatives
    suggested = _analyze_css_selector(selector)

    return json_result(
        True,
        f"CSS selector '{selector}' appears valid. "
        f"This is heuristic validation without browser access — "
        f"use browser_snapshot or browser_click to verify and interact "
        f"with the element. Suggested alternatives: {suggested}",
        confidence=0.5,
        suggested_selectors=[selector] + suggested,
        plausibility_scores=[0.5] + [0.3] * len(suggested),
    )


# Common element patterns for heuristic selector generation
_ELEMENT_PATTERNS = {
    "button": [
        ("button:has-text('{text}')", 0.8),
        ("button.{text_lower}", 0.4),
        ("input[type='submit'][value='{text}']", 0.6),
        ("[role='button']:has-text('{text}')", 0.5),
        ("button >> text='{text}'", 0.7),
    ],
    "input": [
        ("input[name='{text_lower}']", 0.7),
        ("input[type='{text_lower}']", 0.5),
        ("input[placeholder*='{text}']", 0.6),
        ("input[label='{text}']", 0.4),
        ("label:has-text('{text}') + input", 0.6),
    ],
    "link": [
        ("a:has-text('{text}')", 0.8),
        ("a[href*='{text_lower}']", 0.4),
        ("a[title='{text}']", 0.5),
    ],
    "heading": [
        ("h1:has-text('{text}')", 0.7),
        ("h2:has-text('{text}')", 0.6),
        ("h3:has-text('{text}')", 0.5),
        ("h4:has-text('{text}')", 0.4),
        ("[role='heading']:has-text('{text}')", 0.3),
    ],
    "dropdown": [
        ("select[name='{text_lower}']", 0.6),
        ("select[aria-label*='{text}']", 0.5),
        ("[role='listbox']", 0.3),
    ],
    "select": [
        ("select[name='{text_lower}']", 0.7),
        ("select:has-text('{text}')", 0.5),
    ],
    "textarea": [
        ("textarea[name='{text_lower}']", 0.7),
        ("textarea[placeholder*='{text}']", 0.5),
    ],
    "checkbox": [
        ("input[type='checkbox'][name='{text_lower}']", 0.6),
        ("input[type='checkbox'][aria-label*='{text}']", 0.5),
    ],
    "radio": [
        ("input[type='radio'][value='{text}']", 0.6),
        ("input[type='radio'][name='{text_lower}']", 0.5),
    ],
    "nav": [
        ("nav", 0.5),
        ("nav:has-text('{text}')", 0.6),
        ("[role='navigation']", 0.4),
    ],
    "menu": [
        ("[role='menu']", 0.5),
        ("[role='menu']:has-text('{text}')", 0.4),
    ],
    "modal": [
        ("[role='dialog']", 0.5),
        ("[class*='modal']", 0.4),
        ("[class*='overlay']", 0.3),
    ],
    "dialog": [
        ("[role='dialog']", 0.6),
        ("[class*='dialog']", 0.4),
    ],
    "form": [
        ("form", 0.5),
        ("form[action*='{text_lower}']", 0.4),
    ],
}


def _generate_selectors_from_description(element_type: str, relation: str, text: str) -> str:
    """Generate plausible CSS selectors from a natural-language element description.

    Args:
        element_type: The type of element (button, input, link, etc.).
        relation: How the text relates to the element (named, labeled, for, etc.).
        text: The text/label associated with the element.

    Returns:
        JSON-formatted result with suggested selectors and plausibility scores.
    """
    text_lower = text.lower().replace(" ", "-")

    patterns = _ELEMENT_PATTERNS.get(element_type, [
        (f"{element_type}:has-text('{text}')", 0.5),
        (f"[aria-label*='{text}']", 0.4),
    ])

    # Generate selectors by filling in templates
    suggested_selectors: list[str] = []
    plausibility_scores: list[float] = []

    for template, base_score in patterns:
        selector = template.format(text=text, text_lower=text_lower)
        suggested_selectors.append(selector)
        plausibility_scores.append(round(base_score, 2))

    # Sort by plausibility descending
    paired = sorted(zip(suggested_selectors, plausibility_scores),
                     key=lambda x: x[1], reverse=True)
    suggested_selectors = [p[0] for p in paired]
    plausibility_scores = [p[1] for p in paired]

    top_selector = suggested_selectors[0]
    top_score = plausibility_scores[0]

    if top_score >= 0.7:
        passed = True
        confidence = top_score
    elif top_score >= 0.5:
        passed = True
        confidence = top_score
    else:
        passed = False
        confidence = top_score

    return json_result(
        passed,
        f"Element description '{element_type} {relation} \"{text}\"' "
        f"interpreted heuristically. This is heuristic validation "
        f"without browser access — use browser_snapshot for actual "
        f"verification. Most plausible selector: '{top_selector}' "
        f"(score={top_score}).",
        confidence=confidence,
        suggested_selectors=suggested_selectors[:5],
        plausibility_scores=plausibility_scores[:5],
        element_type=element_type,
        description_text=text,
    )


def _analyze_css_selector(selector: str) -> list[str]:
    """Analyze a CSS selector and suggest plausible alternative selectors.

    Given a selector like '#login-btn', suggest alternatives like
    'button#login-btn', '[data-testid=login-btn]', etc.
    """
    alternatives: list[str] = []

    # If selector is an ID (#something), suggest attribute-based alternatives
    id_match = re.match(r'^#([a-zA-Z0-9_-]+)$', selector)
    if id_match:
        id_val = id_match.group(1)
        alternatives.append(f'[id="{id_val}"]')
        alternatives.append(f'[data-testid="{id_val}"]')
        alternatives.append(f'button#{id_val}')

    # If selector is a class (.something), suggest tag+class alternatives
    class_match = re.match(r'^\.([a-zA-Z0-9_-]+)$', selector)
    if class_match:
        cls_val = class_match.group(1)
        alternatives.append(f'[class*="{cls_val}"]')
        alternatives.append(f'div.{cls_val}')
        alternatives.append(f'button.{cls_val}')

    # If selector contains :has-text, suggest aria-label alternative
    if ":has-text" in selector or "text=" in selector:
        text_match = re.search(r"has-text\(['\"](.+?)['\"]\)|text=['\"](.+?)['\"]", selector)
        if text_match:
            text_val = text_match.group(1) or text_match.group(2)
            alternatives.append(f'[aria-label*="{text_val}"]')
            alternatives.append(f'[title="{text_val}"]')

    return alternatives[:3]


def json_result(
    passed: bool,
    reason: str,
    confidence: float | None = None,
    **extra_fields: Any,
) -> str:
    """Format a verification result as a JSON string.

    Args:
        passed: Whether the verification check passed.
        reason: Human-readable explanation of the result.
        confidence: Confidence score (0.0-1.0). Defaults to 1.0 for pass, 0.0 for fail.
        **extra_fields: Additional fields to include in the result (e.g.
            match_percentage, matched_excerpts, closest_matches,
            similarity_percentage, dimensions_match, structural_similarity,
            suggested_selectors, plausibility_scores, etc.)
    """
    if confidence is None:
        confidence = 1.0 if passed else 0.0
    result = {
        "passed": passed,
        "reason": reason,
        "confidence": confidence,
    }
    for key, value in extra_fields.items():
        if value is not None:
            result[key] = value
    return json.dumps(result)


# ---------------------------------------------------------------------------
# MCP Server definition
# ---------------------------------------------------------------------------

app = Server("verify-mcp")


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    """Return the list of available Verify MCP tools."""
    return [
        types.Tool(
            name="compare_screenshots",
            description="Compare an expected screenshot with an actual screenshot. "
                        "Performs basic size and binary comparison. For detailed "
                        "visual analysis, use the Qwen3-VL vision model via the "
                        "verify node instead.",
            inputSchema={
                "type": "object",
                "properties": {
                    "expected_b64": {
                        "type": "string",
                        "description": "Base64-encoded expected screenshot image.",
                    },
                    "actual_b64": {
                        "type": "string",
                        "description": "Base64-encoded actual screenshot image.",
                    },
                },
                "required": ["expected_b64", "actual_b64"],
            },
        ),
        types.Tool(
            name="check_text_content",
            description="Check if page text content contains expected text. "
                        "Performs case-insensitive substring matching with "
                        "partial word matching support.",
            inputSchema={
                "type": "object",
                "properties": {
                    "page_text": {
                        "type": "string",
                        "description": "The full text content of the page to check.",
                    },
                    "expected_text": {
                        "type": "string",
                        "description": "The text expected to be present on the page.",
                    },
                },
                "required": ["page_text", "expected_text"],
            },
        ),
        types.Tool(
            name="check_element_exists",
            description="Validate a CSS or XPath selector and provide guidance "
                        "for verifying element existence via browser tools. "
                        "Note: this tool validates selector syntax but does not "
                        "have direct browser access — use browser_snapshot for "
                        "actual DOM verification.",
            inputSchema={
                "type": "object",
                "properties": {
                    "selector": {
                        "type": "string",
                        "description": "CSS selector or XPath expression to validate.",
                    },
                },
                "required": ["selector"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    """Handle tool calls for the Verify MCP server."""
    if name == "compare_screenshots":
        expected = arguments.get("expected_b64", "")
        actual = arguments.get("actual_b64", "")
        if not expected or not actual:
            return [types.TextContent(
                type="text",
                text="Error: both 'expected_b64' and 'actual_b64' parameters are required",
            )]
        result = _compare_screenshots(expected, actual)
        return [types.TextContent(type="text", text=result)]

    elif name == "check_text_content":
        page_text = arguments.get("page_text", "")
        expected_text = arguments.get("expected_text", "")
        if not page_text:
            return [types.TextContent(
                type="text",
                text="Error: 'page_text' parameter is required",
            )]
        if not expected_text:
            return [types.TextContent(
                type="text",
                text="Error: 'expected_text' parameter is required",
            )]
        result = _check_text_content(page_text, expected_text)
        return [types.TextContent(type="text", text=result)]

    elif name == "check_element_exists":
        selector = arguments.get("selector", "")
        result = _check_element_exists(selector)
        return [types.TextContent(type="text", text=result)]

    else:
        return [types.TextContent(type="text", text=f"Unknown tool: {name}")]


async def main() -> None:
    """Run the Verify MCP server via stdio transport."""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())