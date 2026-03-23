import os
import fitz
import time

SOURCE_DIR = "/app/data/legal_docs_source"


def analyze_sample(sample_size=100):
    pdf_files = []
    for root, _, files in os.walk(SOURCE_DIR):
        for file in files:
            if file.lower().endswith('.pdf'):
                pdf_files.append(os.path.join(root, file))

    total_files = len(pdf_files)
    if not pdf_files:
        return 0, 0, 0, 0

    import random
    sample = random.sample(pdf_files, min(sample_size, total_files))

    scanned_count = 0
    digital_count = 0
    total_pages = 0
    scanned_pages = 0

    for f in sample:
        try:
            doc = fitz.open(f)
            pages = len(doc)
            total_pages += pages

            # Check first 3 pages
            text = ""
            for i in range(min(3, pages)):
                text += doc[i].get_text()

            if len(text.strip()) < 100:
                scanned_count += 1
                scanned_pages += pages
            else:
                digital_count += 1
            doc.close()
        except:
            continue

    return total_files, scanned_count / len(sample), digital_count / len(sample), total_pages / len(sample)


if __name__ == "__main__":
    total, scanned_ratio, digital_ratio, avg_pages = analyze_sample(200)
    print(f"TOTAL_FILES: {total}")
    print(f"SCANNED_RATIO: {scanned_ratio:.2f}")
    print(f"DIGITAL_RATIO: {digital_ratio:.2f}")
    print(f"AVG_PAGES: {avg_pages:.1f}")
