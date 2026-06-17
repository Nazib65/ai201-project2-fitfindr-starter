# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Searches the mock listings dataset for secondhand items matching the user's
description, optional size, and maximum price. Returns matching listings sorted
by how relevant they are to the search words.

**Input parameters:**
- `description` (str): free-text search, e.g. "vintage graphic tee". Split into
  words and matched (case-insensitive) against each listing's title, description,
  and style_tags.
- `size` (str or None): desired size, e.g. "M". If None, the size filter is
  skipped and listings of all sizes are eligible. If given, a listing matches
  when the size string is contained in the listing's size (case-insensitive),
  so "M" matches both "M" and "S/M".
- `max_price` (float): only listings with price <= max_price are returned.

**What it returns:**
A list of matching listing dicts (each with the full fields: id, title,
description, category, style_tags, size, condition, price, colors, brand,
platform). The list is sorted by relevance — the number of search words a
listing matched, highest first — with ties broken by price ascending (cheaper
first). A listing must match at least one search word to be included.

**What happens if it fails or returns nothing:**
The tool returns an empty list `[]` — it never raises or returns None. When the
agent receives an empty list, it stops the workflow and tells the user no
listings matched, suggesting what to adjust (raise the max price, drop the size
filter, or try different keywords). It does NOT call suggest_outfit.

---

### Tool 2: suggest_outfit

**What it does:**
Given a specific new item and the user's current wardrobe, calls the LLM
(Groq llama-3.3-70b-versatile) to suggest one or two complete outfit
combinations that pair the new item with pieces the user already owns, plus a
short styling tip (how to wear/tuck/layer it).

**Input parameters:**
- `new_item` (dict): a single listing dict from search_listings' results. The
  prompt uses its title, category, colors, style_tags, and description so the
  LLM knows what's being styled.
- `wardrobe` (dict): the user's wardrobe in schema form, `{"items": [...]}`,
  where each item has name, category, colors, style_tags, and optional notes.
  The prompt lists these items so the LLM pairs against real pieces.

**What it returns:**
A natural-language string describing one or two outfit combinations that name
specific wardrobe pieces, plus a styling tip. Example: "Pair this with your
wide-leg khaki trousers and chunky white sneakers... roll the sleeves once."

**What happens if it fails or returns nothing:**
If wardrobe["items"] is empty, the tool does NOT crash and does NOT invent
fake wardrobe pieces. Instead it asks the LLM for GENERAL styling advice for
the new item on its own (e.g. silhouettes, colors, and shoe types that pair
well), and returns that string. If the LLM call itself errors, the tool catches
the exception and returns a short fallback string so the agent keeps running.

---

### Tool 3: create_fit_card

**What it does:**
Generates a short, shareable, social-media-style caption for the complete
outfit — the kind of thing someone would post with a thrifted find. Calls the
LLM with a higher temperature so the output varies for different inputs (and
across runs on the same input).

**Input parameters:**
- `outfit` (str): the outfit suggestion text returned by suggest_outfit.
- `new_item` (dict): the listing dict, so the caption can mention the actual
  piece, its price, and platform (e.g. "thrifted off depop for $22").

**What it returns:**
A short caption string (roughly 1–2 sentences, casual tone, may include an
emoji) suitable as an Instagram/Depop caption. Different inputs produce
different captions; the same input produces varied captions across runs.

**What happens if it fails or returns nothing:**
If `outfit` is an empty string (or missing), the tool does NOT call the LLM and
returns a clear error-message string explaining a caption can't be made without
an outfit — it never raises. If the LLM call errors, it catches the exception
and returns a short fallback caption string.

---

## Planning Loop

**How does your agent decide which tool to call next?**

The planning loop runs in order but branches on what each tool returns, so the
agent does NOT call all three tools unconditionally.

1. Parse the user query into `description`, `size`, and `max_price` using an LLM
   extraction step: the raw sentence is sent to the LLM (Groq
   llama-3.3-70b-versatile, low temperature) with a prompt asking it to return
   those three fields as structured values (e.g. JSON). `size` and `max_price`
   may come back as None when the user didn't state them. If the extraction call
   fails or returns unparseable output, the agent falls back to safe defaults
   (`description` = the raw query, `size` = None, `max_price` = a high default)
   so search can still run.
2. Call `search_listings(description, size, max_price)`.
   - **Branch A — empty list:** set `session["error"]` to a helpful message,
     leave `selected_item`, `outfit_suggestion`, and `fit_card` as None, and
     return early. suggest_outfit and create_fit_card are NEVER called.
   - **Branch B — results exist:** set `session["selected_item"] = results[0]`
     (top of the relevance-sorted list) and continue.
3. Call `suggest_outfit(session["selected_item"], wardrobe)` and store the
   result in `session["outfit_suggestion"]`.
4. Call `create_fit_card(session["outfit_suggestion"], session["selected_item"])`
   and store the result in `session["fit_card"]`.
5. Return the session. The loop is "done" when either the error branch returned
   early or all three steps have populated their session fields.

The key property: steps 3 and 4 only run because step 2 took Branch B. The
agent's behavior changes based on what search_listings returned.

---

## State Management

**How does information from one tool get passed to the next?**

A single `session` dict is created at the start of `run_agent()` and threaded
through the whole interaction. It holds:

- `query` (str): the original user query
- `selected_item` (dict or None): the listing chosen from search results
- `outfit_suggestion` (str or None): the text returned by suggest_outfit
- `fit_card` (str or None): the caption returned by create_fit_card
- `error` (str or None): set only when a step fails / returns nothing

