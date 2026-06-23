import os
import re
import json
import time
import logging
from urllib.parse import urljoin, urlparse

import requests
import cssutils
from bs4 import BeautifulSoup, Comment
from flask import Flask, request, jsonify, render_template

from dotenv import load_dotenv

load_dotenv()

from auth import ConnectedAppAuth
from llm_provider import ConnectAPILLM

cssutils.log.setLevel(logging.CRITICAL)

authenticator = ConnectedAppAuth(creds_file="creds.json")
llm = ConnectAPILLM(authenticator=authenticator)

app = Flask(__name__)

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)

HERO_KEYWORDS = re.compile(r"(hero|banner|jumbotron|masthead|splash|jumbo)", re.I)
RECS_KEYWORDS = re.compile(r"(recommend|product|card|grid|carousel|featured|related|tile|collection)", re.I)

DEFAULT_STYLES = {
    "banner": {"backgroundColor": "#333333", "fontFamily": "Arial, Helvetica, sans-serif"},
    "header": {"fontSize": "32px", "fontWeight": "600", "color": "#DDDDDD"},
    "subheader": {"fontSize": "20px", "fontWeight": "400", "color": "#DDDDDD"},
    "cta": {
        "backgroundColor": "#097fb3",
        "borderRadius": "20px",
        "padding": "10px 20px",
        "color": "#DDDDDD",
    },
}

DEFAULT_RECS_STYLES = {
    "card": {
        "backgroundColor": "#ffffff",
        "borderRadius": "12px",
        "boxShadow": "0 2px 12px rgba(0,0,0,0.10)",
        "padding": "20px",
    },
    "card_image": {"borderRadius": "8px", "aspectRatio": "auto"},
    "card_title": {"fontSize": "18px", "fontWeight": "600", "color": "#1d1d1d"},
    "card_text": {"fontSize": "14px", "color": "#555555"},
    "card_link": {"color": "#097fb3", "textDecoration": "none", "fontWeight": "500"},
}

SITEMAP_TEMPLATE_V2 = r"""//SimpleSitemap (Experience Template model)
SalesforceInteractions.setLoggingLevel(100);
SalesforceInteractions.updateConsents({
    purpose: SalesforceInteractions.ConsentPurpose.Tracking,
    provider: "Example Consent Manager",
    status: SalesforceInteractions.ConsentStatus.OptIn
});

document.addEventListener(
    SalesforceInteractions.CustomEvents.OnSetAnonymousId, () => {
        SalesforceInteractions.sendEvent({
            user: { attributes: { eventType: 'identity', isAnonymous: 1 } }
        })
    }
);

document.querySelector('html').style.fontSize = '14px';

SalesforceInteractions.init().then(() => {
    const config = {
        global: { onActionEvent: (event) => { return event; } },
        pageTypes: [{
            name: "Homepage",
            isMatch: () => window.location.pathname === '/',
            interaction: { name: "Homepage", eventType: "browse", pageType: "Homepage" },
            contentZones: [
                { name: "Homepage | Hero", selector: "{{HERO_SELECTOR}}" },
                { name: "Homepage | Cards", selector: "{{CARD_SELECTOR}}" }
            ]
        }],
        pageTypeDefault: { name: "Default" }
    };
    SalesforceInteractions.initSitemap(config);
});"""


CARD_EXPERIENCE_TEMPLATE_HTML = r"""<style>
    .sfdcep-recs-carousel {
        width: 100%;
        max-width: 1440px;
        margin: 0 auto;
        display: flex;
        flex-flow: row wrap;
        justify-content: space-evenly;
        padding: 20px 0;
        gap: 20px;
    }
    .sfdcep-recs-card-wrapper {
        width: 22%;
        min-width: 240px;
        flex: 1 1 240px;
    }
    .sfdcep-recs-card {
        height: 100%;
        background: #fff;
        border-radius: 12px;
        overflow: hidden;
        box-shadow: 0 2px 12px rgba(0,0,0,0.10);
        display: flex;
        flex-direction: column;
    }
    .sfdcep-recs-card .cmp-image__image {
        width: 100%;
        height: 200px;
        object-fit: cover;
        display: block;
    }
    .sfdcep-recs-card__content {
        padding: 20px;
        display: flex;
        flex-direction: column;
        gap: 12px;
        flex: 1;
    }
    .sfdcep-recs-card__title {
        font-size: 18px;
        font-weight: 600;
        color: #1d1d1d;
        margin: 0;
        font-family: Arial, Helvetica, sans-serif;
    }
    .sfdcep-recs-card__cta {
        color: #097fb3;
        font-size: 14px;
        text-decoration: none;
        font-weight: 500;
        font-family: Arial, Helvetica, sans-serif;
        display: inline-flex;
        align-items: center;
        gap: 4px;
        margin-top: auto;
    }
    .sfdcep-recs-card__cta:hover {
        text-decoration: underline;
    }
</style>
<div class="sfdcep-recs-carousel">
    {{#each (subVar 'recs')}}
    <div class="sfdcep-recs-card-wrapper">
        <div class="sfdcep-recs-card">
            <div class="cmp-teaser__image">
                {{#if (subVar 'image')}}
                    <img src="{{subVar 'image'}}" class="cmp-image__image" alt="{{subVar 'name'}}">
                {{else}}
                    <img src="https://placehold.co/750x422/e8f4fb/097fb3?text=No+Image" class="cmp-image__image" alt="">
                {{/if}}
            </div>
            <div class="sfdcep-recs-card__content">
                <h3 class="sfdcep-recs-card__title">{{subVar 'name'}}</h3>
                <a class="sfdcep-recs-card__cta" href="{{subVar 'linkUrl'}}" target="_self">Learn More</a>
            </div>
        </div>
    </div>
    {{/each}}
</div>"""


def assemble_sitemap_v2(hero_selector, card_selector):
    """Build the minimal Experience Template-style sitemap JS with hero + card content zones."""
    return (
        SITEMAP_TEMPLATE_V2
        .replace("{{HERO_SELECTOR}}", hero_selector)
        .replace("{{CARD_SELECTOR}}", card_selector or "BODY_CARDS_SELECTOR")
    )


