import os, re, json, statistics
from collections import Counter
from pymilvus import connections, Collection, MilvusClient
from core.config import get_settings

s = get_settings()
connections.connect(host=s.MILVUS_HOST, port=str(s.MILVUS_PORT))
col = Collection(s.MILVUS_COLLECTION)
col.load()
client = MilvusClient(uri=f'http://{s.MILVUS_HOST}:{s.MILVUS_PORT}')

total = col.num_entities
print(f"{'='*60}")
print(f"MILVUS QUALITY AUDIT  —  {total:,} entities")
print(f"{'='*60}")

res = client.query(
    collection_name=s.MILVUS_COLLECTION,
    filter='chunk_type == "parent"',
    output_fields=['text','source','page','doc_type','source_category','is_table','synthetic_queries','doc_number'],
    limit=500
)
print(f"\nSampled {len(res)} parent chunks")

lengths = [len(r['text']) for r in res]
print(f"\n[DIM 1] TEXT LENGTH DISTRIBUTION")
print(f"  Min        : {min(lengths):>6}")
print(f"  Max        : {max(lengths):>6}")
print(f"  Mean       : {statistics.mean(lengths):>6.0f}")
print(f"  Median     : {statistics.median(lengths):>6.0f}")
print(f"  <100 chars : {sum(1 for l in lengths if l<100):>6}  (noise)")
print(f"  <50 chars  : {sum(1 for l in lengths if l<50):>6}  (critical noise)")
print(f"  >8000 chars: {sum(1 for l in lengths if l>8000):>6}  (oversized)")

def count_short_lines(text):
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    return sum(1 for l in lines if len(l) < 60 and len(l) > 5)

print(f"\n[DIM 2] PARAGRAPH FRAGMENTATION")
fragmented = [r for r in res if count_short_lines(r['text']) > 5]
print(f"  Chunks with >5 short lines (<60c): {len(fragmented)}/{len(res)}")
if fragmented:
    worst = max(fragmented, key=lambda r: count_short_lines(r['text']))
    n = count_short_lines(worst['text'])
    print(f"  Worst: {n} short lines in: {worst['source'][:50]}")
    preview = '\n'.join(worst['text'].split('\n')[:6])
    print(f"  Preview:\n    {preview[:300]}")

print(f"\n[DIM 3] TABLE / TABULAR DATA QUALITY")
is_table_chunks = [r for r in res if r.get('is_table')]
tabular_text = [r for r in res if not r.get('is_table') and r['text'].count('|') > 3]
# Tables as plain text: multiple numeric values clustered on same line
num_table = [r for r in res if not r.get('is_table') and
    len(re.findall(r'\d+[,.]?\d*\s{2,}\d+[,.]?\d*', r['text'])) > 2]
print(f"  is_table=True chunks           : {len(is_table_chunks)}")
print(f"  Markdown table detected (|)    : {len(tabular_text)}")
print(f"  Numeric table as plain text    : {len(num_table)}  <- tables NOT flagged")

print(f"\n[DIM 4] METADATA COMPLETENESS")
missing_doc_num = sum(1 for r in res if not r.get('doc_number','').strip())
khac_cat = sum(1 for r in res if r.get('source_category','KHAC') == 'KHAC')
has_synth = sum(1 for r in res if r.get('synthetic_queries','').strip())
doc_types = Counter(r.get('doc_type','?') for r in res)
source_cats = Counter(r.get('source_category','?') for r in res)
print(f"  Missing doc_number         : {missing_doc_num}/{len(res)}")
print(f"  source_category = KHAC     : {khac_cat}/{len(res)}")
print(f"  Has synthetic_queries      : {has_synth}/{len(res)}")
print(f"  doc_type top-5             : {dict(doc_types.most_common(5))}")
print(f"  source_category dist       : {dict(source_cats.most_common(8))}")

print(f"\n[DIM 5] TEXT QUALITY / AI LEAKAGE")
def spacing_ratio(text):
    sp = text.count(' ')
    chars = len(text.replace(' ',''))
    return sp / (chars + sp + 1)

bad_sp = [r for r in res if spacing_ratio(r['text']) > 0.35]
monologue = ['certainly,', "I'll", "I will", "As an AI", "Here is", "Here's", "I cannot", "I would"]
leaked = [r for r in res if any(p.lower() in r['text'].lower() for p in monologue)]
print(f"  Chunks with spacing_ratio>0.35 : {len(bad_sp)}  (OCR artifact)")
print(f"  Potential AI monologue leakage : {len(leaked)}")
if leaked:
    for r in leaked[:2]:
        idx = r['text'].lower().find('certainly')
        if idx == -1: idx = r['text'].lower().find("here is")
        if idx == -1: idx = 0
        print(f"  → {r['source'][:40]}: ...{r['text'][max(0,idx-20):idx+60]}...")

print(f"\n[DIM 6] DUPLICATE CONTENT")
text_fp = [hash(r['text'].strip()[:300]) for r in res]
dup_fp = {h: c for h, c in Counter(text_fp).items() if c > 1}
print(f"  Duplicate content fingerprints : {len(dup_fp)}")
dup_chunks = sum(c-1 for c in dup_fp.values())
print(f"  Excess duplicate chunks        : {dup_chunks}")

issues = (
    sum(1 for l in lengths if l<50) +
    len(fragmented) +
    len(num_table) +
    len(bad_sp) +
    len(leaked) +
    dup_chunks
)
score = max(0, 100 - int(issues / max(len(res),1) * 100))
print(f"\n{'='*60}")
print(f"ESTIMATED QUALITY SCORE: {score}/100")
print(f"Total issues: {issues} (on sample of {len(res)})")
print(f"{'='*60}")
