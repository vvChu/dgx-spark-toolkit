import glob, os, subprocess

broken = []
for f in glob.glob('/app/data/**/*.pdf', recursive=True):
    print(f"Testing {f}...")
    result = subprocess.run(
        ['python3', '-c', 'import sys, fitz; fitz.open(sys.argv[1])[0].get_text()', f],
        capture_output=True
    )
    if result.returncode != 0:
        print(f"BROKEN PDF FOUND: {f}")
        broken.append(f)

for b in broken:
    os.remove(b)
    print(f"Successfully deleted {b}")
print("Scan complete.")