LLM_PROMPT = """You are an expert at adapting website HTML into Salesforce Personalization Handlebars transformers.

You will receive two inputs:
1. TARGET_HTML - The cleaned HTML of the hero element to personalize
2. EXTRACTED_STYLES - Fallback CSS values extracted from the customer's page

=== TASK ===

Adapt TARGET_HTML into a Handlebars transformer HTML snippet. Preserve the
customer's DOM structure, nesting, and CSS class names while replacing content
with the 5 subVar variables listed below.

The output should look like a trimmed version of TARGET_HTML with subVars slotted
into the semantically correct positions — NOT a generic template.

Rules:

1. PRESERVE THE CUSTOMER'S STRUCTURE.
   Keep the tag hierarchy, nesting, wrapper divs, and CSS class names from
   TARGET_HTML. The transformer replaces the original element on the live page,
   so the customer's existing stylesheets will style these class names.
   Do NOT flatten the hierarchy. Do NOT invent generic class names.

2. SLOT THE 5 MANDATORY subVar VARIABLES:
   - {{{{subVar 'BackgroundImageUrl'}}}} — place as an inline style
     background: url('{{{{subVar 'BackgroundImageUrl'}}}}') no-repeat center center / cover;
     on the element where the hero's background image belongs (follow the
     customer's existing pattern from TARGET_HTML).
   - {{{{subVar 'Header'}}}} — text content of the main heading element
   - {{{{subVar 'Subheader'}}}} — text content of the subtitle/description element
   - {{{{subVar 'CallToActionUrl'}}}} — href of a CTA link
   - {{{{subVar 'CallToActionText'}}}} — text of that CTA link
   If TARGET_HTML lacks a CTA link, add one inside the content area styled
   to match using EXTRACTED_STYLES.cta values as inline styles.
   All five variables MUST appear.

3. STRIP REMAINING NOISE.
   Remove any leftover video, audio, modal, script, or interactive elements.
   NEVER remove wrapper or container elements — even if they appear structural-only.
   NEVER remove any element that carries inline styles. Those styles are load-bearing
   visual identity; stripping them destroys the customer's design.
   When in doubt, keep the element and replace only its content with subVars.

4. INLINE STYLES — use sparingly.
   Keep inline styles that already exist in TARGET_HTML. Add inline styles
   only where essential (background image, overlay opacity). Do NOT add a
   <style> block. If you must add fallback styles (e.g. for an added CTA),
   use EXTRACTED_STYLES values as inline style attributes.

=== INPUTS ===
- TARGET_HTML:
{target_html}
- EXTRACTED_STYLES:
{extracted_styles}

=== OUTPUT ===
Output ONLY valid HTML. No <style> block, no JavaScript, no boilerplate,
no markdown fences, no commentary."""


ISSUE_INSTRUCTIONS = {
    "background_image": (
        "BACKGROUND IMAGE: Ensure {{subVar 'BackgroundImageUrl'}} is placed as an "
        "inline style background: url(...) on the appropriate element, following "
        "the customer's pattern from TARGET_HTML."
    ),
    "text_content": (
        "HEADER / SUBHEADER: Ensure the heading uses {{subVar 'Header'}} and the "
        "subtitle uses {{subVar 'Subheader'}}. Preserve the customer's class names "
        "on these elements. If styling is missing, use EXTRACTED_STYLES header and "
        "subheader values as inline style attributes."
    ),
    "cta_missing": (
        "CTA BUTTON: Ensure a visible CTA link is present: "
        "<a href=\"{{subVar 'CallToActionUrl'}}\">{{subVar 'CallToActionText'}}</a>. "
        "If adding a new CTA, style it using EXTRACTED_STYLES cta values as inline styles."
    ),
    "layout_wrong": (
        "LAYOUT: The transformer HTML structure should more closely mirror the tag "
        "hierarchy and nesting in TARGET_HTML. Preserve the customer's wrapper divs, "
        "containers, and layout structure."
    ),
}

CORRECTION_PROMPT = """You are revising a Salesforce Personalization Handlebars transformer HTML snippet.
The user has flagged specific issues.

RULES:
- Fix ONLY the transformer HTML.
- All five subVar Handlebars variables remain MANDATORY.
- Preserve the customer's DOM structure and class names from TARGET_HTML.
- Do NOT add a <style> block. Use inline styles only where TARGET_HTML already has
  them or where essential (e.g. background image).
- Output ONLY the corrected HTML. No JavaScript, no boilerplate, no markdown fences, no commentary.

=== ISSUES TO FIX ===
{issue_list}

{user_note}

=== ORIGINAL INPUTS ===
- TARGET_HTML:
{target_html}
- EXTRACTED_STYLES:
{extracted_styles}

=== YOUR PREVIOUS TRANSFORMER HTML ===
{previous_html}

=== OUTPUT ===
Output ONLY the corrected HTML. No JavaScript, no boilerplate, no markdown fences, no commentary."""


