import os

from src.gmail_auth import get_gmail_service
from src.gmail_reader import (
    search_messages, get_message, parse_message, save_cv_attachments,
    load_processed_ids, save_processed_ids,
)
from src.cv_extractor import build_candidate, CVExtractionError
from src.storage import load_candidates, save_candidates


SUBJECT_KEYWORDS = [
    "application", "CV", "resume", "job",
    '"طلب توظيف"', '"سيرة ذاتية"',
]
NEWER_THAN = "30d"
MAX_RESULTS = 50


def build_query():
    subjects = " OR ".join(f"subject:{kw}" for kw in SUBJECT_KEYWORDS)
    return (
        "has:attachment (filename:pdf OR filename:docx) "
        f"({subjects}) newer_than:{NEWER_THAN}"
    )


def main():
    service = get_gmail_service()
    processed = load_processed_ids()
    candidates = load_candidates()
    existing = {(c["email_id"], c["cv_file"]) for c in candidates}

    query = build_query()
    print("Search query:", query)
    ids = search_messages(service, query=query, max_results=MAX_RESULTS)
    print(f"Found {len(ids)} emails")

    for msg_id in ids:
        if msg_id in processed:
            print(f"Skipping already processed: {msg_id}")
            continue

        email = parse_message(get_message(service, msg_id))
        print("-" * 50)
        print("From:   ", email["sender"])
        print("Subject:", email["subject"])

        saved = save_cv_attachments(service, email)

        extracted = 0
        for path in saved:
            name = os.path.basename(path)
            try:
                candidate = build_candidate(email, path)
                key = (candidate["email_id"], candidate["cv_file"])
                if key not in existing:
                    candidates.append(candidate)
                    existing.add(key)
                extracted += 1
                print(f"  Text extracted: {name} ({len(candidate['cv_text'])} chars)")
            except CVExtractionError as e:
                print(f"  Extraction failed for {name}: {e}")


        if extracted:
            processed.add(msg_id)
        else:
            print("  No usable CV text, will retry next run")

    save_processed_ids(processed)
    save_candidates(candidates)
    print(f"\nTotal candidates stored: {len(candidates)}")


if __name__ == "__main__":
    main()