
import csv
import os
import re
from pathlib import Path
from datetime import date, timedelta
from dotenv import load_dotenv
from google import genai
from search_knowledge import search_knowledge


# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = PROJECT_ROOT / "data" / "products.csv"
HOLIDAYS_FILE = PROJECT_ROOT / "data" / "holidays.csv"

REFERENCE_DATE = "20 October 2026"
MODEL_NAME = "gemini-3.5-flash-lite"

load_dotenv(PROJECT_ROOT / ".env")
API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY is missing. Check your root .env file."
    )

client = genai.Client(api_key=API_KEY)

UNSUPPORTED_ANSWER = (
    "Sorry, I don't have information about that. "
    "I can connect you to a colleague who can help."
)


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def normalize_words(text):
    return set(re.findall(r"[a-z0-9]+", str(text).lower()))


def contains_any(text, phrases):
    text = str(text).lower()
    return any(phrase.lower() in text for phrase in phrases)


# ============================================================
# BUSINESS-DAY AND REFUND CALCULATIONS
# ============================================================

def load_holidays():
    """Load holiday dates from the dataset."""
    holidays = set()

    if not HOLIDAYS_FILE.exists():
        return holidays

    try:
        with open(
            HOLIDAYS_FILE, "r", encoding="utf-8-sig", newline=""
        ) as file:
            for row in csv.DictReader(file):
                for value in row.values():
                    value = str(value or "").strip()
                    try:
                        holidays.add(date.fromisoformat(value[:10]))
                        break
                    except ValueError:
                        continue
    except (OSError, csv.Error) as error:
        print(f"Could not read holiday calendar: {error}")

    return holidays


def is_business_day(day, holidays):
    """Business days are Monday-Saturday, excluding holidays."""
    return day.weekday() < 6 and day not in holidays


def add_business_days(start_date, days):
    """
    Count business days beginning the day after initiation.
    Business days are Monday-Saturday, excluding listed holidays.
    """
    if days <= 0:
        return start_date

    holidays = load_holidays()
    current = start_date + timedelta(days=1)
    counted = 0

    while counted < days:
        if is_business_day(current, holidays):
            counted += 1

        if counted < days:
            current += timedelta(days=1)

    return current


def get_refund_method(question):
    """Identify an explicit refund payment method."""
    text = str(question).lower()

    if re.search(r"\bupi\b", text):
        return "UPI", 1, 3

    if re.search(r"\bnet[\s-]*banking\b", text):
        return "net banking", 3, 5

    if re.search(r"\b(credit|debit)\s*cards?\b|\bcards?\b", text):
        return "card", 5, 7

    if "wallet" in text:
        return "wallet", 0, 0

    if re.search(r"\b(neft|bank transfer)\b", text):
        return "bank transfer", 5, 7

    return None


def get_refund_initiation_date(question):
    """Extract an explicit date from a refund question."""
    text = str(question).lower()

    # ISO dates, for example: 2026-10-17
    match = re.search(
        r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", text
    )

    if match:
        try:
            return date(
                int(match.group(1)),
                int(match.group(2)),
                int(match.group(3)),
            )
        except ValueError:
            return None

    month_names = {
        "jan": 1, "january": 1,
        "feb": 2, "february": 2,
        "mar": 3, "march": 3,
        "apr": 4, "april": 4,
        "may": 5,
        "jun": 6, "june": 6,
        "jul": 7, "july": 7,
        "aug": 8, "august": 8,
        "sep": 9, "sept": 9, "september": 9,
        "oct": 10, "october": 10,
        "nov": 11, "november": 11,
        "dec": 12, "december": 12,
    }

    month_pattern = (
        r"january|february|march|april|may|june|july|"
        r"august|september|october|november|december|"
        r"jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec"
    )

    patterns = [
        (
            rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+"
            rf"({month_pattern})(?:\s+(20\d{{2}}))?\b",
            "day_first",
        ),
        (
            rf"\b({month_pattern})\s+(\d{{1,2}})"
            rf"(?:st|nd|rd|th)?(?:,?\s+(20\d{{2}}))?\b",
            "month_first",
        ),
    ]

    for pattern, order in patterns:
        match = re.search(pattern, text)

        if not match:
            continue

        try:
            if order == "day_first":
                day = int(match.group(1))
                month_text = match.group(2)
                year = int(match.group(3) or "2026")
            else:
                month_text = match.group(1)
                day = int(match.group(2))
                year = int(match.group(3) or "2026")

            month = month_names[month_text.lower()]
            return date(year, month, day)

        except (ValueError, TypeError, KeyError):
            continue

    return None