RECS_LLM_PROMPT = """You are an expert at adapting website HTML into Salesforce Personalization Handlebars transformer templates.

You will receive three inputs:
1. CONTAINER_HTML - The outer container element from the customer's site that holds the cards
2. CARD_HTML - The cleaned HTML of one product/recommendation card from the customer's site
3. EXTRACTED_STYLES - Fallback CSS values extracted from the customer's card

=== TASK ===

Produce a complete Handlebars Experience Template. The output must be:

    <container with {{#each}} loop>
        {{#each (subVar 'recs')}}
        <per-card body>
        {{/each}}
    </container>

Use CONTAINER_HTML as the outer shell. Use CARD_HTML as the template source for the
per-card body inside the loop.

Rules:

1. CONTAINER: use CONTAINER_HTML as the outer shell.
   Keep its tag, class names, and existing inline styles. You may add or modify
   inline styles on the container (e.g. background-color, display, gap) to make
   the layout work — this is where layout and background decisions belong.
   Do NOT invent a new container tag or class names.

2. LOOP: wrap the per-card body in {{{{#each (subVar 'recs')}}}}...{{{{/each}}}}
   directly inside the container element. No extra wrapper divs around the loop.

3. CARD BODY: adapt CARD_HTML into the per-card Handlebars body.
   Keep the tag hierarchy, nesting, wrapper divs, CSS class names, and HTML
   attributes (width, height, aria-*, decoding, loading, etc.) from CARD_HTML.
   Do NOT flatten the hierarchy. Do NOT invent generic class names.

4. SLOT EXACTLY 3 subVar VARIABLES - NO OTHERS, NO EXCEPTIONS:
   - {{{{subVar 'image'}}}} - src of the card's product image
   - {{{{subVar 'name'}}}} - text content of the card's title/heading
   - {{{{subVar 'linkUrl'}}}} - href of the card's link

   ALL THREE MUST APPEAR. Do NOT add any other subVar variables (no 'price',
   'description', 'category', 'rating', etc.) - the data binding only provides
   these three fields. Inventing other variables breaks the live integration.

5. IMAGE IS MANDATORY - preserve the customer's image element and wrapper chain.
   If CARD_HTML has an <img>, keep that <img> tag's class names and ALL of its
   parent wrappers (e.g. <picture>, <figure>, anchor wrappers, container divs)
   exactly as they appear in CARD_HTML. Set src="{{{{subVar 'image'}}}}" and
   alt="{{{{subVar 'name'}}}}". No conditionals, no {{{{#if}}}}, no fallback
   patterns — the image field is always populated.

   Example - if CARD_HTML has:
       <picture class="x-pic"><a class="x-link"><img class="x-img" src="..." alt="..."></a></picture>
   Output:
       <picture class="x-pic"><a class="x-link" href="{{{{subVar 'linkUrl'}}}}"><img class="x-img" src="{{{{subVar 'image'}}}}" alt="{{{{subVar 'name'}}}}"></a></picture>

   Do NOT add inline width/display styles to the <img>. Do NOT drop wrapper elements like <picture>.

   If CARD_HTML has no <img> at all, insert at the top of the card body:
   <img src="{{{{subVar 'image'}}}}" alt="{{{{subVar 'name'}}}}">

6. PRESERVE THE CARD'S CTA ELEMENT.
   Keep the card's primary CTA link or button. Rewrite its href to {{{{subVar 'linkUrl'}}}},
   keep its tag, class names, inline styles, and visible text exactly as they appear.

7. REMOVE PER-CARD DATA NOT MAPPED TO THE 3 VARIABLES.
   Remove ALL element nodes carrying per-card data not mapped to image/name/linkUrl.
   This includes: <p> description paragraphs, prices, ratings, dates, author,
   read-time, category labels, overlay content sections, and any static text copied
   verbatim from CARD_HTML. Do NOT preserve them as static text.
   Do NOT invent subVars for them. Remove empty wrapper divs left behind.

8. STRIP REMAINING NOISE.
   Remove video, audio, modal, script, popup, and interactive elements not part of
   the card's link or CTA. Remove empty wrapper divs that result from rule 7.
   NEVER remove elements that carry inline styles. Those styles are load-bearing
   visual identity. NEVER remove structural wrapper or container elements.

9. INLINE STYLES - use sparingly on card elements.
   Keep inline styles already in CARD_HTML. Add inline styles only where essential.
   Do NOT add a <style> block.

=== INPUTS ===
- CONTAINER_HTML:
{container_html}
- CARD_HTML:
{card_html}
- EXTRACTED_STYLES:
{extracted_styles}

=== OUTPUT ===
Return a single HTML block. Nothing before it, nothing after it.
No explanations, no reasoning, no alternatives, no self-corrections.
Exactly 3 subVar variables: image, name, linkUrl. No <style> block, no JavaScript,
no markdown fences."""


RECS_ISSUE_INSTRUCTIONS = {
    "container_layout": (
        "CONTAINER LAYOUT: Fix the outer container's layout — correct the flex/grid "
        "structure, column arrangement, or spacing so cards display in the intended row/grid pattern. "
        "Use CONTAINER_HTML as the reference."
    ),
    "container_styling": (
        "CONTAINER STYLING: Fix the outer container's visual styling — background color, "
        "padding, border, or other cosmetic properties. Apply changes as inline styles on "
        "the container element."
    ),
    "card_layout": (
        "CARD LAYOUT: The card structure should more closely mirror CARD_HTML. Preserve the "
        "customer's wrapper divs, class names, and nesting."
    ),
    "card_content": (
        "CARD CONTENT: Fix content issues inside the card — remove duplicate elements, "
        "strip static text that should have been removed, ensure all three subVar variables "
        "(image, name, linkUrl) are correctly placed and rendering."
    ),
}


RECS_CORRECTION_PROMPT = """You are revising a Salesforce Personalization Handlebars Recommendations Experience Template.
The user has flagged specific issues.

RULES:
- Output the complete corrected template: container + {{#each}} loop + per-card body.
- You may modify the container's inline styles (e.g. background-color, padding, layout)
  when the feedback calls for it. Keep the container's tag and class names.
- EXACTLY 3 subVar variables: image, name, linkUrl. NO OTHERS.
- The image must use {{subVar 'image'}} with an if/else fallback to
  https://placehold.co/750x422/eeeeee/aaaaaa?text=No+Image. Preserve the
  customer's <img> class names and parent wrappers exactly as they appear in CARD_HTML.
- Preserve the customer's card DOM structure and class names from CARD_HTML.
- Preserve the card's primary CTA element. Rewrite its href to {{subVar 'linkUrl'}},
  keep its tag, class names, inline styles, and visible text.
- Remove ALL per-card data not mapped to image/name/linkUrl: <p> descriptions,
  prices, ratings, dates, overlay content, static text copied from CARD_HTML.
  Do not preserve as static text. Do not invent subVars. Remove empty wrappers left behind.
- Do NOT add a <style> block. Use inline styles only where essential.
- Output ONLY the corrected complete template. No JavaScript, no boilerplate, no
  markdown fences, no commentary.

=== ISSUES TO FIX ===
{issue_list}

{user_note}

=== ORIGINAL INPUTS ===
- CONTAINER_HTML:
{container_html}
- CARD_HTML:
{card_html}
- EXTRACTED_STYLES:
{extracted_styles}

=== YOUR PREVIOUS TEMPLATE ===
{previous_template}

=== OUTPUT ===
Output ONLY the corrected complete template. No JavaScript, no boilerplate, no markdown fences, no commentary."""


def fetch_page(url):
    resp = requests.get(url, headers={"User-Agent": BROWSER_UA, "Accept": "text/html"}, timeout=25, allow_redirects=True)
    resp.raise_for_status()
    return resp.text, resp.url


def best_selector(tag):
    if tag.get("id"):
        return f"#{tag['id']}"
    classes = [c for c in tag.get("class", []) if re.match(r"^[-_a-zA-Z0-9]+$", c)]
    if classes:
        return f"{tag.name}.{'.'.join(classes[:3])}"
    return tag.name


def detect_hero(soup):
    candidates = soup.body.find_all(["section", "div"], limit=200) if soup.body else []

    # Pass 1: background-image with text content — prefer elements that carry both.
    first_bg = None
    for el in candidates:
        style = el.get("style", "")
        if re.search(r"background(-image)?\s*:", style, re.I):
            if first_bg is None:
                first_bg = el
            if el.find(["h1", "h2"]) or el.find("a"):
                return el
    if first_bg is not None:
        return first_bg

    for el in candidates:
        cls = " ".join(el.get("class", []))
        if HERO_KEYWORDS.search(cls):
            return el

    for el in candidates:
        if el.find(["h1", "h2"]) and el.find("a"):
            return el

    first_section = soup.find("section")
    if first_section:
        return first_section

    return None


