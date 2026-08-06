#!/usr/bin/env python3
"""Standalone Export Remediation Script — Fix all audit P1-P6 issues.

Applies in-place fixes to exported Markdown + JSON files:
  P1 — Broken table GFM separators
  P2 — OCR stuck-word patterns (Vietnamese + English)
  P3 — BIM template heading structure enhancement
  P4 — Duplicate content at page boundaries
  P5 — Table cell OCR cleanup
  P6 — JSON chunk text normalization

Usage:
    python3 scripts/remediate_exports.py --apply
    python3 scripts/remediate_exports.py --dry-run
    python3 scripts/remediate_exports.py --revert

Creates .bak backups before any modifications.
"""

import os
import re
import sys
import json
import glob
import shutil
import argparse
import logging
from pathlib import Path
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Paths ───────────────────────────────────────────────────────────────
EXPORT_MD_DIR = os.environ.get("EXPORT_MD_DIR", "/home/vvc/Public/exports/markdown")
EXPORT_JSON_DIR = os.environ.get("EXPORT_JSON_DIR", "/home/vvc/Public/exports/json")


# ═══════════════════════════════════════════════════════════════════════
# FIX 1: OCR STUCK-WORD PATTERNS
# ═══════════════════════════════════════════════════════════════════════

# Vietnamese stuck words found during audit
_STUCK_WORD_FIXES = [
    # --- Audit-detected patterns (highest priority) ---
    ('hợpnếutấtcảcácch', 'hợp nếu tất cả các ch'),
    ('Ủyban', 'Ủy ban'), ('ủyban', 'ủy ban'),
    ('bốkèm', 'bố kèm'),

    # --- Common legal document patterns ---
    ('địa lýcó', 'địa lý có'), ('phân bốcác', 'phân bố các'),
    ('làcá nhân', 'là cá nhân'), ('làcá', 'là cá'),
    ('sựcần thiết', 'sự cần thiết'), ('sựcần', 'sự cần'),
    ('hộicủa', 'hội của'), ('hộicó', 'hội có'),
    ('đốivới', 'đối với'), ('Đốivới', 'Đối với'),
    ('nhưsau', 'như sau'), ('cóthể', 'có thể'),
    ('làmột', 'là một'), ('Làmột', 'Là một'),
    ('phảiđược', 'phải được'), ('khôngđược', 'không được'),
    ('dướiđây', 'dưới đây'), ('sauđây', 'sau đây'),
    ('mộtsố', 'một số'), ('dựán', 'dự án'),
    ('quảlý', 'quả lý'), ('xửlý', 'xử lý'),
    ('nhàở', 'nhà ở'), ('cơsở', 'cơ sở'),
    ('hồsơ', 'hồ sơ'), ('Hồsơ', 'Hồ sơ'),
    ('đảmbảo', 'đảm bảo'), ('antoàn', 'an toàn'),
    ('kỹthuật', 'kỹ thuật'), ('đầutư', 'đầu tư'),
    ('vàcác', 'và các'), ('vàcó', 'và có'),
    ('vàcông', 'và công'), ('vàkhông', 'và không'),
    ('củacác', 'của các'), ('củanhà', 'của nhà'),
    ('từcác', 'từ các'), ('chocác', 'cho các'),
    ('trongcác', 'trong các'), ('theocác', 'theo các'),
    ('vớicác', 'với các'), ('tạicác', 'tại các'),
    ('cáccông', 'các công'), ('cácnội', 'các nội'),
    ('đếncác', 'đến các'), ('cócác', 'có các'),
    ('cócông', 'có công'), ('códiện', 'có điện'),
    ('cónhiều', 'có nhiều'), ('phảicó', 'phải có'),
    ('khôngcó', 'không có'), ('khôngquá', 'không quá'),
    ('bằngcách', 'bằng cách'), ('đểcác', 'để các'),
    ('đểnhận', 'để nhận'), ('đểđảm', 'để đảm'),
    ('đểkiểm', 'để kiểm'), ('đểcó', 'để có'),
    ('tốiđa', 'tối đa'), ('vịtrí', 'vị trí'),
    ('nhỏnhất', 'nhỏ nhất'), ('lớnnhất', 'lớn nhất'),
    ('sốcủa', 'số của'), ('sốnày', 'số này'),
    ('kểtừ', 'kể từ'), ('đãcó', 'đã có'),
    ('vềxây', 'về xây'), ('vềyêu', 'về yêu'),
    ('vềkỹ', 'về kỹ'), ('vềkhung', 'về khung'),
    ('vềan', 'về an'), ('vềthiết', 'về thiết'),

    # --- BIM template patterns (Vietnamese) ---
    ('đáp ứngcácmục', 'đáp ứng các mục'),
    ('đáp ứngcác', 'đáp ứng các'),
    ('Yêucầu', 'Yêu cầu'), ('yêucầu', 'yêu cầu'),
    ('đểc hỉ', 'để chỉ'),
    ('đểchỉ chất lượng', 'để chỉ chất lượng'),
    ('quycách', 'quy cách'), ('Quycách', 'Quy cách'),
    ('thôngtin', 'thông tin'), ('Thôngtin', 'Thông tin'),
    ('dữliệu', 'dữ liệu'), ('Dữliệu', 'Dữ liệu'),
    ('quảnlý', 'quản lý'), ('Quảnlý', 'Quản lý'),
    ('hệthống', 'hệ thống'), ('Hệthống', 'Hệ thống'),
    ('côngtrình', 'công trình'), ('xâydựng', 'xây dựng'),
    ('thiếtkế', 'thiết kế'), ('thicông', 'thi công'),
    ('nghiệmthu', 'nghiệm thu'),
    ('báocáo', 'báo cáo'), ('Báocáo', 'Báo cáo'),
    ('phạmvi', 'phạm vi'), ('Phạmvi', 'Phạm vi'),
    ('tiêuchuẩn', 'tiêu chuẩn'), ('quyphạm', 'quy phạm'),
    ('chấtlượng', 'chất lượng'),
    ('thựchiện', 'thực hiện'), ('Thựchiện', 'Thực hiện'),
    ('kếhoạch', 'kế hoạch'), ('Kếhoạch', 'Kế hoạch'),
    ('côngviệc', 'công việc'), ('Côngviệc', 'Công việc'),
    ('tráchnhiệm', 'trách nhiệm'),
    ('nộidung', 'nội dung'), ('Nộidung', 'Nội dung'),
    ('mụctiêu', 'mục tiêu'), ('Mụctiêu', 'Mục tiêu'),
    ('giảipháp', 'giải pháp'), ('phươngpháp', 'phương pháp'),
    ('quytrình', 'quy trình'), ('Quytrình', 'Quy trình'),

    # --- BIM-specific stuck words found in content analysis ---
    ('Đểcó', 'Để có'), ('đểcó', 'để có'),
    ('sơđồ', 'sơ đồ'), ('Sơđồ', 'Sơ đồ'),
    ('sơbộ', 'sơ bộ'), ('Sơbộ', 'Sơ bộ'),
    ('mãmàu', 'mã màu'), ('Mãmàu', 'Mã màu'),
    ('Kýtự', 'Ký tự'), ('kýtự', 'ký tự'),
    ('Tấtcả', 'Tất cả'), ('tấtcả', 'tất cả'),
    ('Cácmốc', 'Các mốc'), ('cácmốc', 'các mốc'),
    ('cácmức', 'các mức'), ('Cácmức', 'Các mức'),
    ('cáccấu', 'các cấu'), ('Cáccấu', 'Các cấu'),
    ('cácbộ', 'các bộ'), ('Cácbộ', 'Các bộ'),
    ('cáctài', 'các tài'), ('Cáctài', 'Các tài'),
    ('đơnvị', 'đơn vị'), ('Đơnvị', 'Đơn vị'),
    ('đặtra', 'đặt ra'), ('Đặtra', 'Đặt ra'),
    ('đặttên', 'đặt tên'), ('Đặttên', 'Đặt tên'),
    ('chomột', 'cho một'), ('Chomột', 'Cho một'),
    ('cómột', 'có một'), ('Cómột', 'Có một'),
    ('vàmô', 'và mô'), ('lývà', 'lý và'),
    ('BIMcủa', 'BIM của'), ('BIMdự', 'BIM dự'),
    ('BIMcho', 'BIM cho'), ('BIMvà', 'BIM và'),
    ('dựáncó', 'dự án có'), ('dựánZZZ', 'dự án ZZZ'),
    ('dựánXXX', 'dự án XXX'),
    ('nhiệmvụ', 'nhiệm vụ'), ('Nhiệmvụ', 'Nhiệm vụ'),
    ('lànơi', 'là nơi'), ('Lànơi', 'Là nơi'),
    ('phốihợp', 'phối hợp'), ('Phốihợp', 'Phối hợp'),
    ('quymô', 'quy mô'), ('Quymô', 'Quy mô'),
    ('Quytắc', 'Quy tắc'), ('quytắc', 'quy tắc'),
    ('lưutrữ', 'lưu trữ'), ('Lưutrữ', 'Lưu trữ'),
    ('bànhành', 'ban hành'), ('Bànhành', 'Ban hành'),
    ('bộmôn', 'bộ môn'), ('Bộmôn', 'Bộ môn'),
    ('nhânlực', 'nhân lực'), ('Nhânlực', 'Nhân lực'),
    ('nhânsự', 'nhân sự'), ('Nhânsự', 'Nhân sự'),
    ('thiếtkếcơ', 'thiết kế cơ'),
    ('Mứcđộ', 'Mức độ'), ('mứcđộ', 'mức độ'),
    ('Vănphòng', 'Văn phòng'), ('vănphòng', 'văn phòng'),
    ('cụthể', 'cụ thể'), ('Cụthể', 'Cụ thể'),
    ('ởmỗi', 'ở mỗi'), ('ởmức', 'ở mức'),
    ('vàođó', 'vào đó'), ('vàomô', 'vào mô'),
    ('sẽtùy', 'sẽ tùy'), ('sẽtổ', 'sẽ tổ'),
    ('sẽđược', 'sẽ được'), ('Sẽđược', 'Sẽ được'),
    ('lậpkế', 'lập kế'),
    ('loạibỏ', 'loại bỏ'), ('Loạibỏ', 'Loại bỏ'),
    ('tấtcảcác', 'tất cả các'), ('Tấtcảcác', 'Tất cả các'),
    ('bảnvẽ', 'bản vẽ'), ('Bảnvẽ', 'Bản vẽ'),
    ('Môtả', 'Mô tả'), ('môtả', 'mô tả'),
    ('chia sẻcho', 'chia sẻ cho'), ('chia sẻcác', 'chia sẻ các'),
    ('chia sẻmô', 'chia sẻ mô'),
    ('bổsung', 'bổ sung'), ('Bổsung', 'Bổ sung'),
    ('cơbản', 'cơ bản'), ('Cơbản', 'Cơ bản'),
    ('thểnhư', 'thể như'), ('cụthển', 'cụ thể n'),
    ('xảracác', 'xảy ra các'),
    ('bêncập', 'bên cập'),

    # --- Residual OCR patterns found in post-fix verification ---
    ('bởicác', 'bởi các'), ('bởiChủ', 'bởi Chủ'),
    ('yêu cầucủa', 'yêu cầu của'),
    ('Làkế', 'Là kế'), ('làkế', 'là kế'),
    ('đượcthống', 'được thống'),
    ('loạibỏtấtcảcác', 'loại bỏ tất cả các'),
    ('loạibỏtất', 'loại bỏ tất'),
    ('loạibỏ', 'loại bỏ'),
    ('tấtcảcác', 'tất cả các'),
    ('tấtcảcáctrao', 'tất cả các trao'),
    ('tấtcả', 'tất cả'),
    ('đốivớicông', 'đối với công'),
    ('mứcđộchi', 'mức độ chi'),
    ('mứcđộ', 'mức độ'),
    ('sốcấu', 'số cấu'),
    ('đồtổ', 'đồ tổ'), ('độmốc', 'độ mốc'),
    ('vụứng', 'vụ ứng'), ('bộnội', 'bộ nội'),
    ('vịcó', 'vị có'),
    ('cơbảncho', 'cơ bản cho'),
    ('côngtrườngvà', 'công trường và'),
    ('quymôDự', 'quy mô Dự'),
    ('cókế', 'có kế'),
    ('đầuDự', 'đầu Dự'),
]