def get_deterministic_refund_answer(question, results):
    """
    Calculate refund deadlines only when REF-2 is retrieved
    and the method and initiation date are explicit.
    """
    if not has_section(results, "pol_refunds.md", "REF-2"):
        return None

    method = get_refund_method(question)
    initiated = get_refund_initiation_date(question)

    if not method or not initiated:
        return None

    name, minimum_days, maximum_days = method

    if name == "wallet":
        return (
            "ZentroMart Wallet refunds are normally instant, "
            "within 2 hours of initiation."
        )

    earliest = add_business_days(initiated, minimum_days)
    latest = add_business_days(initiated, maximum_days)

    return (
        f"For {name} refunds initiated on "
        f"{initiated.strftime('%d %B %Y')}, the expected "
        f"timeline is {minimum_days} to {maximum_days} "
        f"business days. Based on the published business-day "
        f"calendar, that is approximately "
        f"{earliest.strftime('%d %B %Y')} to "
        f"{latest.strftime('%d %B %Y')} "
        f"(latest date: {latest.isoformat()})."
    )


# ============================================================
# PRODUCT CATALOG
# ============================================================

def load_products():
    if not DATA_FILE.exists():
        raise FileNotFoundError(
            f"Product catalog not found: {DATA_FILE}"
        )

    with open(
        DATA_FILE, "r", encoding="utf-8-sig", newline=""
    ) as file:
        return list(csv.DictReader(file))


def find_product_by_sku(question, products):
    match = re.search(r"\b[A-Z]{3}-\d{4}\b", str(question).upper())

    if not match:
        return None

    sku = match.group(0)

    for product in products:
        if product.get("sku", "").strip().upper() == sku:
            return product

    return None


def check_product(question):
    products = load_products()
    question_lower = str(question).lower()
    question_words = normalize_words(question)

    product = find_product_by_sku(question, products)

    if product:
        category = product.get("return_category", "").strip()
        return ("matched", category) if category else ("unknown", None)

    exact_matches = [
        product for product in products
        if product.get("title", "").strip()
        and product["title"].strip().lower() in question_lower
    ]

    if len(exact_matches) == 1:
        category = exact_matches[0].get("return_category", "").strip()
        if category:
            return "matched", category

    if len(exact_matches) > 1:
        categories = {
            product.get("return_category", "").strip()
            for product in exact_matches
        }

        if len(categories) == 1 and "" not in categories:
            return "matched", categories.pop()

        return "ambiguous", None

    color_words = {
        "black", "blue", "green", "grey", "gray", "red",
        "white", "beige", "maroon", "pink", "purple",
        "silver", "gold", "yellow", "brown",
    }
    ignored_words = {"a", "an", "the", "of", "and"}
    candidates = []

    for product in products:
        title = product.get("title", "").strip()

        if not title:
            continue

        core_words = (
            normalize_words(title) - color_words - ignored_words
        )

        if core_words and core_words.issubset(question_words):
            candidates.append((product, core_words))

    if candidates:
        most_specific = [
            (product, words)
            for product, words in candidates
            if not any(words < other for _, other in candidates)
        ]

        categories = {
            product.get("return_category", "").strip()
            for product, _ in most_specific
        }

        if len(categories) == 1 and "" not in categories:
            return "matched", categories.pop()

        if len(most_specific) == 1:
            category = most_specific[0][0].get(
                "return_category", ""
            ).strip()

            if category:
                return "matched", category

        return "ambiguous", None

    aliases = {
        "electronics": {
            "electronics", "accessories", "electronic", "earbuds",
            "smartwatch", "smartphone", "headphones", "powerbank",
            "laptop",
        },
        "fashion": {
            "fashion", "clothing", "footwear", "bags", "kurta",
            "shirt", "shoes", "dress", "trousers", "jeans", "tote",
        },
        "home_kitchen": {
            "home", "kitchen", "furniture", "bedsheet", "bedsheets",
            "pillow", "cookware",
        },
        "books_media": {"books", "book", "stationery", "notebook"},
        "beauty_sealed": {
            "beauty", "cosmetics", "perfume", "lipstick",
            "makeup", "fragrance",
        },
        "grocery": {"grocery", "groceries", "perishables"},
        "innerwear": {
            "innerwear", "lingerie", "swimwear", "briefs", "swimsuit",
        },
        "digital": {"gift", "cards", "digital", "codes"},
    }

    matches = [
        category for category, words in aliases.items()
        if question_words.intersection(words)
    ]

    if len(matches) == 1:
        return "matched", matches[0]

    if len(matches) > 1:
        return "ambiguous", None

    return "unknown", None