def _structural_signature(el):
    """Lightweight fingerprint — tag + sorted class set — used to spot repeating siblings."""
    classes = tuple(sorted(el.get("class", [])))
    return (el.name, classes)


def _card_has_content(child):
    """A plausible card has an image and a link or heading."""
    has_img = child.find("img") is not None
    has_link_or_heading = child.find("a") is not None or child.find(["h2", "h3", "h4"]) is not None
    return has_img and has_link_or_heading


def _score_repeating_container(container):
    """Return (best_card_signature, sample_card) if container has >=3 similar cardlike children."""
    children = [c for c in container.find_all(True, recursive=False) if c.name]
    if len(children) < 3:
        return None

    sig_groups = {}
    for child in children:
        sig = _structural_signature(child)
        sig_groups.setdefault(sig, []).append(child)

    for sig, group in sig_groups.items():
        if len(group) >= 3 and all(_card_has_content(c) for c in group[:3]):
            return sig, group[0]
    return None


NAV_SIGNALS = re.compile(r"\b(nav|menu|navigation|header)\b", re.I)


def _is_nav_container(el):
    if el.name in ("nav", "header"):
        return True
    cls_id = " ".join(el.get("class", [])) + " " + (el.get("id") or "")
    if NAV_SIGNALS.search(cls_id):
        return True
    for ancestor in el.parents:
        if ancestor.name in ("nav", "header"):
            return True
        anc_cls = " ".join(ancestor.get("class", []))
        if NAV_SIGNALS.search(anc_cls):
            return True
    return False


def detect_recs(soup):
    """
    Find a repeating product/card grid. Returns dict with container_selector,
    card_selector, exemplar_html — or None if nothing scores.
    """
    if not soup.body:
        return None

    containers = soup.body.find_all(["ul", "ol", "div", "section"], limit=200)

    # Pass 1: structural signal — 3+ similar children with img + link/heading.
    for container in containers:
        if _is_nav_container(container):
            continue
        result = _score_repeating_container(container)
        if result:
            _sig, exemplar = result
            return {
                "containerSelector": best_selector(container),
                "cardSelector": best_selector(exemplar),
                "exemplarOuterHtml": str(exemplar),
                "containerOuterHtml": str(container),
            }

    # Pass 2: keyword + image structure.
    for container in containers:
        if _is_nav_container(container):
            continue
        cls_id = " ".join(container.get("class", [])) + " " + (container.get("id") or "")
        if not RECS_KEYWORDS.search(cls_id):
            continue
        children = [c for c in container.find_all(True, recursive=False) if c.name]
        with_img = [c for c in children if c.find("img")]
        if len(with_img) >= 3:
            return {
                "containerSelector": best_selector(container),
                "cardSelector": best_selector(with_img[0]),
                "exemplarOuterHtml": str(with_img[0]),
                "containerOuterHtml": str(container),
            }

    return None


def parse_inline_style(style_str):
    out = {}
    if not style_str:
        return out
    for decl in style_str.split(";"):
        decl = decl.strip()
        if ":" not in decl:
            continue
        prop, val = decl.split(":", 1)
        out[prop.strip().lower()] = val.strip()
    return out


def collect_hero_classes(hero):
    class_set = set()
    for c in hero.get("class", []):
        class_set.add(c)
    for child in hero.find_all(True, recursive=False):
        for c in child.get("class", []):
            class_set.add(c)
    return class_set


def selector_matches(selector_text, hero_classes):
    sel = selector_text.lower()
    for cls in hero_classes:
        if f".{cls.lower()}" in sel:
            return True
    return False


def infer_bucket(selector_text, declarations):
    s = selector_text.lower()
    if " a" in s or s.endswith("a") or ".cta" in s or ".btn" in s:
        return "cta"
    if "h1" in s or "title" in s or "header" in s:
        return "header"
    if "h2" in s or "subheader" in s or "subtitle" in s or " p" in s:
        return "subheader"
    return "banner"


def infer_bucket_card(selector_text, declarations):
    s = selector_text.lower()
    if "img" in s or ".image" in s or ".thumb" in s:
        return "card_image"
    if "h2" in s or "h3" in s or "h4" in s or "title" in s or "name" in s:
        return "card_title"
    if " a" in s or s.endswith("a") or ".link" in s or ".cta" in s or ".btn" in s:
        return "card_link"
    if " p" in s or ".price" in s or ".desc" in s or ".body" in s or ".text" in s:
        return "card_text"
    return "card"


NOISE_TAGS = {
    "script", "noscript", "iframe", "link", "meta",
    "video", "audio", "source", "track",
    "button", "picture",
}

RECS_NOISE_TAGS = {
    "script", "noscript", "iframe", "meta",
    "video", "audio", "track",
}

CAROUSEL_SLIDE_CLASSES = {
    "swiper-slide",
    "slick-slide",
    "owl-item",
    "flickity-cell",
    "splide__slide",
    "glide__slide",
    "carousel-item",
    "cycle-slide",
    "tns-item",
}

CAROUSEL_OUTER_CLASSES = {
    "swiper",
    "swiper-initialized",
    "swiper-container",
    "swiper-container-initialized",
    "slick-slider",
    "slick-initialized",
    "owl-carousel",
    "flickity-enabled",
    "splide",
    "glide",
    "carousel",
}

CAROUSEL_TRACK_CLASSES = {
    "swiper-wrapper",
    "swiper-container",
    "slick-track",
    "slick-list",
    "owl-stage",
    "owl-stage-outer",
    "flickity-viewport",
    "flickity-slider",
    "splide__list",
    "glide__slides",
    "embla__container",
    "tns-inner",
    "tns-ovh",
    "carousel-inner",
}

CAROUSEL_CHROME_CLASSES = {
    "swiper-pagination",
    "swiper-button-next",
    "swiper-button-prev",
    "swiper-notification",
    "swiper-scrollbar",
    "slick-dots",
    "slick-arrow",
    "slick-prev",
    "slick-next",
    "owl-nav",
    "owl-dots",
    "flickity-page-dots",
    "flickity-prev-next-button",
    "splide__arrows",
    "splide__pagination",
    "glide__arrows",
    "glide__bullets",
    "carousel-indicators",
    "carousel-control-prev",
    "carousel-control-next",
}


