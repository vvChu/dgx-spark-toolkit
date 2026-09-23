"""
Legal Taxonomy Classifier for Vietnamese Legal Documents.

Populates 3 Milvus v9 fields that are currently UNKNOWN:
  - doc_type   : 14 standardized document types (incl. QCVN/TCVN)
  - legal_level: 7 hierarchical levels of legal authority
  - discipline : 16 subject-matter domains

Approach: Simple string-contains matching (fast, reliable with Unicode).
"""
import re
import os
from typing import Optional


# ─────────────────────────────────────────────────────────────────────
# 1. DOC_TYPE — Loại văn bản (14 types)
# ─────────────────────────────────────────────────────────────────────
# Each rule: (list_of_substrings, doc_type)
# Order matters: more specific first
_DOC_TYPE_RULES = [
    (['QCVN'],                              'QCVN'),
    (['TCVN'],                              'TCVN'),
    (['VBHN'],                              'VB_HOP_NHAT'),
    (['NĐ-', 'NĐ/', 'ND-', 'ND/'],        'NGHI_DINH'),
    (['NQ-', 'NQ/', 'QH15', 'QH14'],       'NGHI_QUYET'),
    (['QĐ-', 'QĐ/', 'QD-', 'QD/'],        'QUYET_DINH'),
    (['TTr-', 'TTr/'],                      'TO_TRINH'),
    (['TT-', 'TT/'],                        'THONG_TU'),
    (['CT-', 'CT/'],                        'CHI_THI'),
    (['TB-', 'TB/'],                        'THONG_BAO'),
    (['CV-', 'CV/'],                        'CONG_VAN'),
]

# Separate check for TB+digits (e.g. TB340)
_TB_DIGIT_RE = re.compile(r'TB\d')


# Regex patterns for filename prefix matching (e.g. TT01-2023, ND15-2021, QD08-TTg)
# Order: more specific doc types first, then generic ones
_FILENAME_PREFIX_RULES = [
    (re.compile(r'(?i)^QCVN'), 'QCVN'),
    (re.compile(r'(?i)^TCVN'), 'TCVN'),
    (re.compile(r'(?i)^VBHN'), 'VB_HOP_NHAT'),
    (re.compile(r'(?i)^N[ĐD]\d'),  'NGHI_DINH'),
    (re.compile(r'(?i)^NQ\d'),     'NGHI_QUYET'),
    (re.compile(r'(?i)^Q[ĐD]\d'),  'QUYET_DINH'),
    (re.compile(r'(?i)^TTr\d'),    'TO_TRINH'),
    (re.compile(r'(?i)^TT\d'),     'THONG_TU'),
    (re.compile(r'(?i)^CT\d'),     'CHI_THI'),
    (re.compile(r'(?i)^TB\d'),     'THONG_BAO'),
    (re.compile(r'(?i)^CV\d'),     'CONG_VAN'),
]


def classify_doc_type(
    doc_number: str = "",
    filename: str = "",
    text_head: str = "",
) -> str:
    """Classify document type from doc_number, filename, or text head."""
    # Priority 1: Substring matching on doc_number, filename, text_head
    sources = [doc_number, filename, text_head[:300]]
    for source in sources:
        if not source:
            continue
        upper = source.upper()
        for substrings, dtype in _DOC_TYPE_RULES:
            for sub in substrings:
                if sub.upper() in upper:
                    return dtype
        # TB+digit check
        if _TB_DIGIT_RE.search(source):
            return 'THONG_BAO'

    # Priority 2: Filename prefix matching (e.g. TT01-2023-BTP → THONG_TU)
    # This catches filenames like "TT01-2023" where there's no "TT-" separator
    if filename:
        basename = os.path.basename(filename).split('.')[0]  # Remove extension
        for pattern, dtype in _FILENAME_PREFIX_RULES:
            if pattern.match(basename):
                return dtype

    return "VAN_BAN"