# English stuck words common in BIM templates
_STUCK_ENGLISH_FIXES = [
    ('dime nsional', 'dimensional'),
    ('Two-dime nsional', 'Two-dimensional'),
    ('Three-dime nsional', 'Three-dimensional'),
    ('Fou ndation', 'Foundation'),
    ('fou ndation', 'foundation'),
    ('Inform ation', 'Information'),
    ('inform ation', 'information'),
    ('Require ments', 'Requirements'),
    ('require ments', 'requirements'),
    ('Docu ment', 'Document'),
    ('docu ment', 'document'),
    ('Deli verable', 'Deliverable'),
    ('deli verable', 'deliverable'),
    ('Coord ination', 'Coordination'),
    ('coord ination', 'coordination'),
    ('Colla boration', 'Collaboration'),
    ('colla boration', 'collaboration'),
    ('Sched ule', 'Schedule'),
    ('sched ule', 'schedule'),
    ('Temp late', 'Template'),
    ('temp late', 'template'),
    ('Strat egy', 'Strategy'),
    ('strat egy', 'strategy'),
    ('Organ ization', 'Organization'),
    ('organ ization', 'organization'),
    ('Respon sibility', 'Responsibility'),
    ('respon sibility', 'responsibility'),
    ('Imple mentation', 'Implementation'),
    ('imple mentation', 'implementation'),
    ('infra structure', 'infrastructure'),
    ('Infra structure', 'Infrastructure'),
    ('archi tecture', 'architecture'),
    ('Archi tecture', 'Architecture'),
    ('constr uction', 'construction'),
    ('Constr uction', 'Construction'),
    ('manage ment', 'management'),
    ('Manage ment', 'Management'),
    ('speci fication', 'specification'),
    ('Speci fication', 'Specification'),
    # BIM-specific English OCR patterns from template content
    ('co mbine', 'combine'),
    ('Co mbine', 'Combine'),
    ('Respo nsible', 'Responsible'),
    ('respo nsible', 'responsible'),
    ('Au thority', 'Authority'),
    ('au thority', 'authority'),
    ('Co nsulted', 'Consulted'),
    ('co nsulted', 'consulted'),
    ('Du plicate', 'Duplicate'),
    ('du plicate', 'duplicate'),
    ('Inter ference', 'Interference'),
    ('inter ference', 'interference'),
    ('Accoun table', 'Accountable'),
    ('accoun table', 'accountable'),
]

