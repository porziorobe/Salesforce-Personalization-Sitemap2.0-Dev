# Personalization Sitemap Generator 2.0 (Dev)

A web application for Salesforce Sales Engineers to generate Personalization sitemap JS and Experience Template HTML from a customer's website. Provide the hero and recs HTML from DevTools (or let the tool auto-detect from a URL), and get the artifacts you need to paste into the WPM UI — no manual HTML wrangling required.

## What This Does

1. **Accepts** hero and recs HTML provided by the SE (pasted from DevTools, or auto-detected from a URL as a starting point)
2. **Extracts** CSS styles (colors, fonts, spacing) from the live page
3. **Generates** three artifacts independently:
   - **Sitemap JS** — minimal SDK init + content zones (deploy to site)
   - **Hero Experience Template** — Handlebars HTML for the hero (paste into WPM Experience Template)
   - **Recommendations Experience Template** — Handlebars HTML for product cards (paste into WPM Experience Template)

Each artifact has its own Generate button so the SE can re-run only what they need without spending an LLM call on the others. Sitemap JS is assembled deterministically in Python; Hero and Recs Experience Templates are both LLM-bound.

## Stack

- **Backend:** Python 3 / Flask
- **Frontend:** Vanilla HTML/CSS/JS (no build step)
- **LLM:** Claude Sonnet 4.6 via Salesforce Einstein Platform API (`/chat-generations` endpoint, Connected App auth)
- **Deployment:** Heroku (Python buildpack + gunicorn)

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `EINSTEIN_CLIENT_SECRET` | **Yes** | Client secret for the Salesforce Connected App. Never commit this value. |
| `PORT` | On Heroku | HTTP port. Heroku sets this automatically; locally defaults to `3000`. |

## Local Development

```bash
cp .env.example .env
# Populate EINSTEIN_CLIENT_SECRET — pull from Heroku:
#   heroku config:get EINSTEIN_CLIENT_SECRET --app sitemap-dev
pip install -r requirements.txt
python3 main.py
```

Open [http://localhost:3000](http://localhost:3000)

## Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/detect` | POST | Fetch the customer URL, detect the hero element, and detect any repeating recs container/card pattern |
| `/extract-styles` | POST | Re-fetch the page and bucket CSS values for the LLM prompt. Accepts `mode: "hero"` (default) or `mode: "recs"` |
| `/assemble-sitemap` | POST | Python-only — assemble the minimal sitemap JS from hero + recommendations selectors |
| `/generate` | POST | LLM-bound — generate the Hero Experience Template HTML |
| `/regenerate` | POST | LLM-bound — regenerate the Hero with feedback (issue checkboxes + free text) |
| `/hero-template` | POST | Returns the generic default Hero Experience Template (no LLM, no customer inputs required) |
| `/generate-recs` | POST | LLM-bound — generate the full Recs Experience Template (container + loop + card body) |
| `/regenerate-recs` | POST | LLM-bound — regenerate the full recs template with feedback |
| `/recommendations-template` | POST | Returns the generic default Recs Experience Template (no LLM, no customer inputs required) |

## Architecture

The tool uses a **declarative templating approach**: the LLM generates the Experience Template HTML for hero and recs; the backend assembles the sitemap JS deterministically by replacing placeholders in raw-string Python constants.

A deterministic post-processor (`inline_extracted_styles`) sits after each LLM call and resolves any `{{EXTRACTED_STYLES.bucket.key}}` literals the LLM occasionally leaks.

**Carousel sanitizer** strips framework chrome before the HTML reaches the LLM:
- *Hero carousels:* collapse to first slide only, unwrap track/outer wrappers, decompose nav/pagination chrome.
- *Recs carousels:* unwrap track wrappers (keep per-slide/card elements), decompose chrome.

Supported frameworks: Swiper, Slick, Owl, Flickity, Splide, Glide, Bootstrap Carousel, Embla, tns.

**Design boundary:** deterministic for mechanical parts (sitemap assembly, subVar insertion, post-processing invariants), LLM for creative parts (HTML transformation, semantic mapping, noise stripping).

**CSS class-based styling transfers correctly.** WPM injects the template into the customer's live page — the customer's stylesheets are present and match class names on injected elements.

## Deploy

This app is deployed via `git subtree push` from the parent monorepo:

```bash
# From the monorepo root (personalization-sitemap-generator/)
git subtree push --prefix=sitemap-generator-dev sitemap-dev main
```

Set `EINSTEIN_CLIENT_SECRET` in Heroku config vars. The `Procfile` runs `web: gunicorn main:app`.
