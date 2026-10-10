JOB_PATH = "data/job_description.txt"


def load_job_description(path=JOB_PATH):

    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read().strip()
    except FileNotFoundError:
        raise FileNotFoundError(f"Job description file not found: {path}")

    if not text:
        raise ValueError("Job description file is empty")
    return text