# ─────────────────────────────────────────────────────────────────────
# 2. LEGAL_LEVEL — Cấp hiệu lực pháp lý (7 levels)
# ─────────────────────────────────────────────────────────────────────
_TYPE_TO_LEVEL = {
    'HIEN_PHAP':   'HIEN_PHAP',
    'BO_LUAT':     'LUAT',
    'LUAT':        'LUAT',
    'PHAP_LENH':   'LUAT',
    'NGHI_DINH':   'NGHI_DINH',
    'NGHI_QUYET':  'NGHI_QUYET',
    'QUYET_DINH':  'QUYET_DINH',
    'THONG_TU':    'THONG_TU',
    'CHI_THI':     'THONG_TU',
    'TO_TRINH':    'THONG_TU',
    'THONG_BAO':   'THONG_TU',
    'CONG_VAN':    'THONG_TU',
    'QCVN':        'KY_THUAT',
    'TCVN':        'KY_THUAT',
    'VB_HOP_NHAT': 'VB_HOP_NHAT',
}

_LOCAL_KEYWORDS = ['UBND', 'HĐND', 'HDND']


def classify_legal_level(
    doc_type: str = "VAN_BAN",
    authority: str = "",
) -> str:
    """Derive hierarchical legal level from doc_type + authority."""
    level = _TYPE_TO_LEVEL.get(doc_type)
    if level:
        # If a local authority issued a QĐ/NQ → DIA_PHUONG
        if level in ('QUYET_DINH', 'NGHI_QUYET', 'THONG_TU'):
            auth_upper = authority.upper()
            for kw in _LOCAL_KEYWORDS:
                if kw in auth_upper:
                    return 'DIA_PHUONG'
        return level

    # Fallback
    auth_upper = authority.upper()
    for kw in _LOCAL_KEYWORDS:
        if kw in auth_upper:
            return 'DIA_PHUONG'

    return 'UNKNOWN'


# ─────────────────────────────────────────────────────────────────────
# 3. DISCIPLINE — Lĩnh vực / Ngành (16 domains)
# ─────────────────────────────────────────────────────────────────────
_DISCIPLINE_RULES = [
    # (keywords, discipline_code)
    (['BXD'],                                           'XAY_DUNG'),
    (['BTNMT'],                                         'MOI_TRUONG'),
    (['BGTVT'],                                         'GIAO_THONG'),
    (['BTP'],                                           'TU_PHAP'),
    (['BTC'],                                           'TAI_CHINH'),
    (['BKHĐT', 'BKHDT'],                                'DAU_TU'),
    (['BLĐTBXH', 'BLDTBXH'],                            'LAO_DONG'),
    (['BGDĐT', 'BGDDT'],                                'GIAO_DUC'),
    (['BYT'],                                           'Y_TE'),
    (['BCT'],                                           'CONG_THUONG'),
    (['BNNPTNT'],                                       'NONG_NGHIEP'),
    (['BNV'],                                           'NOI_VU'),
    (['BQP'],                                           'QUOC_PHONG'),
    (['BCA', 'PCCC', 'CATP'],                           'CONG_AN'),
    (['BTTTT'],                                         'CNTT'),
]

# Text-based discipline detection (only for text_head fallback)
_TEXT_DISCIPLINE_KEYWORDS = {
    'XAY_DUNG':  ['xây dựng', 'kiến trúc', 'quy hoạch xây', 'quy hoạch đô'],
    'MOI_TRUONG': ['môi trường', 'khí thải', 'nước thải', 'tài nguyên'],
    'DAT_DAI':   ['đất đai', 'sử dụng đất', 'quyền sử dụng'],
    'GIAO_THONG': ['giao thông', 'vận tải', 'đường bộ'],
    'TU_PHAP':   ['tư pháp', 'thi hành án', 'XLVPHC', 'hộ tịch'],
    'TAI_CHINH': ['tài chính', 'thuế', 'ngân sách', 'hải quan'],
    'DAU_TU':    ['đầu tư', 'khu công nghiệp', 'thương mại tự do'],
    'LAO_DONG':  ['lao động', 'bảo hiểm xã hội'],
    'GIAO_DUC':  ['giáo dục', 'đào tạo'],
    'Y_TE':      ['y tế', 'dược', 'khám chữa bệnh'],
    'CONG_THUONG': ['công thương', 'xuất khẩu', 'nhập khẩu'],
    'NONG_NGHIEP': ['nông nghiệp', 'lâm nghiệp', 'thủy sản'],
    'NOI_VU':    ['nội vụ', 'cán bộ', 'công chức', 'viên chức'],
    'CONG_AN':   ['công an', 'phòng cháy', 'PCCC'],
    'CNTT':      ['viễn thông', 'công nghệ thông tin'],
}