def _sanitize(raw_html, noise_tags):
    soup = BeautifulSoup(raw_html, "html.parser")

    for tag in list(soup.find_all(noise_tags)):
        tag.decompose()

    for comment in list(soup.find_all(string=lambda t: isinstance(t, Comment))):
        comment.extract()

    for tag in list(soup.find_all(True)):
        if not tag.parent:
            continue
        classes = " ".join(tag.get("class", []))
        if "modal" in classes.lower() or tag.get("aria-hidden") == "true":
            tag.decompose()
            continue
        for attr in list(tag.attrs):
            if attr.startswith("data-"):
                del tag[attr]

    return str(soup).strip()


def _strip_carousel_chrome(soup):
    """Remove carousel navigation/pagination elements entirely."""
    for tag in list(soup.find_all(True)):
        if not tag.parent:
            continue
        tag_classes = set(tag.get("class", []))
        if tag_classes & CAROUSEL_CHROME_CLASSES:
            tag.decompose()


def _unwrap_carousel_tracks(soup):
    """Unwrap carousel track/stage wrappers, promoting their children up one level."""
    for tag in list(soup.find_all(True)):
        if not tag.parent:
            continue
        tag_classes = set(tag.get("class", []))
        if tag_classes & CAROUSEL_TRACK_CLASSES:
            tag.unwrap()


def _collapse_hero_carousel(soup):
    """
    Collapse a hero carousel to a single slide. Detects carousel structure,
    keeps only the first slide, strips chrome and track/outer wrappers.
    """
    _strip_carousel_chrome(soup)

    slides = [
        tag for tag in soup.find_all(True)
        if tag.parent and set(tag.get("class", [])) & CAROUSEL_SLIDE_CLASSES
    ]
    if len(slides) > 1:
        for slide in slides[1:]:
            slide.decompose()

    _unwrap_carousel_tracks(soup)

    for tag in list(soup.find_all(True)):
        if not tag.parent:
            continue
        tag_classes = set(tag.get("class", []))
        if tag_classes & CAROUSEL_OUTER_CLASSES:
            tag.unwrap()


def sanitize_html(raw_html):
    """Strip interactive/media noise from TARGET_HTML, collapse hero carousels."""
    soup = BeautifulSoup(raw_html, "html.parser")

    for tag in list(soup.find_all(NOISE_TAGS)):
        tag.decompose()

    for comment in list(soup.find_all(string=lambda t: isinstance(t, Comment))):
        comment.extract()

    _collapse_hero_carousel(soup)

    for tag in list(soup.find_all(True)):
        if not tag.parent:
            continue
        classes = " ".join(tag.get("class", []))
        if "modal" in classes.lower() or tag.get("aria-hidden") == "true":
            tag.decompose()
            continue
        for attr in list(tag.attrs):
            if attr.startswith("data-"):
                del tag[attr]

    return str(soup).strip()


def sanitize_card_html(raw_html):
    """Card sanitizer: strip carousel chrome, unwrap track wrappers, remove media noise."""
    soup = BeautifulSoup(raw_html, "html.parser")

    for tag in list(soup.find_all(RECS_NOISE_TAGS)):
        tag.decompose()

    for comment in list(soup.find_all(string=lambda t: isinstance(t, Comment))):
        comment.extract()

    _strip_carousel_chrome(soup)

    for tag in list(soup.find_all(True)):
        if not tag.parent:
            continue
        classes = " ".join(tag.get("class", []))
        if "modal" in classes.lower():
            tag.decompose()
            continue
        for attr in list(tag.attrs):
            if attr.startswith("data-"):
                del tag[attr]

    return str(soup).strip()


def _usable(val):
    """Reject CSS variable references, currentColor, and empty values."""
    if not val:
        return False
    v = val.strip().lower()
    return not v.startswith("var(") and v != "currentcolor"


def pick_style_values(base, declarations, bucket):
    if bucket == "banner":
        if "background-color" in declarations and _usable(declarations["background-color"]):
            base["banner"]["backgroundColor"] = declarations["background-color"]
        elif "background" in declarations and _usable(declarations["background"]):
            base["banner"]["backgroundColor"] = declarations["background"]
        if "font-family" in declarations and _usable(declarations["font-family"]):
            base["banner"]["fontFamily"] = declarations["font-family"]
    elif bucket == "header":
        if "color" in declarations and _usable(declarations["color"]):
            base["header"]["color"] = declarations["color"]
        if "font-size" in declarations and _usable(declarations["font-size"]):
            base["header"]["fontSize"] = declarations["font-size"]
        if "font-weight" in declarations and _usable(declarations["font-weight"]):
            base["header"]["fontWeight"] = declarations["font-weight"]
    elif bucket == "subheader":
        if "color" in declarations and _usable(declarations["color"]):
            base["subheader"]["color"] = declarations["color"]
        if "font-size" in declarations and _usable(declarations["font-size"]):
            base["subheader"]["fontSize"] = declarations["font-size"]
        if "font-weight" in declarations and _usable(declarations["font-weight"]):
            base["subheader"]["fontWeight"] = declarations["font-weight"]
    elif bucket == "cta":
        if "background-color" in declarations and _usable(declarations["background-color"]):
            base["cta"]["backgroundColor"] = declarations["background-color"]
        elif "background" in declarations and _usable(declarations["background"]):
            base["cta"]["backgroundColor"] = declarations["background"]
        if "border-radius" in declarations and _usable(declarations["border-radius"]):
            base["cta"]["borderRadius"] = declarations["border-radius"]
        if "padding" in declarations and _usable(declarations["padding"]):
            base["cta"]["padding"] = declarations["padding"]
        if "color" in declarations and _usable(declarations["color"]):
            base["cta"]["color"] = declarations["color"]