# Vietnamese diacritic + uppercase boundary regex (generic stuck-word detector)
_VN_DIACRITIC_LOWER = r'[àáảãạắằẳẵặấầẩẫậéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]'
_VN_UPPER_START = r'[A-ZĐÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬÈÉẺẼẸÊẾỀỂỄỆÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÙÚỦŨỤƯỨỪỬỮỰỲÝỶỸỴ]'
_STUCK_GENERIC_RE = re.compile(rf'({_VN_DIACRITIC_LOWER})({_VN_UPPER_START})')

# Vietnamese syllable boundary patterns
_VN_DIAC_VOWELS = r'[àáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵ]'
_VN_VOWELS_ALL = r'[aăâeêioôơuưyàáảãạắằẳẵặấầẩẫậèéẻẽẹếềểễệìíỉĩịòóỏõọốồổỗộớờởỡợùúủũụứừửữựỳýỷỹỵ]'
_VN_MULTI_NF = r'(?:gh|gi|kh|ph|th|tr|qu)'
_VN_SINGLE_NF = r'[bdđghlqrsvxy]'
_VN_NEVER_FINAL = rf'(?:{_VN_MULTI_NF}|{_VN_SINGLE_NF})'
_VN_FINAL_CONS = r'(?:ng|nh|ch|[ckmntpk])'

