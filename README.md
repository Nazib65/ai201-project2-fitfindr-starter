# FitFindr 🛍️

FitFindr is a multi-tool AI agent that helps you find secondhand clothing and
figure out how to wear it. You describe what you want in plain language; the
agent searches a listings dataset, picks the best match, suggests an outfit that
pairs it with your existing wardrobe, and writes a shareable caption for the
look. It also handles the messy cases — no listings found, an empty wardrobe, or
a missing outfit — without crashing.

---

## Setup

1. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate          # Windows (PowerShell)
   # source .venv/Scripts/activate # Windows (Git Bash)
   # source .venv/bin/activate     # Mac/Linux
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Add your Groq API key to a `.env` file in the project root (never commit this):
   ```
   GROQ_API_KEY=your_key_here
   ```
   Get a free key at [console.groq.com](https://console.groq.com).

## Running it

```bash
python app.py            # launch the Gradio web UI (open the localhost URL it prints)
python agent.py          # run the agent from the CLI (happy path + no-results path)
python -m pytest tests/  # run the test suite
```

---

## The Three Tools

All three live in `tools.py` and can be called and tested independently.

### `search_listings(description, size, max_price) -> list[dict]`
Filters the mock dataset (`data/listings.json`) and returns matching listings.
- **description** (str): split into lowercase words and matched against each
  listing's title, description, and style_tags. A listing is included if it
  matches **at least one** word (case-insensitive).
- **size** (str or None): if given, matches when the size string is contained in
  the listing's size (`"M"` matches `"S/M"`); if `None`, the size filter is skipped.
- **max_price** (float): only listings priced at or below this are returned.
- **Returns:** a list of full listing dicts, sorted by **relevance** (number of
  words matched, highest first), ties broken by **price ascending**. Returns an
  empty list `[]` when nothing matches — never raises.

### `suggest_outfit(new_item, wardrobe) -> str`
Uses the LLM (Groq `llama-3.3-70b-versatile`) to suggest 1–2 outfits pairing the
new item with pieces in the user's wardrobe, plus a styling tip.
- **new_item** (dict): a listing dict from `search_listings`.
- **wardrobe** (dict): `{"items": [...]}` in the schema from
  `data/wardrobe_schema.json`.
- **Returns:** a natural-language string. If the wardrobe is empty, it returns
  general styling advice for the item instead of naming pieces the user doesn't own.

### `create_fit_card(outfit, new_item) -> str`
Uses the LLM (high temperature, for variety) to write a short, casual,
social-media-style caption for the outfit.
- **outfit** (str): the suggestion text from `suggest_outfit`.
- **new_item** (dict): the listing dict, so the caption can name the item, price,
  and platform.
- **Returns:** a short caption string. Different inputs (and repeated runs)
  produce different captions.

---

## How the Planning Loop Works

`run_agent(query, wardrobe)` in `agent.py` runs the loop. It does **not** call
all three tools unconditionally — it branches on what each tool returns:

1. **Parse the query** with an LLM extraction step (`_parse_query`, temperature 0)
   into `description`, `size`, and `max_price`. If extraction fails or returns
   unparseable output, it falls back to safe defaults so search can still run.
2. **Call `search_listings`** with the parsed parameters.
   - **If the result is empty:** set `session["error"]` to a helpful message and
     **return early.** `suggest_outfit` and `create_fit_card` are never called.
   - **If there are results:** set `session["selected_item"]` to the top
     (most relevant) listing and continue.
3. **Call `suggest_outfit`** with the selected item and wardrobe; store the result.
4. **Call `create_fit_card`** with the outfit suggestion and selected item; store it.
5. **Return the session.**

The key property: steps 3–4 only run because step 2 found matches. The agent's
behavior changes based on what `search_listings` returned — that is the planning
loop, not a fixed script.

## State Management

A single `session` dict (created in `_new_session`) is threaded through the whole
interaction and is the single source of truth:

| field | meaning |
|-------|---------|
| `query` | the original user query |
| `parsed` | extracted description / size / max_price |
| `search_results` | list of matching listings |
| `selected_item` | the chosen listing, passed into `suggest_outfit` |
| `wardrobe` | the user's wardrobe |
| `outfit_suggestion` | string from `suggest_outfit`, passed into `create_fit_card` |
| `fit_card` | the final caption |
| `error` | set only when the run ended early |

Each tool reads what it needs from the session and writes its result back. The
item found by `search_listings` flows into `suggest_outfit`, whose output flows
into `create_fit_card` — the user never re-enters anything between steps.

## Error-Handling Strategy

Every tool handles its own failure mode and returns a usable value (never raises,
never returns `None` where a string is expected), so one failure can't crash the
agent or poison the next step.

| Tool | Failure mode | What happens |
|------|--------------|--------------|
| `search_listings` | No listings match | Returns `[]`. The agent sets an error message telling the user what to adjust (raise max price, drop the size filter, different keywords) and stops — it does not call the other tools. |
| `suggest_outfit` | Wardrobe is empty | Returns general styling advice for the item on its own instead of naming fake pieces. The workflow continues. |
| `create_fit_card` | Outfit string is empty/missing | Returns a clear error-message string before ever calling the LLM. |
| Both LLM tools | Network/API error | Wrapped in `try/except`; return a short fallback string so the agent keeps running. |
| Query parser | LLM/JSON failure | Falls back to safe defaults (raw query as description, no size, high max price). |

---

## A Complete Multi-Step Interaction

**Query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy
jeans and chunky sneakers. What's out there and how would I style it?"

1. **Parse** → `description="vintage graphic tee"`, `size=None`, `max_price=30`.
2. **`search_listings`** → matches sorted by relevance; top result is the
   **Y2K Baby Tee — Butterfly Print** ($18, depop). Stored as `selected_item`.
3. **`suggest_outfit`** → "Pair the baby tee with your baggy straight-leg jeans
   and chunky white sneakers... tuck the front hem for shape." Stored as
   `outfit_suggestion`.
4. **`create_fit_card`** → "found this y2k butterfly baby tee on depop for $18
   and it was MADE for my baggy jeans 🦋 full fit in stories." Stored as `fit_card`.

The UI shows all three results in separate panels. On a no-results query (e.g.
*designer ballgown size XXS under $5*), the user instead sees a single helpful
error message and steps 3–4 never run.

---

## Project Structure

```
ai201-project2-fitfindr-starter/
├── data/
│   ├── listings.json          # 40 mock secondhand listings
│   └── wardrobe_schema.json   # wardrobe format + example/empty wardrobes
├── utils/
│   └── data_loader.py         # load_listings / get_example_wardrobe / get_empty_wardrobe
├── tools.py                   # the three tools
├── agent.py                   # planning loop + state (run_agent)
├── app.py                     # Gradio web interface
├── tests/
│   └── test_tools.py          # pytest tests (tool behavior + failure modes)
├── planning.md                # design spec, diagram, and AI tool plan
└── requirements.txt
```