def pick_recs_style_values(base, declarations, bucket):
    if bucket == "card":
        if "background-color" in declarations and _usable(declarations["background-color"]):
            base["card"]["backgroundColor"] = declarations["background-color"]
        elif "background" in declarations and _usable(declarations["background"]):
            base["card"]["backgroundColor"] = declarations["background"]
        if "border-radius" in declarations and _usable(declarations["border-radius"]):
            base["card"]["borderRadius"] = declarations["border-radius"]
        if "box-shadow" in declarations and _usable(declarations["box-shadow"]):
            base["card"]["boxShadow"] = declarations["box-shadow"]
        if "padding" in declarations and _usable(declarations["padding"]):
            base["card"]["padding"] = declarations["padding"]
    elif bucket == "card_image":
        if "border-radius" in declarations and _usable(declarations["border-radius"]):
            base["card_image"]["borderRadius"] = declarations["border-radius"]
        if "aspect-ratio" in declarations and _usable(declarations["aspect-ratio"]):
            base["card_image"]["aspectRatio"] = declarations["aspect-ratio"]
    elif bucket == "card_title":
        if "color" in declarations and _usable(declarations["color"]):
            base["card_title"]["color"] = declarations["color"]
        if "font-size" in declarations and _usable(declarations["font-size"]):
            base["card_title"]["fontSize"] = declarations["font-size"]
        if "font-weight" in declarations and _usable(declarations["font-weight"]):
            base["card_title"]["fontWeight"] = declarations["font-weight"]
    elif bucket == "card_text":
        if "color" in declarations and _usable(declarations["color"]):
            base["card_text"]["color"] = declarations["color"]
        if "font-size" in declarations and _usable(declarations["font-size"]):
            base["card_text"]["fontSize"] = declarations["font-size"]
    elif bucket == "card_link":
        if "color" in declarations and _usable(declarations["color"]):
            base["card_link"]["color"] = declarations["color"]
        if "text-decoration" in declarations and _usable(declarations["text-decoration"]):
            base["card_link"]["textDecoration"] = declarations["text-decoration"]
        if "font-weight" in declarations and _usable(declarations["font-weight"]):
            base["card_link"]["fontWeight"] = declarations["font-weight"]


def extract_matching_rules(css_text, hero_classes):
    try:
        sheet = cssutils.parseString(css_text, validate=False)
    except Exception:
        return []
    out = []
    for rule in sheet:
        if rule.type != rule.STYLE_RULE:
            continue
        sel = rule.selectorText
        if not selector_matches(sel, hero_classes):
            continue
        declarations = {}
        for prop in rule.style:
            declarations[prop.name.lower()] = prop.value
        out.append((sel, declarations))
    return out


def derive_customer_name(page_url):
    hostname = urlparse(page_url).hostname or ""
    hostname = re.sub(r"^www\.", "", hostname, flags=re.I)
    root = hostname.split(".")[0] or "Customer"
    normalized = re.sub(r"[^a-zA-Z0-9]+", " ", root).strip()
    if not normalized:
        return "Customer"
    return "".join(w.capitalize() for w in normalized.split())


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/detect", methods=["POST"])
def detect():
    data = request.get_json(silent=True) or {}
    page_url = (data.get("pageUrl") or "").strip()
    if not page_url:
        return jsonify(error="pageUrl is required."), 400

    try:
        html, final_url = fetch_page(page_url)
    except Exception as e:
        return jsonify(error=f"Failed to fetch page: {e}"), 502

    soup = BeautifulSoup(html, "html.parser")
    hero = detect_hero(soup)

    if not hero:
        return jsonify(error="Could not detect a hero element on this page."), 404

    recs = detect_recs(soup)

    return jsonify(
        pageUrl=final_url,
        selector=best_selector(hero),
        outerHtml=str(hero),
        recs=recs,
    )


def _resolve_selector(soup, selector):
    if selector.startswith("#"):
        return soup.find(id=selector[1:])
    if selector.startswith("."):
        parts = selector[1:].split(".")
        return soup.find(class_=lambda c: c and all(p in c.split() for p in parts))
    return soup.select_one(selector)


@app.route("/extract-styles", methods=["POST"])
def extract_styles():
    data = request.get_json(silent=True) or {}
    page_url = (data.get("pageUrl") or "").strip()
    target_selector = (data.get("targetSelector") or "").strip()
    mode = (data.get("mode") or "hero").strip().lower()

    if not page_url:
        return jsonify(error="pageUrl is required."), 400
    if not target_selector:
        return jsonify(error="targetSelector is required."), 400

    try:
        html, final_url = fetch_page(page_url)
    except Exception as e:
        return jsonify(error=f"Failed to fetch page: {e}"), 502

    soup = BeautifulSoup(html, "html.parser")
    target = _resolve_selector(soup, target_selector)

    if mode == "recs":
        if not target:
            return jsonify(extractedStyles=json.loads(json.dumps(DEFAULT_RECS_STYLES)))

        extracted = json.loads(json.dumps(DEFAULT_RECS_STYLES))
        target_classes = collect_hero_classes(target)

        inline = parse_inline_style(target.get("style", ""))
        pick_recs_style_values(extracted, inline, "card")
        for child in target.find_all(True, recursive=False):
            child_inline = parse_inline_style(child.get("style", ""))
            bucket = infer_bucket_card(child.name or "", child_inline)
            pick_recs_style_values(extracted, child_inline, bucket)

        for style_tag in soup.find_all("style"):
            css_text = style_tag.string or ""
            for sel, declarations in extract_matching_rules(css_text, target_classes):
                pick_recs_style_values(extracted, declarations, infer_bucket_card(sel, declarations))

        for link in soup.find_all("link", rel="stylesheet"):
            href = link.get("href")
            if not href:
                continue
            try:
                abs_url = urljoin(final_url, href)
                resp = requests.get(abs_url, headers={"User-Agent": BROWSER_UA}, timeout=15)
                if resp.status_code == 200:
                    for sel, declarations in extract_matching_rules(resp.text, target_classes):
                        pick_recs_style_values(extracted, declarations, infer_bucket_card(sel, declarations))
            except Exception:
                continue

        return jsonify(extractedStyles=extracted)

    # hero mode (default, unchanged behavior)
    hero = target or detect_hero(soup)

    extracted = json.loads(json.dumps(DEFAULT_STYLES))

    if hero:
        hero_classes = collect_hero_classes(hero)

        inline = parse_inline_style(hero.get("style", ""))
        pick_style_values(extracted, inline, "banner")
        for child in hero.find_all(True, recursive=False):
            child_inline = parse_inline_style(child.get("style", ""))
            tag_name = child.name or ""
            bucket = infer_bucket(tag_name, child_inline)
            pick_style_values(extracted, child_inline, bucket)

        for style_tag in soup.find_all("style"):
            css_text = style_tag.string or ""
            for sel, declarations in extract_matching_rules(css_text, hero_classes):
                pick_style_values(extracted, declarations, infer_bucket(sel, declarations))

        for link in soup.find_all("link", rel="stylesheet"):
            href = link.get("href")
            if not href:
                continue
            try:
                abs_url = urljoin(final_url, href)
                resp = requests.get(abs_url, headers={"User-Agent": BROWSER_UA}, timeout=15)
                if resp.status_code == 200:
                    for sel, declarations in extract_matching_rules(resp.text, hero_classes):
                        pick_style_values(extracted, declarations, infer_bucket(sel, declarations))
            except Exception:
                continue

    return jsonify(extractedStyles=extracted)


