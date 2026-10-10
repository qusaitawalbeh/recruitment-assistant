import glob
from src.cv_extractor import extract_cv_text, CVExtractionError

files = glob.glob("data/cvs/*.pdf") + glob.glob("data/cvs/*.docx")
print(f"Found {len(files)} CV files\n")

for path in files:
    print("=" * 60)
    print("FILE:", path)
    try:
        text = extract_cv_text(path)
        print("LENGTH:", len(text), "characters")
        print("PREVIEW:")
        print(text[:500])
    except CVExtractionError as e:
        print("FAILED:", e)