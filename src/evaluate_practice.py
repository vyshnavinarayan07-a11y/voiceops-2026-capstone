
import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
QUESTIONS_FILE = PROJECT_ROOT / "practice" / "questions.csv"
RESULTS_DIR = PROJECT_ROOT / "data" / "results"

sys.path.insert(0, str(Path(__file__).resolve().parent))

from answer_question import answer_question


def normalize(text):
    """Normalize text for case-insensitive phrase matching."""
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def split_groups(value):
    """
    Semicolons separate required groups.
    Slashes separate alternatives within a group.

    Example:
        12; My Orders / app

    Requires '12' and either 'My Orders' or 'app'.
    """
    groups = []

    for group in (value or "").split(";"):
        alternatives = [
            item.strip()
            for item in group.split("/")
            if item.strip()
        ]

        if alternatives:
            groups.append(alternatives)

    return groups


def split_prohibited(value):
    """Return prohibited phrases for checking."""
    return [
        item.strip()
        for item in (value or "").split(";")
        if item.strip()
    ]


def evaluate_question(row, answer, error=""):
    """Check required phrases, prohibited phrases and errors."""
    answer_norm = normalize(answer)

    required_groups = split_groups(
        row.get("must_include", "")
    )
    prohibited_items = split_prohibited(
        row.get("must_not_include", "")
    )

    missing = []

    for alternatives in required_groups:
        if not any(
            normalize(phrase) in answer_norm
            for phrase in alternatives
        ):
            missing.append(" OR ".join(alternatives))

    prohibited = [
        phrase
        for phrase in prohibited_items
        if normalize(phrase) in answer_norm
    ]

    generation_failed = (
        bool(error)
        or not answer.strip()
        or "couldn't generate an answer right now" in answer_norm
        or "could not generate an answer right now" in answer_norm
    )

    checks_passed = (
        not generation_failed
        and not missing
        and not prohibited
    )

    if generation_failed:
        status = "generation_error"
    elif checks_passed:
        status = "phrase_checks_passed"
    else:
        status = "phrase_checks_failed"

    return {
        "id": row.get("id", ""),
        "language": row.get("language", ""),
        "question": row.get("question", ""),
        "expected_decision": row.get("expected_decision", ""),
        "acceptable_decisions": row.get("acceptable_decisions", ""),
        "answerable": row.get("answerable", ""),
        "gold_evidence": row.get("gold_evidence", ""),
        "answer": answer,
        "missing_required_items": "; ".join(missing),
        "prohibited_items_found": "; ".join(prohibited),
        "checks_passed": checks_passed,
        "evaluation_status": status,
        "error": error,
    }


def save_results(results):
    """Write evaluation results to CSV and JSONL."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    output_csv = RESULTS_DIR / "practice_evaluation.csv"
    output_jsonl = RESULTS_DIR / "practice_evaluation.jsonl"

    fields = [
        "id",
        "language",
        "question",
        "expected_decision",
        "acceptable_decisions",
        "answerable",
        "gold_evidence",
        "answer",
        "missing_required_items",
        "prohibited_items_found",
        "checks_passed",
        "evaluation_status",
        "error",
    ]

    with output_csv.open(
        "w", encoding="utf-8-sig", newline=""
    ) as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(results)

    with output_jsonl.open(
        "w", encoding="utf-8"
    ) as file:
        for result in results:
            file.write(
                json.dumps(result, ensure_ascii=False) + "\n"
            )

    return output_csv, output_jsonl


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate ZentroMart practice questions."
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Evaluate only the first N questions.",
    )

    parser.add_argument(
        "--id",
        dest="question_id",
        default="",
        help="Evaluate one question, such as PQ0003.",
    )

    parser.add_argument(
        "--pause",
        type=float,
        default=2.0,
        help="Seconds to wait between questions. Default: 2.",
    )

    args = parser.parse_args()

    if args.limit < 0 or args.pause < 0:
        print("--limit and --pause must not be negative.")
        sys.exit(1)

    if not QUESTIONS_FILE.exists():
        print(f"Question file not found: {QUESTIONS_FILE}")
        sys.exit(1)

    with QUESTIONS_FILE.open(
        "r", encoding="utf-8-sig", newline=""
    ) as file:
        questions = list(csv.DictReader(file))

    if args.question_id:
        questions = [
            row for row in questions
            if row.get("id", "").strip().upper()
            == args.question_id.strip().upper()
        ]

        if not questions:
            print(f"Question ID not found: {args.question_id}")
            sys.exit(1)

    elif args.limit:
        questions = questions[:args.limit]

    if not questions:
        print("No questions selected.")
        sys.exit(1)

    results = []

    print(f"Questions selected: {len(questions)}")
    print("Using the existing Gemini + knowledge-base pipeline.")
    print("API errors will be recorded, not counted as passes.\n")

    for index, row in enumerate(questions, start=1):
        question_id = row.get("id", f"question_{index}")
        question = row.get("question", "").strip()

        print(
            f"[{index}/{len(questions)}] "
            f"{question_id}: {question}"
        )

        answer = ""
        error_message = ""

        try:
            answer = answer_question(question)

            if (
                not answer
                or "couldn't generate an answer right now"
                in normalize(answer)
                or "could not generate an answer right now"
                in normalize(answer)
            ):
                error_message = (
                    "Answer generation failed; inspect terminal "
                    "output for the underlying API error."
                )

        except Exception as error:
            error_message = (
                f"{type(error).__name__}: {error}"
            )

        result = evaluate_question(
            row,
            answer or "",
            error_message,
        )

        results.append(result)

        print(f"Status: {result['evaluation_status']}")

        if result["missing_required_items"]:
            print(
                "Missing required groups: "
                f"{result['missing_required_items']}"
            )

        if result["prohibited_items_found"]:
            print(
                "Prohibited phrases: "
                f"{result['prohibited_items_found']}"
            )

        if error_message:
            print(f"Error: {error_message}")

        print()

        if index < len(questions) and args.pause:
            time.sleep(args.pause)

    output_csv, output_jsonl = save_results(results)

    passed = sum(
        row["evaluation_status"] == "phrase_checks_passed"
        for row in results
    )
    failed = sum(
        row["evaluation_status"] == "phrase_checks_failed"
        for row in results
    )
    errors = sum(
        row["evaluation_status"] == "generation_error"
        for row in results
    )

    print("=" * 48)
    print("EVALUATION SUMMARY")
    print(f"Questions evaluated: {len(results)}")
    print(f"Phrase checks passed: {passed}")
    print(f"Phrase checks failed: {failed}")
    print(f"Generation errors: {errors}")
    print(f"\nCSV report: {output_csv}")
    print(f"JSONL report: {output_jsonl}")
    print(
        "\nReminder: phrase checks are not a complete "
        "semantic or policy-correctness evaluation."
    )


if __name__ == "__main__":
    main()
