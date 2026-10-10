from src.gmail_auth import get_gmail_service
from src.gmail_reader import (
    search_messages, get_message, parse_message,
    load_processed_ids, save_processed_ids,
)

service = get_gmail_service()
processed = load_processed_ids()

query = "has:attachment (filename:pdf OR filename:docx) subject:Application"
ids = search_messages(service, query=query, max_results=20)
print(f"Found {len(ids)} emails")

for msg_id in ids:
    if msg_id in processed:
        print(f"Skipping already processed: {msg_id}")
        continue

    email = parse_message(get_message(service, msg_id))
    print("-" * 50)
    print("From:   ", email["sender"])
    print("Subject:", email["subject"])
    print("Files:  ", [a["filename"] for a in email["attachments"]])

    processed.add(msg_id)

save_processed_ids(processed)