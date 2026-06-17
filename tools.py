"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform

    TODO:
        1. Load all listings with load_listings().
        2. Filter by max_price and size (if provided).
        3. Score each remaining listing by keyword overlap with `description`.
        4. Drop any listings with a score of 0 (no relevant matches).
        5. Sort by score, highest first, and return the listing dicts.

    Before writing code, fill in the Tool 1 section of planning.md.
    """
    listings = load_listings()

    # Split the search text into lowercase words for case-insensitive matching.
    search_words = description.lower().split()

    matches = []
    for listing in listings:
        # Price filter: skip anything over the ceiling (if a ceiling was given).
        if max_price is not None and listing["price"] > max_price:
            continue

        # Size filter: only applied when a size is given. "M" matches "S/M".
        if size is not None and size.lower() not in listing["size"].lower():
            continue

        # Relevance score: how many search words appear in the listing's
        # title, description, or style_tags (all lowercased).
        haystack = " ".join([
            listing["title"],
            listing["description"],
            " ".join(listing["style_tags"]),
        ]).lower()
        score = sum(1 for word in search_words if word in haystack)

        # A listing must match at least one search word to be included.
        if score > 0:
            matches.append((score, listing))

    # Sort by relevance (highest score first), ties broken by price ascending.
    matches.sort(key=lambda pair: (-pair[0], pair[1]["price"]))

    # Return just the listing dicts, dropping the score we sorted on.
    return [listing for _score, listing in matches]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    TODO:
        1. Check whether wardrobe['items'] is empty.
        2. If empty: call the LLM with a prompt for general styling ideas
           (what kinds of items pair well, what vibe it suits, etc.).
        3. If not empty: format the wardrobe items into a prompt and ask
           the LLM to suggest specific outfit combinations using the new item
           and named pieces from the wardrobe.
        4. Return the LLM's response as a string.

    Before writing code, fill in the Tool 2 section of planning.md.
    """
    # Describe the new item for the prompt.
    item_desc = (
        f"{new_item.get('title', 'item')} "
        f"(category: {new_item.get('category', 'unknown')}, "
        f"colors: {', '.join(new_item.get('colors', []))}, "
        f"style: {', '.join(new_item.get('style_tags', []))})"
    )

    items = wardrobe.get("items", [])

    if not items:
        # Empty wardrobe → general styling advice, no crash, no fake pieces.
        prompt = (
            f"A user just found this secondhand item: {item_desc}.\n"
            "They have not entered their wardrobe yet. Give them general styling "
            "advice for this piece on its own: what silhouettes, colors, and shoe "
            "types pair well, and the overall vibe it suits. Keep it to 2-3 "
            "sentences and do not invent specific items they own."
        )
    else:
        # Format the wardrobe so the LLM can pair against real pieces.
        wardrobe_lines = "\n".join(
            f"- {it.get('name', 'item')} "
            f"({it.get('category', '')}; {', '.join(it.get('colors', []))})"
            for it in items
        )
        prompt = (
            f"A user just found this secondhand item: {item_desc}.\n\n"
            f"Here is their current wardrobe:\n{wardrobe_lines}\n\n"
            "Suggest 1-2 complete outfit combinations that pair the new item with "
            "specific pieces from their wardrobe (name the pieces). Add one short "
            "styling tip (how to tuck/layer/roll it). Keep it to 2-4 sentences."
        )

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        # Network/API failure → fallback string so the agent keeps running.
        return (
            "Couldn't generate an outfit suggestion right now "
            f"({type(e).__name__}). Try this piece with simple basics in "
            "complementary colors for now."
        )


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    TODO:
        1. Guard against an empty or whitespace-only outfit string.
        2. Build a prompt that gives the LLM the item details and the outfit,
           and asks for a caption matching the style guidelines above.
        3. Call the LLM and return the response.

    Before writing code, fill in the Tool 3 section of planning.md.
    """
    # Guard: no outfit → return an error string, do NOT call the LLM or crash.
    if not outfit or not outfit.strip():
        return "Can't make a fit card without an outfit suggestion."

    item_title = new_item.get("title", "this piece")
    price = new_item.get("price")
    platform = new_item.get("platform", "")
    price_str = f"${price:.0f}" if isinstance(price, (int, float)) else ""

    prompt = (
        f"Write a short, casual social-media caption (2-4 sentences) for an "
        f"outfit-of-the-day post about a thrifted find.\n"
        f"Item: {item_title}. Price: {price_str}. Platform: {platform}.\n"
        f"Outfit: {outfit}\n"
        "Mention the item, its price, and the platform naturally (once each). "
        "Sound like a real person posting, not a product description. An emoji "
        "is fine. Just return the caption."
    )

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=1.0,  # high temp → varied captions across runs
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        # Network/API failure → fallback caption, never raises.
        return (
            f"Just scored {item_title} for {price_str} on {platform} "
            f"— obsessed 🛍️ (caption generator hiccuped: {type(e).__name__})"
        )