_VN_SYLB_P1 = re.compile(rf'({_VN_DIAC_VOWELS})({_VN_NEVER_FINAL})(?={_VN_VOWELS_ALL})')
_VN_SYLB_P2 = re.compile(rf'({_VN_DIAC_VOWELS}{_VN_FINAL_CONS})({_VN_NEVER_FINAL})(?={_VN_VOWELS_ALL})')
_VN_SYLB_P3 = re.compile(rf'([aeio]|u(?!y)|(?<!u)y)({_VN_NEVER_FINAL})(?={_VN_DIAC_VOWELS})')

# uy-compound rejoin patterns (to fix over-splitting)
_UY_REJOIN_RE = re.compile(
    r'\b(thu|ngu|chu|tu|khu|hu|xu|bu|lu|phu|tru|du|su|vu|mu|cu|nu|ru)'
    r'\s+(yền|yên|yến|yện|yệt|yết|yể|yễ|yệ|yếu|yểu|yều)\b',
    re.IGNORECASE
)


def fix_ocr_stuck_words(text: str) -> str:
    """Apply all OCR stuck-word fixes to text."""
    if not text:
        return text

    # 1. Dictionary-based fixes (highest precision)
    for wrong, correct in _STUCK_WORD_FIXES:
        if wrong in text:
            text = text.replace(wrong, correct)

    # 2. English stuck-word fixes
    for wrong, correct in _STUCK_ENGLISH_FIXES:
        if wrong in text:
            text = text.replace(wrong, correct)

    # 3. Generic diacritic+uppercase boundary (regex)
    text = _STUCK_GENERIC_RE.sub(r'\1 \2', text)

    # 4. Vietnamese syllable boundary detection (iterative)
    for _ in range(3):
        prev = text
        text = _VN_SYLB_P1.sub(r'\1 \2', text)
        text = _VN_SYLB_P2.sub(r'\1 \2', text)
        text = _VN_SYLB_P3.sub(r'\1 \2', text)
        if text == prev:
            break

    # 5. Rejoin uy-compounds that got over-split
    text = _UY_REJOIN_RE.sub(r'\1\2', text)

    return text


