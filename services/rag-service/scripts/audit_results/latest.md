# Audit Result — latest

```

======================================================================
  COMPREHENSIVE RAG QUALITY AUDIT
  JSON: /home/vvc/Public/exports/json
  MD:   /home/vvc/Public/exports/markdown
  PDFs: /home/vvc/Public/exports
======================================================================

  Found 123 JSON exports, 123 Markdown exports

──────────────────────────────────────────────────────────────────────
  DIMENSION A: MARKDOWN QUALITY
──────────────────────────────────────────────────────────────────────
  ✅ no_h1                    :    0/123  (0.0%)
  ✅ no_headings              :    0/123  (0.0%)
  ✅ broken_table             :    0/123  (0.0%)
  🟡 ai_leakage               :    2/123  (1.6%)
  🔴 ocr_spacing              :   19/123  (15.4%)
  🟡 boilerplate              :    2/123  (1.6%)
  ✅ encoding_issues          :    0/123  (0.0%)
  ✅ very_short               :    0/123  (0.0%)

  📊 MARKDOWN SCORE: 90/100

──────────────────────────────────────────────────────────────────────
  DIMENSION B: JSON EXPORT QUALITY
──────────────────────────────────────────────────────────────────────
  ✅ missing_root_field       :    0/123  (0.0%)
  ✅ missing_meta_field       :    0/123  (0.0%)
  ✅ no_summary               :    0/123  (0.0%)
  ✅ empty_chunks             :    0/123  (0.0%)
  ✅ missing_chunk_field      :    0/123  (0.0%)
  ✅ invalid_doc_id           :    0/123  (0.0%)
  ✅ chunk_no_text            :    0/123  (0.0%)

  Total chunks across 123 files: 32,427
  Chunk type distribution: {'parent': 16875, 'child': 15519, 'preamble': 33}
  Strategy distribution:   {'Paragraph': 29430, 'Section': 1562, 'Table': 834, 'Article': 568, 'Preamble': 33}

  📊 JSON EXPORT SCORE: 100/100

──────────────────────────────────────────────────────────────────────
  DIMENSION C: CHUNKING QUALITY
──────────────────────────────────────────────────────────────────────
  Total chunks: 32,427  (parent: 16,875, child: 15,519, preamble: 33)
  🟡 Child/Parent ratio     : 0.92  (target: ≥1.5)
  🔴 Article strategy rate  : 1.2%  (target: ≥30%)
     Strategy breakdown     : {'Paragraph': 14902, 'Section': 944, 'Table': 834, 'Article': 195}
  ✅ Parent <100c (noise)   : 11/16875  (0.1%)
     Parent <50c (critical) : 0/16875  (0.0%)
  ✅ Parent >8000c (oversized): 1/16875  (0.0%)
     Length stats: min=64, max=10907, mean=564, median=444
  ✅ Child <100c             : 77/15519  (0.5%)
  ✅ Duplicate parent chunks : 0  (0 unique fingerprints repeated)
  🟡 Synthetic query coverage: 5164/16875  (30.6%, target: ≥40%)

  📊 CHUNKING SCORE: 65/100

──────────────────────────────────────────────────────────────────────
  DIMENSION D: MILVUS INGESTION QUALITY
──────────────────────────────────────────────────────────────────────
  ⚠  pymilvus or core.config not available, checking via JSON exports only

──────────────────────────────────────────────────────────────────────
  DIMENSION E: PDF→MARKDOWN FIDELITY
──────────────────────────────────────────────────────────────────────
  ✅ Source PDFs found      : 0
     Exported documents    : 123
     Coverage              : 12300.0%
  ✅ Docs with no chunks    : 0/123
     Pages/doc stats: min=2, max=887, mean=37.0
     Chunks/doc stats: min=6, max=7653, mean=263.6
  ✅ Very short docs (<500c): 0/123
     Text/doc stats: min=3332, max=3927938, mean=134772
  ✅ Docs with tables       : 73/123  (59.3%)
     Total table chunks    : 836

  📊 FIDELITY SCORE: 100/100


======================================================================
  FINAL QUALITY REPORT
======================================================================
  ✅ Markdown Quality          ██████████████████░░  90/100
  ✅ JSON Export Quality       ████████████████████ 100/100
  🟡 Chunking Quality          █████████████░░░░░░░  65/100
  ✅ PDF→MD Fidelity           ████████████████████ 100/100

  ══════════════════════════════════════════════════
  ✅ OVERALL QUALITY SCORE: 88/100
  ══════════════════════════════════════════════════

  ⚠  Milvus dimension skipped (not available). Run inside Docker for full audit.


```