@app.route("/assemble-sitemap", methods=["POST"])
def assemble_sitemap_endpoint():
    data = request.get_json(silent=True) or {}
    hero_selector = (data.get("heroSelector") or "").strip()
    rec_selector = (data.get("recSelector") or "").strip()

    if not hero_selector:
        return jsonify(error="heroSelector is required."), 400

    sitemap_js = assemble_sitemap_v2(hero_selector, rec_selector)
    return jsonify(sitemap=sitemap_js)


DEFAULT_HERO_TEMPLATE_HTML = r"""<style>
    .sfdcep-hero {
        position: relative;
        width: 100%;
        min-height: 480px;
        display: flex;
        align-items: center;
        background: url('{{subVar 'BackgroundImageUrl'}}') no-repeat center center / cover;
        font-family: Arial, Helvetica, sans-serif;
    }
    .sfdcep-hero__overlay {
        position: absolute;
        inset: 0;
        background: rgba(0,0,0,0.45);
    }
    .sfdcep-hero__content {
        position: relative;
        z-index: 1;
        max-width: 640px;
        padding: 48px 40px;
        color: #ffffff;
    }
    .sfdcep-hero__heading {
        font-size: 40px;
        font-weight: 700;
        line-height: 1.15;
        margin: 0 0 16px;
        color: #ffffff;
    }
    .sfdcep-hero__subheading {
        font-size: 18px;
        font-weight: 400;
        line-height: 1.5;
        margin: 0 0 28px;
        color: #eeeeee;
    }
    .sfdcep-hero__cta {
        display: inline-block;
        padding: 12px 28px;
        background: #097fb3;
        color: #ffffff;
        font-size: 15px;
        font-weight: 600;
        text-decoration: none;
        border-radius: 4px;
    }
    .sfdcep-hero__cta:hover {
        background: #065f87;
    }
</style>
<div class="sfdcep-hero" style="background-image:url('{{subVar 'BackgroundImageUrl'}}')">
    <div class="sfdcep-hero__overlay"></div>
    <div class="sfdcep-hero__content">
        <h1 class="sfdcep-hero__heading">{{subVar 'Header'}}</h1>
        <p class="sfdcep-hero__subheading">{{subVar 'Subheader'}}</p>
        <a class="sfdcep-hero__cta" href="{{subVar 'CallToActionUrl'}}">{{subVar 'CallToActionText'}}</a>
    </div>
</div>"""


@app.route("/hero-template", methods=["POST"])
def hero_template_endpoint():
    return jsonify(heroTemplate=DEFAULT_HERO_TEMPLATE_HTML)


@app.route("/recommendations-template", methods=["POST"])
def recommendations_template_endpoint():
    return jsonify(recTemplate=CARD_EXPERIENCE_TEMPLATE_HTML)


@app.route("/generate", methods=["POST"])
def generate():
    data = request.get_json(silent=True) or {}
    page_url = (data.get("pageUrl") or "").strip()
    target_html = data.get("targetHtml") or ""
    target_selector = (data.get("targetSelector") or "").strip()
    extracted_styles = data.get("extractedStyles") or DEFAULT_STYLES
    customer_name = (data.get("customerName") or "").strip()

    if not page_url:
        return jsonify(error="pageUrl is required."), 400
    if not target_html.strip():
        return jsonify(error="targetHtml is required."), 400
    if not target_selector:
        return jsonify(error="targetSelector is required."), 400

    if not customer_name:
        customer_name = derive_customer_name(page_url)

    try:
        clean_html = sanitize_html(target_html)
    except Exception:
        clean_html = target_html

    prompt = LLM_PROMPT.format(
        target_html=clean_html,
        extracted_styles=json.dumps(extracted_styles, indent=2),
    )

    last_err = None
    result = None
    for attempt in range(3):
        try:
            result = llm.invoke(prompt)
            break
        except Exception as e:
            last_err = e
            if attempt < 2:
                time.sleep(2 ** attempt)
    if result is None:
        return jsonify(error=_llm_error_message(last_err)), 502

    hero_html = result if isinstance(result, str) else str(result)
    hero_html = strip_markdown_fences(hero_html)
    hero_html = inline_extracted_styles(hero_html, extracted_styles)

    return jsonify(heroTemplate=hero_html)


def _llm_error_message(err):
    msg = str(err) if err else ""
    if "503" in msg or "timeout" in msg.lower():
        return (
            "The AI service timed out \u2014 this can happen with large or complex "
            "hero elements. Try again, or select a simpler parent element with "
            "fewer nested containers if the problem persists."
        )
    return f"LLM generation failed: {msg}"


_EXTRACTED_STYLES_LITERAL = re.compile(
    r"\{\{\s*EXTRACTED_STYLES\.(\w+)\.(\w+)\s*\}\}"
)


def inline_extracted_styles(html, styles):
    """Replace any leaked {{EXTRACTED_STYLES.bucket.key}} tokens with actual values."""
    if not html or not styles:
        return html

    def _sub(match):
        bucket, key = match.group(1), match.group(2)
        return str(styles.get(bucket, {}).get(key, ""))

    return _EXTRACTED_STYLES_LITERAL.sub(_sub, html)


_PLACEHOLDER_LITERAL = re.compile(r"<placeholder[^>]*>", re.IGNORECASE)
_RECS_ALLOWED_SUBVARS = {"image", "name", "linkUrl"}
_SUBVAR_TOKEN = re.compile(r"\{\{\s*subVar\s+['\"]([\w]+)['\"]\s*\}\}")
_SUBVAR_IF_BLOCK = re.compile(
    r"\{\{#if\s*\(\s*subVar\s+['\"]([\w]+)['\"]\s*\)\s*\}\}"
    r"(.*?)"
    r"(?:\{\{else\}\}(.*?))?"
    r"\{\{/if\}\}",
    re.DOTALL,
)


def sanitize_recs_output(html):
    """
    Defensive cleanup of recs LLM output:
    - Strip leaked <placeholder ...> meta-language literals.
    - Remove {{#if (subVar 'X')}}...{{/if}} blocks for variables outside the allowed set
      (image/name/linkUrl), keeping only the 'else' branch if present.
    - Replace stray {{subVar 'X'}} tokens for disallowed names with empty string.
    """
    if not html:
        return html

    cleaned = _PLACEHOLDER_LITERAL.sub("", html)

    def _strip_disallowed_if(match):
        var_name = match.group(1)
        if var_name in _RECS_ALLOWED_SUBVARS:
            return match.group(0)
        else_branch = match.group(3) or ""
        return else_branch

    cleaned = _SUBVAR_IF_BLOCK.sub(_strip_disallowed_if, cleaned)

    def _strip_disallowed_token(match):
        var_name = match.group(1)
        return match.group(0) if var_name in _RECS_ALLOWED_SUBVARS else ""

    cleaned = _SUBVAR_TOKEN.sub(_strip_disallowed_token, cleaned)
    return cleaned


