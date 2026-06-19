"""
Quick test: run modified recs prompt against Qualys and Zayo inputs
via the Einstein Connected App directly.
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(__file__))
os.chdir(os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

from auth import ConnectedAppAuth
from llm_provider import ConnectAPILLM
from main import sanitize_card_html, strip_markdown_fences, inline_extracted_styles, sanitize_recs_output, DEFAULT_RECS_STYLES

authenticator = ConnectedAppAuth(creds_file="creds.json")
llm = ConnectAPILLM(authenticator=authenticator)

RECS_PROMPT_V2 = """You are an expert at adapting website HTML into Salesforce Personalization Handlebars transformer templates.

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
   PRESERVE EVERY INTERMEDIATE WRAPPER between the outermost container and the
   repeating card elements. If CONTAINER_HTML has nested divs (e.g. a swiper-wrapper
   div inside a swiper div), keep them ALL. These wrappers provide layout context
   (flex, grid) even if they appear to have no content.

2. LOOP: wrap the per-card body in {{{{#each (subVar 'recs')}}}}...{{{{/each}}}}
   directly inside the innermost wrapper that held the repeating cards.
   No extra wrapper divs around the loop.

3. CARD BODY: adapt CARD_HTML into the per-card Handlebars body.
   Keep the tag hierarchy, nesting, wrapper divs, and CSS class names from CARD_HTML.
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
   exactly as they appear in CARD_HTML. Only change the <img>'s src and alt and
   wrap it in an if/else for fallback. Example - if CARD_HTML has:
       <picture class="x-pic"><a class="x-link"><img class="x-img" src="..." alt="..."></a></picture>
   Output:
       <picture class="x-pic"><a class="x-link" href="{{{{subVar 'linkUrl'}}}}">{{{{#if (subVar 'image')}}}}<img class="x-img" src="{{{{subVar 'image'}}}}" alt="{{{{subVar 'name'}}}}">{{{{else}}}}<img class="x-img" src="https://placehold.co/750x422/eeeeee/aaaaaa?text=No+Image" alt="">{{{{/if}}}}</a></picture>

   Do NOT add inline width/display styles to the <img>. Do NOT drop wrapper elements like <picture>.

   If CARD_HTML has no <img> at all, insert this minimal pattern at the top of the card body:
   {{{{#if (subVar 'image')}}}}<img src="{{{{subVar 'image'}}}}" alt="{{{{subVar 'name'}}}}">{{{{else}}}}<img src="https://placehold.co/750x422/eeeeee/aaaaaa?text=No+Image" alt="">{{{{/if}}}}

6. PRESERVE THE CARD'S CTA ELEMENT.
   Keep the card's primary CTA link or button. Rewrite its href to {{{{subVar 'linkUrl'}}}},
   keep its tag, class names, inline styles, and visible text exactly as they appear.

7. REMOVE PER-CARD DATA NOT MAPPED TO THE 3 VARIABLES.
   Remove ALL element nodes carrying per-card data not mapped to image/name/linkUrl.
   This includes: <p> description paragraphs, prices, ratings, dates, author,
   read-time, category labels, overlay content sections, and any static text copied
   verbatim from CARD_HTML. Do NOT preserve them as static text.
   Do NOT invent subVars for them. Remove empty wrapper divs left behind ONLY if
   they carry no CSS class names.

8. STRIP REMAINING NOISE.
   Remove video, audio, modal, script, popup, and interactive elements not part of
   the card's link or CTA.
   NEVER remove elements that carry CSS class names — those classes provide styling
   (padding, shadows, layout, backgrounds) even when the element has no text content.
   NEVER remove elements that carry inline styles. Those styles are load-bearing
   visual identity.
   NEVER remove structural wrapper or container elements.

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
Output ONLY the complete Handlebars template (container + loop + per-card body).
Exactly 3 subVar variables: image, name, linkUrl. No <style> block, no JavaScript,
no boilerplate, no markdown fences, no commentary."""


def run_test(name, container_path, card_path):
    print(f"\n{'='*60}")
    print(f"  TESTING: {name}")
    print(f"{'='*60}\n")

    with open(container_path) as f:
        container_html = f.read()
    with open(card_path) as f:
        card_html = f.read()

    try:
        clean_card = sanitize_card_html(card_html)
        clean_container = sanitize_card_html(container_html)
    except Exception:
        clean_card = card_html
        clean_container = container_html

    prompt = RECS_PROMPT_V2.format(
        container_html=clean_container,
        card_html=clean_card,
        extracted_styles=json.dumps(DEFAULT_RECS_STYLES, indent=2),
    )

    print(f"Prompt length: {len(prompt)} chars")
    print("Calling Einstein LLM...")

    try:
        result = llm.invoke(prompt)
    except Exception as e:
        print(f"ERROR: {e}")
        return

    output = result if isinstance(result, str) else str(result)
    output = strip_markdown_fences(output)
    output = inline_extracted_styles(output, DEFAULT_RECS_STYLES)
    output = sanitize_recs_output(output)

    print(f"\nOutput length: {len(output)} chars")
    print(f"\n--- OUTPUT HTML ---\n{output}\n--- END ---\n")

    # Quick structural checks
    checks = {
        "has #each loop": "{{#each (subVar 'recs')}}" in output,
        "has {{/each}}": "{{/each}}" in output,
        "has subVar image": "subVar 'image'" in output,
        "has subVar name": "subVar 'name'" in output,
        "has subVar linkUrl": "subVar 'linkUrl'" in output,
    }
    if name == "Qualys":
        checks["has swiper-wrapper"] = "swiper-wrapper" in output
    if name == "Zayo":
        checks["has global__card-image"] = "global__card-image" in output

    print("Structural checks:")
    for check, passed in checks.items():
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {check}")


if __name__ == "__main__":
    run_test("Qualys", "/tmp/qualys_container.html", "/tmp/qualys_card.html")
    run_test("Zayo", "/tmp/zayo_container.html", "/tmp/zayo_card.html")