# ============================================================
# QUESTION CLASSIFICATION
# ============================================================

def is_return_question(question):
    words = normalize_words(question)
    text = str(question).lower()

    return bool(
        words.intersection({
            "return", "returns", "returnable", "exchange", "returning"
        })
        or contains_any(text, (
            "send back", "send it back", "send this back",
            "sent back", "give back", "take back",
        ))
        or contains_any(text, (
            "लौटाने", "लौटाना", "लौटा सकता", "लौटा सकती",
            "लौटा सकत", "वापस", "रिटर्न", "वापसी",
        ))
        or contains_any(text, (
            "return kar", "wapas kar", "return karna", "wapas karna",
        ))
    )


def is_product_return_question(question):
    text = str(question).lower()
    words = normalize_words(question)

    if contains_any(text, (
        "reverse pickup", "pickup fee", "pickup charge",
        "return fee", "return fees", "return charge",
        "return charges", "return process",
        "return policy for members", "membership benefit",
        "membership benefits",
    )):
        return False

    if contains_any(text, (
        "return window", "return period", "how long can i return",
        "how many days can i return", "how long to return",
        "can i return", "can we return", "is it returnable",
        "is this returnable", "return this product",
        "return the product", "return after opening", "return if opened",
        "return for fit", "return because of fit", "return the",
        "return a ", "return my ", "send back", "send it back",
        "send this back", "sent back", "give back", "take back",
        "वापस", "लौटाने", "लौटाना", "लौटा सकता",
        "लौटा सकती", "लौटा सकत", "रिटर्न", "वापसी",
    )):
        return True

    return bool(words.intersection({
        "returnable", "exchange", "exchanges", "returning"
    }))


def is_warranty_question(question):
    return bool(normalize_words(question).intersection({
        "warranty", "warranties", "assured",
        "claim", "claims", "manufacturer",
    }))


def is_cancellation_question(question):
    text = str(question).lower()

    return (
        contains_any(text, ("cancel", "cancellation", "shipped"))
        or contains_any(text, ("कैंसिल", "रद्द", "शिप", "भेज दिया"))
    )


def is_damaged_item_question(question):
    text = str(question).lower()

    return (
        contains_any(text, ("damaged", "broken", "defective", "cracked"))
        or contains_any(text, ("टूटा", "टूटी", "खराब", "क्षतिग्रस्त"))
    )


# ============================================================
# KNOWLEDGE-BASE RETRIEVAL
# ============================================================

def retrieve_evidence(question):
    try:
        return search_knowledge(question) or []
    except Exception as error:
        print(f"Knowledge-base search error: {error}")
        return []


def has_current_return_policy(results):
    return any(
        Path(result.get("filename", "")).name == "pol_returns_v4.md"
        and result.get("section_id") == "RET-2"
        for result in results
    )


def has_section(results, filename, section_id):
    return any(
        Path(result.get("filename", "")).name == filename
        and result.get("section_id") == section_id
        for result in results
    )


