
from pathlib import Path
import re

PROJECT_ROOT = Path(__file__).resolve().parent.parent
KB_FOLDER = PROJECT_ROOT / "kb"

TOPIC_KEYWORDS = {
    "returns": {
        "return", "returns", "exchange", "exchangeable",
        "returnable", "clothing", "electronics", "festive",
        "pickup", "condition", "category", "grocery",
        "beauty", "fashion", "innerwear", "books",
        "send", "back", "sent", "fit", "opened",
    },
    "refunds": {
        "refund", "refunds", "money", "reimbursement",
        "payment", "credited", "bank", "initiation",
    },
    "cancellations": {
        "cancel", "cancellation", "cancelled", "canceled",
        "shipped", "shipment",
    },
    "delivery": {
        "delivery", "deliver", "shipping", "shipment",
        "tracking", "late", "delayed", "order",
    },
    "damaged_wrong_missing": {
        "damaged", "defective", "expired", "wrong",
        "missing", "broken",
    },
}

STOP_WORDS = {
    "what", "when", "where", "which", "who", "how",
    "is", "are", "was", "were", "the", "a", "an",
    "for", "of", "on", "in", "at", "to", "my", "me",
    "i", "you", "we", "it", "this", "that", "can",
    "could", "would", "should", "please", "tell",
    "explain", "about", "do", "does", "did", "and",
    "or", "if", "with", "from", "have", "has",
    "zentromart", "customer", "support",
}

RETURN_QUERY_TERMS = normalize_terms = {
    "return", "returns", "returnable", "exchange",
    "window", "period", "category", "product",
    "delivery", "days", "fashion", "clothing",
    "footwear", "bags", "sale", "festive",
    "eligibility", "condition", "opened", "unopened",
    "send", "back", "sent", "fit",
}


def normalize(text):
    """Convert text into lowercase searchable words."""
    return set(re.findall(r"\b[a-z0-9]+\b", str(text).lower()))


def read_metadata(text):
    """Read YAML-like metadata from a Markdown header."""
    metadata = {}
    parts = text.split("---", 2)

    if len(parts) >= 3:
        for line in parts[1].splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                metadata[key.strip().lower()] = value.strip()

    return metadata


def detect_topic(words):
    """Choose a topic only when there is a positive keyword match."""
    scores = {
        topic: len(words & keywords)
        for topic, keywords in TOPIC_KEYWORDS.items()
    }

    best_topic = max(scores, key=scores.get)
    if scores[best_topic] == 0:
        return None

    return best_topic


def section_records(text):
    """Split a document into sections while preserving section IDs."""
    metadata_parts = text.split("---", 2)
    body = metadata_parts[2] if len(metadata_parts) >= 3 else text

    lines = body.splitlines()
    sections = []
    current_heading = "General information"
    current_lines = []

    heading_pattern = re.compile(
        r"^\s*#{1,6}\s*(?:\[([A-Za-z0-9._-]+)\]\s*)?(.*?)\s*$"
    )

    for line in lines:
        match = heading_pattern.match(line)

        if match:
            content = "\n".join(current_lines).strip()
            if content:
                sections.append({
                    "section_id": None,
                    "section_title": current_heading,
                    "text": content,
                })

            current_heading = match.group(2).strip() or "Untitled section"
            current_section_id = match.group(1)
            if current_section_id:
                current_heading = f"[{current_section_id}] {current_heading}"
            current_lines = []
        else:
            current_lines.append(line)

    content = "\n".join(current_lines).strip()
    if content:
        sections.append({
            "section_id": None,
            "section_title": current_heading,
            "text": content,
        })

    for section in sections:
        match = re.match(
            r"^\[([A-Za-z0-9._-]+)\]\s*(.*)$",
            section["section_title"],
        )
        if match:
            section["section_id"] = match.group(1)
            section["section_title"] = match.group(2)

    return sections


def document_priority(metadata):
    """Higher values mean more authoritative document types."""
    doc_type = metadata.get("doc_type", "").lower()
    status = metadata.get("status", "").lower()

    priorities = {
        "policy": 500,
        "agent_guide": 400,
        "help": 300,
        "faq": 200,
        "marketing": 100,
        "meta": 50,
    }

    priority = priorities.get(doc_type, 0)

    if doc_type == "policy" and status != "current":
        priority = 0

    return priority


def search_knowledge(question):
    """Retrieve relevant sections and prioritize authoritative policies."""
    question_words = normalize(question)
    searchable_words = question_words - STOP_WORDS
    question_text = str(question).lower()

    hindi_return_terms = (
        "वापस", "लौटाने", "लौटाना", "लौटा",
        "रिटर्न", "वापसी",
    )

    return_phrases = (
        "send back", "send it back", "send this back",
        "sent back", "give back", "take back",
        "return window", "return period", "return this",
        "return the", "can i return", "can we return",
        "return for fit", "return because of fit",
    )

    is_return_query = (
        bool(searchable_words & {
            "return", "returns", "returnable", "exchange",
        })
        or any(term in question_text for term in return_phrases)
        or any(term in question_text for term in hindi_return_terms)
    )

    if is_return_query:
        searchable_words |= RETURN_QUERY_TERMS

    topic = detect_topic(searchable_words)
    if is_return_query:
        topic = "returns"

    results = []

    for path in KB_FOLDER.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        metadata = read_metadata(text)
        status = metadata.get("status", "").lower()

        if status == "superseded":
            continue

        doc_type = metadata.get("doc_type", "").lower()
        title = metadata.get("title", path.stem)
        priority = document_priority(metadata)

        for section in section_records(text):
            section_text = section["text"]
            section_words = normalize(
                title + " " + section["section_title"] + " " + section_text
            )

            matching_words = searchable_words & section_words
            if not matching_words:
                continue

            score = len(matching_words) * 3
            score += priority / 100

            if topic == "returns" and (
                "return" in path.stem.lower()
                or "return" in title.lower()
                or "return" in section["section_title"].lower()
            ):
                score += 8

            if topic and topic.replace("_", "") in path.stem.replace("_", ""):
                score += 2

            if topic and topic in normalize(title):
                score += 2

            results.append({
                "score": score,
                "priority": priority,
                "filename": path.name,
                "title": title,
                "doc_type": doc_type,
                "status": status,
                "effective_from": metadata.get("effective_from", ""),
                "section_id": section["section_id"],
                "section_title": section["section_title"],
                "matches": len(matching_words),
                "text": section_text,
            })

    results.sort(
        key=lambda result: (
            result["score"],
            result["priority"],
            result["effective_from"],
        ),
        reverse=True,
    )

    unique_results = []
    seen = set()

    for result in results:
        key = (
            result["filename"],
            result["section_id"],
            result["section_title"],
        )
        if key in seen:
            continue

        seen.add(key)
        unique_results.append(result)

        if len(unique_results) == 10:
            break

    return unique_results


if __name__ == "__main__":
    question = input("Ask a ZentroMart support question: ")
    results = search_knowledge(question)

    if not results:
        print("No matching documents found.")
    else:
        for result in results:
            print(f"\nDocument: {result['filename']}")
            print(f"Title: {result['title']}")
            print(f"Type: {result['doc_type']}")
            print(f"Status: {result['status']}")
            print(f"Effective from: {result['effective_from']}")
            print(
                f"Section: {result['section_id']} - "
                f"{result['section_title']}"
            )
            print(f"Matching words: {result['matches']}")
            print(f"Search score: {result['score']}")
            print("-" * 40)
            print(result["text"][:1500])
