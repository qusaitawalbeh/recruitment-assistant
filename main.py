"""Command-line entry point to the same Week 2 screening workflow as the API."""
import argparse
import json
from pathlib import Path
from dotenv import load_dotenv
from src import screening


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="Screen CVs for an existing, HR-confirmed job.")
    parser.add_argument("--job-id", required=True, help="Create and confirm a job in the UI first")
    sources = parser.add_mutually_exclusive_group(required=True)
    sources.add_argument("--gmail-query", help='Job-specific Gmail query, e.g. subject:"Data Scientist"')
    sources.add_argument("--files", nargs="+", help="PDF/DOCX file paths")
    sources.add_argument("--rescreen", action="store_true", help="Re-evaluate saved CVs")
    args = parser.parse_args()
    try:
        if args.gmail_query:
            result = screening.screen_gmail(args.job_id, args.gmail_query)
        elif args.rescreen:
            result = {"results": screening.rescreen(args.job_id)}
        else:
            job = screening.ready_job(args.job_id)
            results = []
            for name in args.files:
                try:
                    with Path(name).open("rb") as stream:
                        content = stream.read(screening.MAX_FILE_BYTES + 1)
                    results.append(screening.ingest(job, Path(name).name, content, {"type": "local"}))
                except Exception as exc:
                    results.append({"filename": name, "status": "error", "error": str(exc)})
            result = {"results": results}
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as exc:
        parser.exit(1, f"Screening failed: {exc}\n")


if __name__ == "__main__":
    main()