Each tool reads what it needs from the session (the item found by
search_listings flows into suggest_outfit, whose output flows into
create_fit_card) and writes its result back into the session. The user never
re-enters the item or outfit between steps — the session carries it. At the end
of the interaction the session dict is the complete record of what happened.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | Tool returns `[]`. Agent sets an error message: "No listings matched 'vintage graphic tee' under $30 in size M. Try raising your max price, removing the size filter, or different keywords." Agent stops and does not call the other tools. |
| suggest_outfit | Wardrobe is empty | Tool returns general styling advice for the item on its own (silhouettes/colors/shoe types that pair well) instead of crashing or naming fake pieces. Agent continues to create_fit_card with that advice. |
| create_fit_card | Outfit input is missing or incomplete | Tool returns a clear error-message string ("Can't make a fit card without an outfit suggestion") instead of raising. Agent surfaces this message rather than showing a broken card. |

(Both LLM tools also wrap the network call in try/except and return a short
fallback string on error, so a network failure never crashes the agent.)

---

## Architecture

```
User query
    │
    ▼
Planning Loop (run_agent) ────────────────────────────────────┐
    │                                                          │
    │  parse query → description, size, max_price              │
    │                                                          │
    ├─► search_listings(description, size, max_price)          │
    │       │ results == []                                    │
    │       ├──► Session: error = "No listings found..."       │
    │       │         └──► [ERROR] return session early ───────┤
    │       │                                                  │
    │       │ results == [item, ...]                           │
    │       ▼                                                  │
    │   Session: selected_item = results[0]                    │
    │       │                                                  │
    ├─► suggest_outfit(selected_item, wardrobe)                │
    │       │  (empty wardrobe → general advice, no crash)     │
    │       ▼                                                  │
    │   Session: outfit_suggestion = "..."                     │
    │       │                                                  │
    └─► create_fit_card(outfit_suggestion, selected_item)      │
            │  (empty outfit → error string, no crash)         │
            ▼                                                  │
        Session: fit_card = "..."                              │
            │                                                  │
            ▼                          error path returns here ┘
        Return session ◄───────────────────────────────────────
```

Components: **User** (query) → **Planning Loop** (run_agent) → three **Tools**
(search_listings, suggest_outfit, create_fit_card) ↕ **Session state** (dict
holding selected_item, outfit_suggestion, fit_card, error). The error branch
terminates the flow early after search_listings.

---

## AI Tool Plan

<!-- For each part of the implementation below, describe:
     - Which AI tool you plan to use (Claude, Copilot, ChatGPT, etc.)
     - What you'll give it as input (which sections of this planning.md, your agent diagram)
     - What you expect it to produce
     - How you'll verify the output matches your spec before moving on

     "I'll use AI to help me code" is not a plan.
     "I'll give Claude my Tool 1 spec (inputs, return value, failure mode) and ask it to implement
     search_listings() using load_listings() from the data loader — then test it against 3 queries
     before trusting it" is a plan. -->

**Milestone 3 — Individual tool implementations:**
I'll use Claude. For each tool, one at a time, I'll paste that tool's block from
the Tools section above (what it does, inputs, return value, failure mode) and
ask Claude to implement just that function in tools.py.
- For `search_listings`: I'll require it to use `load_listings()` from
  utils/data_loader.py, filter by all three params (with size=None skipping the
  size filter), sort by relevance then price, and return `[]` on no matches.
  Verify: run the 3 pytest cases (results, empty, price filter) before trusting it.
- For `suggest_outfit` and `create_fit_card`: I'll require Groq
  llama-3.3-70b-versatile with the key from .env, the empty-wardrobe / empty-outfit
  guards, and a try/except fallback. Verify: call each directly with example and
  empty inputs and confirm a string comes back (and that fit cards vary across runs).

**Milestone 4 — Planning loop and state management:**
I'll give Claude the Planning Loop section, the State Management section, AND the
Architecture diagram together, and ask it to implement run_agent() in agent.py.
Before running, I'll check: does it branch on the search_listings result (return
early on `[]`)? Does it store values in the session dict instead of re-prompting?
Does it avoid calling all three tools unconditionally? Then I'll test both the
happy path and the no-results path with python agent.py.

---

## A Complete Interaction (Step by Step)

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:**
The planning loop parses the query into `description="vintage graphic tee"`,
`size=None` (no size stated), `max_price=30.0`, and calls
`search_listings("vintage graphic tee", size=None, max_price=30.0)`. This
returns listings whose title/description/style_tags match words like "vintage"
or "graphic"/"tee" and cost <= $30, sorted by relevance then price. The top
result is the Y2K Baby Tee (lst_002, $18, style_tags include "graphic tee" and
"vintage"). The agent stores it: `session["selected_item"] = lst_002`.

**Step 2:**
Because results were non-empty (Branch B), the agent calls
`suggest_outfit(session["selected_item"], wardrobe)` using the example
wardrobe. The LLM returns something like: "Pair this baby tee with your baggy
straight-leg jeans and chunky white sneakers for an easy Y2K look — add the
vintage black denim jacket on top and tuck the front hem for shape." Stored as
`session["outfit_suggestion"]`.

**Step 3:**
The agent calls `create_fit_card(session["outfit_suggestion"],
session["selected_item"])`. The LLM (higher temperature) returns a caption like:
"found this y2k butterfly baby tee on depop for $18 and it was MADE for my baggy
jeans 🦋 full fit in stories." Stored as `session["fit_card"]`.

**Final output to user:**
The user sees three panels: (1) the matched listing (Y2K Baby Tee — $18, depop,
excellent condition), (2) the outfit suggestion pairing it with their baggy
jeans, denim jacket, and chunky sneakers, and (3) the shareable fit-card
caption. If search_listings had returned nothing, the user would instead see a
single helpful error message and steps 2–3 would never run.