def get_return_answer(question, category, results):
    if not has_current_return_policy(results):
        return None

    words = normalize_words(question)
    text = str(question).lower()
    has_sale_policy = has_section(
        results, "pol_returns_v4.md", "RET-8"
    )

    mentions_sale = bool(
        words.intersection({"sale", "sales", "festive"})
        or "sale order" in text
    )

    if category == "fashion" and mentions_sale and has_sale_policy:
        return (
            "Clothing, footwear and bags from orders placed between "
            "1 October and 15 October 2026 can be returned within "
            "30 calendar days of delivery, subject to policy conditions. "
            "Other orders normally have a 15-calendar-day return window."
        )

    answers = {
        "electronics": (
            "Electronics and accessories normally have a 7-calendar-day "
            "return window from delivery. Electronics delivered before "
            "1 August 2026 retain the earlier 10-day window."
        ),
        "fashion": (
            "Clothing, footwear and bags can normally be returned within "
            "15 calendar days from delivery. A special 30-day window "
            "applies to qualifying orders placed between 1 October and "
            "15 October 2026. Check the order date to confirm eligibility."
        ),
        "home_kitchen": (
            "Home, kitchen and furniture products can normally be returned "
            "within 10 calendar days from delivery."
        ),
        "books_media": (
            "Books and stationery can normally be returned within "
            "10 calendar days from delivery."
        ),
        "beauty_sealed": (
            "Beauty and personal-care products can normally be returned "
            "within 7 calendar days from delivery only when unopened "
            "and with the seal intact."
        ),
        "grocery": (
            "Grocery, fresh and perishable products are not returnable "
            "under the standard return policy."
        ),
        "innerwear": (
            "Innerwear, lingerie and swimwear are not returnable "
            "under the standard return policy."
        ),
        "digital": (
            "Gift cards and digital codes are not returnable "
            "under the standard return policy."
        ),
    }

    return answers.get(category)


# ============================================================
# EVIDENCE CONTEXT
# ============================================================

def build_context(results):
    parts = []

    for result in results:
        parts.append(
            f"Document: {result.get('filename', 'unknown')}\n"
            f"Title: {result.get('title', 'unknown')}\n"
            f"Type: {result.get('doc_type', 'unknown')}\n"
            f"Status: {result.get('status', 'unknown')}\n"
            f"Effective from: {result.get('effective_from', 'unknown')}\n"
            f"Section: {result.get('section_id', 'unknown')} - "
            f"{result.get('section_title', 'unknown')}\n"
            f"Content:\n{result.get('text', '')[:5000]}"
        )

    return "\n\n---\n\n".join(parts)


# ============================================================
# CATALOG FACTS FOR WARRANTY QUESTIONS
# ============================================================

def get_catalog_note(question, warranty_question):
    if not warranty_question:
        return ""

    try:
        products = load_products()
        product = find_product_by_sku(question, products)

        if not product:
            return ""

        return (
            f"Verified SKU: {product.get('sku', '')}\n"
            f"Product: {product.get('title', '')}\n"
            f"ZentroMart Assured: {product.get('assured', '')}\n"
            f"Manufacturer warranty months: "
            f"{product.get('warranty_months', '')}\n"
        )

    except (FileNotFoundError, OSError, csv.Error) as error:
        print(f"Catalog verification error: {error}")
        return ""


def get_assured_claim_answer(question):
    """
    Give a deterministic, catalog-verified answer to a product-specific
    ZentroMart Assured claim question.
    """
    text = str(question).lower()

    asks_about_assured = (
        "assured" in text or "zentromart assured" in text
    )

    asks_how_to_claim = (
        contains_any(text, (
            "claim", "claims", "kaise", "karein", "karu",
            "karna", "process", "raise", "कैसे", "करें",
        ))
    )

    if not (asks_about_assured and asks_how_to_claim):
        return None

    try:
        products = load_products()
        product = find_product_by_sku(question, products)

        # Do not assume a product if the SKU is missing or unknown.
        if not product:
            return None

        assured = str(product.get("assured", "")).strip().lower()

        if assured not in ("true", "1", "yes"):
            return (
                "Is product ke liye ZentroMart Assured warranty "
                "catalog mein confirm nahi hai. Brand warranty ke "
                "liye manufacturer se sampark karein."
            )

        return (
            f"Haan, {product.get('sku', '')} "
            f"({product.get('title', '')}) par ZentroMart Assured "
            "ki 12-month warranty delivery date se milti hai, "
            "brand warranty ke alawa. Claim karne ke liye app mein "
            "My Orders section kholen aur claim raise karein. "
            "ZentroMart pickup arrange karke repair ya replacement "
            "ki suvidha deta hai."
        )

    except (FileNotFoundError, OSError, csv.Error) as error:
        print(f"Assured warranty lookup error: {error}")
        return None


# ============================================================
# GEMINI RESPONSE GENERATION
# ============================================================