# ═══════════════════════════════════════════════════════════════════════
# FIX 2: BROKEN TABLE GFM SEPARATORS
# ═══════════════════════════════════════════════════════════════════════

def fix_table_gfm(text: str) -> str:
    """Ensure all pipe-delimited tables have GFM separator rows."""
    if "|" not in text:
        return text

    lines = text.split("\n")
    fixed: list[str] = []
    in_table = False

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Count pipes
        pipe_count = stripped.count("|")
        is_pipe_row = (
            stripped.startswith("|") and stripped.endswith("|")
            and pipe_count >= 3
        )

        # Catch loose pipe rows (without leading/trailing |)
        is_loose_pipe_row = (
            not is_pipe_row
            and pipe_count >= 2
            and re.match(r'^\s*\S.*\|.*\S\s*$', stripped)
            and len(stripped) > 10
        )

        if not is_pipe_row and not is_loose_pipe_row:
            in_table = False
            fixed.append(line)
            continue

        # Normalize loose pipe rows
        if is_loose_pipe_row and not is_pipe_row:
            parts = [p.strip() for p in stripped.split("|")]
            if parts and parts[0] == "":
                parts = parts[1:]
            if parts and parts[-1] == "":
                parts = parts[:-1]
            stripped = "| " + " | ".join(parts) + " |"
            line = stripped
            is_pipe_row = True

        # Check if next line is already a separator
        next_line = lines[i + 1].strip() if i + 1 < len(lines) else ""
        is_next_sep = bool(re.match(r'^[\s|:\-]+$', next_line) and '---' in next_line)

        if is_next_sep:
            in_table = True
            fixed.append(line)
            continue

        if in_table:
            fixed.append(line)
            continue

        # First pipe row — check if it looks like a header
        cells = [c.strip() for c in stripped.split("|")[1:-1]]
        is_header = (
            cells
            and all(len(c) < 80 for c in cells)
            and any(re.search(r'[a-zA-Z\u00c0-\u1ef9]', c) for c in cells)
            and not all(re.match(r'^[\d.,\s%]+$', c) for c in cells if c)
        )
        if is_header:
            sep = "| " + " | ".join("---" for _ in cells) + " |"
            fixed.append(line)
            fixed.append(sep)
            in_table = True
        else:
            fixed.append(line)

    return "\n".join(fixed)


# ═══════════════════════════════════════════════════════════════════════
# FIX 3: BIM TEMPLATE HEADING STRUCTURE
# ═══════════════════════════════════════════════════════════════════════