def strip_markdown_fences(text):
    text = text.strip()
    if text.startswith("```"):
        first_nl = text.index("\n") if "\n" in text else len(text)
        text = text[first_nl + 1:]
        last_fence = text.rfind("```")
        if last_fence != -1:
            text = text[:last_fence]
        text = text.strip()
    return text


@app.route("/regenerate", methods=["POST"])
def regenerate():
    data = request.get_json(silent=True) or {}
    page_url = (data.get("pageUrl") or "").strip()
    target_html = data.get("targetHtml") or ""
    target_selector = (data.get("targetSelector") or "").strip()
    extracted_styles = data.get("extractedStyles") or DEFAULT_STYLES
    previous_output = data.get("previousOutput") or ""
    issues = data.get("issues") or []
    feedback_note = (data.get("feedbackNote") or "").strip()
    customer_name = (data.get("customerName") or "").strip()

    if not previous_output.strip():
        return jsonify(error="previousOutput is required."), 400

    if not customer_name:
        customer_name = derive_customer_name(page_url)

    previous_html = previous_output.strip()

    issue_lines = []
    for key in issues:
        instruction = ISSUE_INSTRUCTIONS.get(key)
        if instruction:
            issue_lines.append(f"- {instruction}")

    if not issue_lines and not feedback_note:
        return jsonify(error="Select an issue or provide feedback text."), 400

    user_note_section = ""
    if feedback_note:
        user_note_section = f"=== ADDITIONAL USER FEEDBACK ===\n{feedback_note}"

    try:
        clean_html = sanitize_html(target_html)
    except Exception:
        clean_html = target_html

    prompt = CORRECTION_PROMPT.format(
        issue_list="\n".join(issue_lines),
        user_note=user_note_section,
        target_html=clean_html,
        extracted_styles=json.dumps(extracted_styles, indent=2),
        previous_html=previous_html,
    )

    last_err = None
    result = None
    for attempt in range(3):
        try:
            result = llm.invoke(prompt)
            break
        except Exception as e:
            last_err = e
            if attempt < 2:
                time.sleep(2 ** attempt)
    if result is None:
        return jsonify(error=_llm_error_message(last_err)), 502

    corrected_html = result if isinstance(result, str) else str(result)
    corrected_html = strip_markdown_fences(corrected_html)
    corrected_html = inline_extracted_styles(corrected_html, extracted_styles)

    return jsonify(heroTemplate=corrected_html)


@app.route("/generate-recs", methods=["POST"])
def generate_recs():
    data = request.get_json(silent=True) or {}
    page_url = (data.get("pageUrl") or "").strip()
    card_html = data.get("cardHtml") or ""
    container_html = data.get("containerHtml") or ""
    extracted_styles = data.get("extractedStyles") or DEFAULT_RECS_STYLES

    if not page_url:
        return jsonify(error="pageUrl is required."), 400
    if not card_html.strip():
        return jsonify(error="cardHtml is required."), 400
    if not container_html.strip():
        return jsonify(error="containerHtml is required."), 400

    try:
        clean_card_html = sanitize_card_html(card_html)
        clean_container_html = sanitize_card_html(container_html)
    except Exception:
        clean_card_html = card_html
        clean_container_html = container_html

    prompt = RECS_LLM_PROMPT.format(
        container_html=clean_container_html,
        card_html=clean_card_html,
        extracted_styles=json.dumps(extracted_styles, indent=2),
    )

    last_err = None
    result = None
    for attempt in range(3):
        try:
            result = llm.invoke(prompt)
            break
        except Exception as e:
            last_err = e
            if attempt < 2:
                time.sleep(2 ** attempt)
    if result is None:
        return jsonify(error=_llm_error_message(last_err)), 502

    full_template = result if isinstance(result, str) else str(result)
    full_template = strip_markdown_fences(full_template)
    full_template = inline_extracted_styles(full_template, extracted_styles)
    full_template = sanitize_recs_output(full_template)

    return jsonify(recsTemplate=full_template, cardBody=full_template)


@app.route("/regenerate-recs", methods=["POST"])
def regenerate_recs():
    data = request.get_json(silent=True) or {}
    container_html = data.get("containerHtml") or ""
    card_html = data.get("cardHtml") or ""
    extracted_styles = data.get("extractedStyles") or DEFAULT_RECS_STYLES
    previous_template = data.get("previousTemplate") or ""
    issues = data.get("issues") or []
    feedback_note = (data.get("feedbackNote") or "").strip()

    if not previous_template.strip():
        return jsonify(error="previousTemplate is required."), 400

    issue_lines = []
    for key in issues:
        instruction = RECS_ISSUE_INSTRUCTIONS.get(key)
        if instruction:
            issue_lines.append(f"- {instruction}")

    if not issue_lines and not feedback_note:
        return jsonify(error="Select an issue or provide feedback text."), 400

    user_note_section = ""
    if feedback_note:
        user_note_section = f"=== ADDITIONAL USER FEEDBACK ===\n{feedback_note}"

    try:
        clean_card_html = sanitize_card_html(card_html)
        clean_container_html = sanitize_card_html(container_html)
    except Exception:
        clean_card_html = card_html
        clean_container_html = container_html

    prompt = RECS_CORRECTION_PROMPT.format(
        issue_list="\n".join(issue_lines),
        user_note=user_note_section,
        container_html=clean_container_html,
        card_html=clean_card_html,
        extracted_styles=json.dumps(extracted_styles, indent=2),
        previous_template=previous_template.strip(),
    )

    last_err = None
    result = None
    for attempt in range(3):
        try:
            result = llm.invoke(prompt)
            break
        except Exception as e:
            last_err = e
            if attempt < 2:
                time.sleep(2 ** attempt)
    if result is None:
        return jsonify(error=_llm_error_message(last_err)), 502

    full_template = result if isinstance(result, str) else str(result)
    full_template = strip_markdown_fences(full_template)
    full_template = inline_extracted_styles(full_template, extracted_styles)
    full_template = sanitize_recs_output(full_template)

    return jsonify(recsTemplate=full_template, cardBody=full_template)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port, debug=True)