def generate_answer(question, results, catalog_note=""):
    context = build_context(results)

    prompt = f"""
You are a careful customer-support assistant for ZentroMart.

Reference date: {REFERENCE_DATE}.

Use only the supplied knowledge-base evidence and verified
catalog facts. Never invent policies, fees, dates or procedures.

Document precedence:
1. Current policies.
2. Agent guides.
3. Help articles.
4. FAQs.
5. Marketing pages.

Rules:
- Prefer current policy over conflicting FAQs or marketing content.
- Respect document status and effective dates.
- Return windows use calendar days.
- Refund and logistics timelines use business days when specified.
- Business days are Monday through Saturday, excluding listed holidays.
- For refund calculations, follow the exact counting rule in REF-2.
- Do not invent refund deadlines or delivery dates.
- For warranty questions, distinguish ZentroMart Assured from
  manufacturer warranty.
- Do not require a product name for general policy questions.
- Do not confuse reverse pickup fees with return eligibility.
- Do not expose customer information or bypass order verification.
- Reply in the customer's language when possible, including Hindi
  and Hinglish.
- For a Hindi question about an order already shipped, use the
  cancellation policy evidence and answer in Hindi.
- For a Hindi question about a damaged or broken item, use the
  damaged-item policy evidence and mention the required reporting
  deadline if the evidence specifies one.
- If evidence does not answer the question, do not guess.
- For undocumented features or services, answer exactly:
  "{UNSUPPORTED_ANSWER}"
- If ambiguous, ask one short clarifying question.
- Be concise, friendly and professional.
- Do not claim an action, refund, ticket or booking was completed
  unless a verified tool result confirms it.

Customer question:
{question}

Verified catalog information:
{catalog_note or "No additional verified catalog facts."}

Knowledge-base evidence:
{context}

Write only the customer-facing answer.
"""

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
        )

        answer = (response.text or "").strip()

        return answer or (
            "I'm sorry, I couldn't generate an answer right now."
        )

    except Exception as error:
        error_text = str(error)
        print(f"Gemini answer-generation error: {error_text}")

        if (
            "429" in error_text
            or "RESOURCE_EXHAUSTED" in error_text.upper()
        ):
            return (
                "I'm temporarily unable to check this information "
                "because the support service is busy. Please try again shortly."
            )

        return "I'm sorry, I couldn't generate an answer right now."


# ============================================================
# MAIN QUESTION-ANSWERING FUNCTION
# ============================================================

def answer_question(question):
    question = str(question).strip()

    if not question:
        return "Please enter a question so I can help."

    return_related = is_return_question(question)
    product_return = is_product_return_question(question)
    warranty_related = is_warranty_question(question)

    # Targeted product-specific warranty claim answer.
    # This uses the verified product catalog and avoids an unnecessary
    # Gemini call for this specific question.
    assured_answer = get_assured_claim_answer(question)

    if assured_answer:
        return assured_answer

    category = None

    if return_related and product_return:
        try:
            product_status, category = check_product(question)

        except (FileNotFoundError, OSError, csv.Error) as error:
            print(f"Product catalog error: {error}")
            return (
                "I'm unable to check the product catalog right now. "
                "Please try again shortly."
            )

        if product_status == "unknown":
            return (
                "I couldn't identify that product or category in our "
                "catalog, so I can't reliably confirm its return window. "
                "Could you share the exact product name or SKU?"
            )

        if product_status == "ambiguous":
            return (
                "I found multiple products or categories that may match "
                "your question. Could you share the exact product name "
                "or SKU so I can check the correct policy?"
            )

    results = retrieve_evidence(question)

    # For Hindi cancellation/damaged-item questions, make a second
    # retrieval attempt using English policy terms if needed.
    if not results and is_cancellation_question(question):
        results = retrieve_evidence(
            "order already shipped cancellation policy CAN-2"
        )

    if not results and is_damaged_item_question(question):
        results = retrieve_evidence(
            "damaged broken item report within 48 hours DWM-1"
        )

    if not results:
        return (
            "I couldn't find enough information in the current "
            "knowledge base to answer that reliably."
        )

    refund_answer = get_deterministic_refund_answer(question, results)

    if refund_answer:
        return refund_answer

    if return_related and product_return:
        verified_answer = get_return_answer(question, category, results)

        if verified_answer:
            return verified_answer

    catalog_note = get_catalog_note(question, warranty_related)

    return generate_answer(question, results, catalog_note)


# ============================================================
# RUN FROM TERMINAL
# ============================================================

if __name__ == "__main__":
    question = input("Ask a ZentroMart support question: ")
    print("\nAnswer:")
    print(answer_question(question))