# Pattern: lines like "1. SECTION TITLE" or "1.2 Subsection title"
_BIM_SECTION_H2_RE = re.compile(r'^(\d+)\.\s+([A-ZĐÀÁẢÃẠ][A-ZĐÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬÈÉẺẼẸÊẾỀỂỄỆÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÙÚỦŨỤƯỨỪỬỮỰỲÝỶỸỴa-zđàáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵ\s,\-–\(\)\/&]+)$')
_BIM_SECTION_H3_RE = re.compile(r'^(\d+\.\d+)\.?\s+([A-ZĐÀÁẢÃẠa-zđàáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵ][\w\s,\-–\(\)\/&\.àáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬÈÉẺẼẸÊẾỀỂỄỆÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÙÚỦŨỤƯỨỪỬỮỰỲÝỶỸỴ]+)$')
_BIM_SECTION_H4_RE = re.compile(r'^(\d+\.\d+\.\d+)\.?\s+([A-ZĐÀÁẢÃẠa-zđàáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵ][\w\s,\-–\(\)\/&\.àáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬÈÉẺẼẸÊẾỀỂỄỆÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÙÚỦŨỤƯỨỪỬỮỰỲÝỶỸỴ]+)$')

# Files that should get BIM heading enhancement
_BIM_TEMPLATE_PATTERNS = ['BEP', 'EIR', 'PreBEP', 'Template']


def _is_bim_template(filename: str) -> bool:
    """Check if a file is a BIM template that needs heading enhancement."""
    return any(pat in filename for pat in _BIM_TEMPLATE_PATTERNS)


def fix_bim_headings(text: str) -> str:
    """Enhance heading structure for BIM template documents.
    
    Detects numbered sections (1., 1.1, 1.1.1) and promotes them to headings.
    Only applies within the ## Content section.
    """
    # Split into pre-content and content sections
    content_match = re.search(r'(## Content\s*\n)(.*)', text, re.DOTALL)
    if not content_match:
        return text

    pre_content = text[:content_match.start(2)]
    content = content_match.group(2)

    lines = content.split('\n')
    fixed_lines = []

    for line in lines:
        stripped = line.strip()

        # Skip empty, heading, or table lines
        if not stripped or stripped.startswith('#') or stripped.startswith('|'):
            fixed_lines.append(line)
            continue

        # h3: "1.2 Subsection title" or "1.2. Subsection title"
        m = _BIM_SECTION_H3_RE.match(stripped)
        if m and len(m.group(2)) > 3:
            sec_num = m.group(1)
            sec_title = m.group(2)
            fixed_lines.append(f"\n### {sec_num}. {sec_title}")
            continue

        # h4: "1.2.3 Sub-subsection"
        m = _BIM_SECTION_H4_RE.match(stripped)
        if m and len(m.group(2)) > 3:
            sec_num = m.group(1)
            sec_title = m.group(2)
            fixed_lines.append(f"\n#### {sec_num}. {sec_title}")
            continue

        # h2: "1. MAIN SECTION" (top-level numbered sections → ### in content)
        m = _BIM_SECTION_H2_RE.match(stripped)
        if m and len(m.group(2)) > 3:
            sec_num = m.group(1)
            sec_title = m.group(2)
            fixed_lines.append(f"\n### {sec_num}. {sec_title}")
            continue

        fixed_lines.append(line)

    return pre_content + '\n'.join(fixed_lines)


# ═══════════════════════════════════════════════════════════════════════
# FIX 4: DUPLICATE CONTENT AT PAGE BOUNDARIES
# ═══════════════════════════════════════════════════════════════════════