def classify_discipline(
    text_head: str = "",
    authority: str = "",
    doc_number: str = "",
    filename: str = "",
) -> str:
    """Classify the subject-matter domain from authority, doc_number, filename, or text."""
    # Priority 1: Authority abbreviation (most reliable)
    if authority:
        auth_upper = authority.upper()
        for keywords, disc in _DISCIPLINE_RULES:
            for kw in keywords:
                if kw.upper() in auth_upper:
                    return disc

    # Priority 2: Doc number suffix (e.g. TT-BTP → BTP)
    if doc_number:
        num_upper = doc_number.upper()
        for keywords, disc in _DISCIPLINE_RULES:
            for kw in keywords:
                if kw.upper() in num_upper:
                    return disc

    # Priority 3: Filename (e.g. QD87-TTg_...thuoc_BTP.pdf)
    if filename:
        fn_upper = filename.upper()
        for keywords, disc in _DISCIPLINE_RULES:
            for kw in keywords:
                if kw.upper() in fn_upper:
                    return disc

    # Priority 4: Text content keywords
    if text_head:
        snippet = text_head[:2000].lower()
        for disc, keywords in _TEXT_DISCIPLINE_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in snippet:
                    return disc

    return "TONG_HOP"


# ─────────────────────────────────────────────────────────────────────
# Convenience: classify all three at once
# ─────────────────────────────────────────────────────────────────────

def classify_all(
    doc_number: str = "",
    filename: str = "",
    authority: str = "",
    text_head: str = "",
) -> dict:
    """Return dict with doc_type, legal_level, discipline."""
    dtype = classify_doc_type(doc_number, filename, text_head)
    level = classify_legal_level(dtype, authority)
    disc = classify_discipline(text_head, authority, doc_number, filename)
    return {
        "doc_type": dtype,
        "legal_level": level,
        "discipline": disc,
    }


# ─────────────────────────────────────────────────────────────────────
# 5. SOURCE_CATEGORY — Phân loại nguồn theo thư mục
# ─────────────────────────────────────────────────────────────────────
_CATEGORY_MAP = {
    "CP_": "CHINH_PHU", "QH_": "QUOC_HOI", "UBND": "DIA_PHUONG",
    "Linh vuc": "BO_NGANH", "BCD_": "BAN_CHI_DAO", "BCHTW": "DANG",
    "Quy chuan": "QUY_CHUAN", "QCVN": "QUY_CHUAN",
    "Tieu chuan": "TIEU_CHUAN_QT", "TL ": "TAI_LIEU_KT",
    "TL_": "TAI_LIEU_KT", "TT ": "TRUNG_TAM",
}


def classify_source_category(rel_path: str) -> str:
    """Classify source category from the relative file path or filename."""
    path_lower = rel_path.lower()
    if any(k in rel_path for k in ["QH_", "QH1", "QH2", "Quoc hoi", "Luat_", "Luat "]) or "qh1" in path_lower or "qh2" in path_lower:
        return "QUOC_HOI"
    if any(k in rel_path for k in ["CP_", "ND-CP", "Nghi dinh"]) or "chinh_phu" in path_lower:
        return "CHINH_PHU"
    if any(k in rel_path for k in ["QCVN", "Quy chuan"]):
        return "QUY_CHUAN"
    if any(k in rel_path for k in ["TCVN", "Tieu chuan", "ISO"]):
        return "TIEU_CHUAN_QT"
    if any(k in rel_path for k in ["BXD", "BKHCN", "BTC", "BCT", "BNN", "Linh vuc"]):
        return "BO_NGANH"
    if any(k in rel_path for k in ["BEP", "EIR", "PreBEP", "BIM", "So tay", "Huong dan", "TL ", "TL_"]):
        return "TAI_LIEU_KT"
    if any(k in rel_path for k in ["UBND"]):
        return "DIA_PHUONG"
    for prefix, cat in _CATEGORY_MAP.items():
        if prefix in rel_path:
            return cat
    return "KHAC"