def fix_duplicate_page_content(text: str) -> str:
    """Remove duplicate content that appears at page boundaries.
    
    Detects when the same numbered list item or Điều content appears
    twice due to page-boundary text extraction overlap.
    """
    if not text:
        return text

    lines = text.split('\n')
    if len(lines) < 10:
        return text

    # Strategy: detect consecutive identical non-empty lines
    fixed = []
    i = 0
    removed = 0
    while i < len(lines):
        # Check if this line is identical to a line 1-3 positions ahead
        # (allowing for blank lines between duplicates)
        is_dup = False
        if lines[i].strip() and len(lines[i].strip()) > 20:
            for lookahead in range(1, 4):
                j = i + lookahead
                if j < len(lines) and lines[j].strip() == lines[i].strip():
                    # Found duplicate — check if the gap is only whitespace
                    gap = lines[i+1:j]
                    if all(not g.strip() for g in gap):
                        # Skip the duplicate (keep second occurrence)
                        is_dup = True
                        removed += 1
                        break

        if not is_dup:
            fixed.append(lines[i])
        i += 1

    if removed > 0:
        logger.info(f"  [DEDUP] Removed {removed} duplicate lines at page boundaries")

    return '\n'.join(fixed)


# ═══════════════════════════════════════════════════════════════════════
# FIX 5: TABLE CELL OCR CLEANUP
# ═══════════════════════════════════════════════════════════════════════

def fix_table_cell_text(text: str) -> str:
    """Clean OCR artifacts specifically within markdown table cells."""
    if '|' not in text:
        return text

    lines = text.split('\n')
    fixed = []

    for line in lines:
        stripped = line.strip()
        # Only process table rows (lines with pipe characters)
        if stripped.startswith('|') and stripped.endswith('|') and '---' not in stripped:
            # Fix stuck words within each cell
            cells = stripped.split('|')
            fixed_cells = []
            for cell in cells:
                cell = cell.strip()
                # Apply OCR fixes to cell content
                cell = fix_ocr_stuck_words(cell)
                fixed_cells.append(f" {cell} " if cell else " ")
            fixed.append('|'.join(fixed_cells))
        else:
            fixed.append(line)

    return '\n'.join(fixed)


# ═══════════════════════════════════════════════════════════════════════
# MAIN PROCESSING
# ═══════════════════════════════════════════════════════════════════════

def process_markdown_file(filepath: str, dry_run: bool = False) -> dict:
    """Apply all fixes to a single markdown file."""
    filename = os.path.basename(filepath)
    text = Path(filepath).read_text(encoding='utf-8', errors='replace')
    original = text
    changes = []

    # --- Fix 1: OCR stuck words (entire document) ---
    text_after_ocr = fix_ocr_stuck_words(text)
    if text_after_ocr != text:
        changes.append("P2-OCR-stuck-words")
    text = text_after_ocr

    # --- Fix 2: Table GFM separators ---
    text_after_table = fix_table_gfm(text)
    if text_after_table != text:
        changes.append("P1-table-gfm")
    text = text_after_table

    # --- Fix 3: BIM template headings ---
    if _is_bim_template(filename):
        text_after_bim = fix_bim_headings(text)
        if text_after_bim != text:
            changes.append("P3-bim-headings")
        text = text_after_bim

    # --- Fix 4: Duplicate page content ---
    text_after_dedup = fix_duplicate_page_content(text)
    if text_after_dedup != text:
        changes.append("P4-dedup")
    text = text_after_dedup

    # --- Fix 5: Table cell OCR cleanup ---
    text_after_cells = fix_table_cell_text(text)
    if text_after_cells != text:
        changes.append("P5-table-cells")
    text = text_after_cells

    # --- Collapse triple+ blank lines ---
    text = re.sub(r'\n{4,}', '\n\n\n', text)

    changed = text != original

    if changed and not dry_run:
        Path(filepath).write_text(text, encoding='utf-8')

    result = {
        "changed": changed,
        "path": filepath,
        "fixes": changes,
    }

    if changed:
        logger.info(f"  ✅ {filename}: {', '.join(changes)}")
    else:
        logger.info(f"  ⏭️  {filename}: no changes needed")

    return result


def process_json_file(filepath: str, dry_run: bool = False) -> dict:
    """Apply OCR and boilerplate fixes to JSON export chunk texts."""
    filename = os.path.basename(filepath)
    try:
        data = json.loads(Path(filepath).read_text(encoding='utf-8', errors='replace'))
    except Exception as e:
        logger.error(f"  ❌ {filename}: JSON parse failed — {e}")
        return {"changed": False, "path": filepath, "error": str(e)}

    changed = False
    chunk_fixes = 0

    # Fix chunk text
    for chunk in data.get("chunks", []):
        old_text = chunk.get("text", "")
        new_text = fix_ocr_stuck_words(old_text)
        if new_text != old_text:
            chunk["text"] = new_text
            changed = True
            chunk_fixes += 1

    if changed and not dry_run:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    if changed:
        logger.info(f"  ✅ {filename}: fixed {chunk_fixes} chunks")
    else:
        logger.info(f"  ⏭️  {filename}: no changes needed")

    return {"changed": changed, "path": filepath, "chunks_fixed": chunk_fixes}


def backup_files(directory: str) -> int:
    """Create .bak backups of all files in directory."""
    count = 0
    for filepath in glob.glob(os.path.join(directory, "*")):
        if filepath.endswith(".bak"):
            continue
        bak = filepath + ".bak"
        if not os.path.exists(bak):
            shutil.copy2(filepath, bak)
            count += 1
    return count


def revert_files(directory: str) -> int:
    """Restore files from .bak backups."""
    count = 0
    for bak in glob.glob(os.path.join(directory, "*.bak")):
        original = bak.rsplit(".bak", 1)[0]
        shutil.copy2(bak, original)
        count += 1
    return count


def apply_all_fixes(dry_run: bool = False):
    """Apply all remediation fixes to all exports."""
    action = "DRY RUN" if dry_run else "APPLYING"
    logger.info(f"{'='*60}")
    logger.info(f" {action} ALL FIXES")
    logger.info(f"{'='*60}")

    if not dry_run:
        # Create backups
        md_bak = backup_files(EXPORT_MD_DIR)
        json_bak = backup_files(EXPORT_JSON_DIR)
        logger.info(f"📦 Backed up {md_bak} markdown + {json_bak} JSON files")

    # Process markdown files
    logger.info(f"\n📝 Processing Markdown files ({EXPORT_MD_DIR}):")
    md_files = sorted(glob.glob(os.path.join(EXPORT_MD_DIR, "*.md")))
    md_results = []
    for f in md_files:
        if f.endswith(".bak"):
            continue
        md_results.append(process_markdown_file(f, dry_run=dry_run))

    # Process JSON files
    logger.info(f"\n📋 Processing JSON files ({EXPORT_JSON_DIR}):")
    json_files = sorted(glob.glob(os.path.join(EXPORT_JSON_DIR, "*.json")))
    json_results = []
    for f in json_files:
        if f.endswith(".bak"):
            continue
        json_results.append(process_json_file(f, dry_run=dry_run))

    # Summary
    md_changed = sum(1 for r in md_results if r["changed"])
    json_changed = sum(1 for r in json_results if r["changed"])

    logger.info(f"\n{'='*60}")
    logger.info(f" SUMMARY")
    logger.info(f"{'='*60}")
    logger.info(f"  Markdown: {md_changed}/{len(md_results)} files fixed")
    logger.info(f"  JSON:     {json_changed}/{len(json_results)} files fixed")

    all_fixes = set()
    for r in md_results:
        all_fixes.update(r.get("fixes", []))
    if all_fixes:
        logger.info(f"  Fix types applied: {', '.join(sorted(all_fixes))}")

    return {
        "md_changed": md_changed,
        "json_changed": json_changed,
        "md_total": len(md_results),
        "json_total": len(json_results),
    }


def main():
    parser = argparse.ArgumentParser(description="RAG Export Remediation — Fix all audit issues")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--apply", action="store_true", help="Apply all fixes (creates .bak backups)")
    group.add_argument("--dry-run", action="store_true", help="Show what would change without writing")
    group.add_argument("--revert", action="store_true", help="Revert all files from .bak backups")

    args = parser.parse_args()

    if args.revert:
        md_count = revert_files(EXPORT_MD_DIR)
        json_count = revert_files(EXPORT_JSON_DIR)
        logger.info(f"🔄 Reverted {md_count} markdown + {json_count} JSON files")
    else:
        result = apply_all_fixes(dry_run=args.dry_run)
        if not args.dry_run:
            logger.info("\n✨ All fixes applied successfully!")
            logger.info("   Use --revert to undo if needed.")


if __name__ == "__main__":
    main()
