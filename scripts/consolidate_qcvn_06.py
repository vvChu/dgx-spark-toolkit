"""QCVN 06:2022/BXD DETERMINISTIC LIVING STANDARD CONSOLIDATION ENGINE
=============================================================================
Consolidates all amendment blocks of Sửa đổi 1:2023 (Thông tư 09/2023/TT-BXD)
directly into master qcvn_06_2022_bxd.md (Chapters 1-7) and modular annexes (Phụ lục A-H).

Key Invariants:
1. Pure Verbatim from Official Gazette (Công báo) - No third-party synthetic wording.
2. Single Applier: Replaces any legacy/conflicting consolidator scripts.
3. Clean Headings: Old 2022 body text never lingers inside ### heading lines.
4. Dot-swallowing map: Deterministic resolution with dual anchors for canonical and legacy IDs.
5. Idempotent: Loads pristine 2022 backup baselines to guarantee zero residual drift.
"""

import re
import shutil
from pathlib import Path

VAULT_DIR = Path("/home/vvc/ccba/ccba-legal-knowledge/legal_docs/02_qcvn/qcvn_06_2022_bxd")
MASTER_FILE = VAULT_DIR / "qcvn_06_2022_bxd.md"
BAK_FILE = VAULT_DIR / "qcvn_06_2022_bxd.md.bak"
AMENDMENT_FILE = VAULT_DIR / "sources/sua_doi_1_2023_qcvn_06_2022_bxd.md"
ANNEXES_DIR = VAULT_DIR / "annexes"

CITATION_LINE = "> *[Sửa đổi bởi Thông tư 09/2023/TT-BXD (Sửa đổi 1:2023), hiệu lực 01/12/2023]*\n\n"
REPEAL_LINE = "> *[Bãi bỏ bởi Thông tư 09/2023/TT-BXD (Sửa đổi 1:2023)]*\n\n"

# Deterministic mapping for swallowed dots and hyphen anomalies in legal text
DOT_SWALLOW_MAP = {
    # Master chapters 3-6
    "3.4.13": "muc-3-4-1-3",
    "3.4.14": "muc-3-4-14",
    "4.23": "muc-4-23",
    "4.27": "muc-4-27",
    "4.31": "muc-4-3-1",
    "4.32.2": "muc-4-3-2-2",
    "4.33.3": "muc-4-3-3-3",
    "4.33.4": "muc-4-3-3-4",
    "4.34": "muc-4-3-4",
    "4.35": "muc-4-35",
    "5.1.5.10": "muc-5-1-5-10",
    "6.12": "muc-6-1-2",
    "6.13": "muc-6-13",
    "6.14": "muc-6-14",
    "6.17.1": "muc-6-1-7-1",
    "6.17.2": "muc-6-17-2",
    # Annex A
    "A.1.3.10": "muc-A-1-3-10",
    "A.1.3.12": "muc-A-1-3-12",
    "A.2.11": "muc-A-2-11",
    "A.2.12": "muc-A-2-12",
    "A.2.14": "muc-A-2-14",
    "A.2.20": "muc-A-2-20",
    "A.3.1.13": "muc-A-3-1-13",
    "A.3.1.16": "muc-A-3-1-16",
    # Annex H
    "H.2.10.3": "muc-H-2-10-3",
    "H.2.11.1": "muc-H-2-11-1",
}


def clean_section(text: str, anchor_id: str, new_heading: str, new_body: str, is_repeal: bool = False, dual_anchor: str = None) -> str:
    """Safely replace a section with a clean heading and verbatim body, ensuring no old text remains."""
    cit = REPEAL_LINE if is_repeal else CITATION_LINE
    
    anc_html = f"<a id=\"{anchor_id}\"></a>"
    if dual_anchor:
        anc_html += f"<a id=\"{dual_anchor}\"></a>"
        
    if f"<a id=\"{anchor_id}\"" in new_heading or f"<a id='{anchor_id}'" in new_heading:
        replacement = f"{new_heading}\n\n{cit}{new_body.strip()}\n"
    else:
        replacement = f"{anc_html}\n{new_heading}\n\n{cit}{new_body.strip()}\n"

    # Precise boundary matching: from section start to next section anchor or end
    pat = rf"((?:<a\s+id=[\"\x27]{re.escape(anchor_id)}[\"\x27][^>]*></a>\s*\n*)?(?:#{{1,4}}\s*)?<a\s+id=[\"\x27]{re.escape(anchor_id)}[\"\x27][^>]*></a>[^\n]*(?:\n#{{1,4}}\s+[^\n]+)?.*?)(?=\n(?:#{{1,4}}\s*)?<a\s+id=|\n#{{1,4}}\s+[0-9A-Z]|\n##\s+DANH MỤC|\Z)"
    
    m = re.search(pat, text, flags=re.DOTALL | re.IGNORECASE)
    if not m:
        # Fallback for anchor without duplicate prefix
        pat_fallback = rf"((?:#{{1,4}}\s*)?<a\s+id=[\"\x27]{re.escape(anchor_id)}[\"\x27][^>]*></a>.*?)(?=\n(?:#{{1,4}}\s*)?<a\s+id=|\n#{{1,4}}\s+[0-9A-Z]|\n##\s+DANH MỤC|\Z)"
        m = re.search(pat_fallback, text, flags=re.DOTALL | re.IGNORECASE)
        if not m:
            print(f"  [WARN] Anchor not found: {anchor_id}")
            return text

    start, end = m.span(1)
    new_text = text[:start] + replacement + text[end:]
    return new_text


def consolidate_master(text: str) -> str:
    """Applies all SĐ1 amendments to Master Chapters 1-7."""
    text = text.replace("_GHI CHÚ CHỈ SỐ PHỤ:_\n", "").replace("_GHI CHÚ CHỈ SỐ PHỤ:_", "")

    # 0. Lời nói đầu (Official Provenance only - NO synthetic Living Standard wording)
    loi_noi_dau_old = "02/2021/TT-BXD ngày 19 tháng 5 năm 2021 của Bộ trưởng Bộ Xây dựng."
    loi_noi_dau_new = (
        loi_noi_dau_old + "\n\n"
        "Sửa đổi 1:2023 QCVN 06:2022/BXD do Viện Khoa học công nghệ xây dựng (Bộ Xây dựng) "
        "chủ trì biên soạn, Bộ Xây dựng ban hành kèm theo Thông tư số 09/2023/TT-BXD ngày 10 tháng 10 năm 2023 "
        "của Bộ trưởng Bộ Xây dựng (có hiệu lực từ ngày 01 tháng 12 năm 2023)."
    )
    loi_noi_dau_idx = text.find("## Lời nói đầu")
    muc_1_pos = text.find('id="muc-1"')
    preamble_part = text[loi_noi_dau_idx:muc_1_pos] if (loi_noi_dau_idx != -1 and muc_1_pos != -1) else ""
    if loi_noi_dau_old in preamble_part and "Thông tư số 09/2023/TT-BXD" not in preamble_part:
        text = text.replace(loi_noi_dau_old, loi_noi_dau_new, 1)
        print("  [OK] Updated Lời nói đầu with SĐ1 provenance.")

    # 1.1.2 Scope of residential buildings
    body_1_1_2 = """1.1.2 Quy chuẩn này áp dụng đối với các nhà sau:

a) Nhà ở:

- **1)** Chung cư và nhà ở tập thể có chiều cao PCCC không quá 150 m và không quá 3 tầng hầm;

- **2)** Nhà ở riêng lẻ, nhà ở riêng lẻ có kết hợp mục đích sử dụng khác và nhà ở riêng lẻ được chuyển đổi sang mục đích sử dụng khác có quy mô như sau:
  - cao từ 7 tầng trở lên (hoặc có chiều cao PCCC từ 25 m trở lên);
  - hoặc có khối tích từ 5 000 m3 trở lên;
  - hoặc có nhiều hơn 1 tầng hầm đến 3 tầng hầm.

CHÚ THÍCH: Đối với nhà ở riêng lẻ, nhà ở riêng lẻ có kết hợp các mục đích sử dụng khác, nhà ở riêng lẻ được chuyển đổi sang mục đích sử dụng khác có quy mô khác với quy mô đã nêu tại đoạn 2) điểm 1.1.2 thì có thể áp dụng các yêu cầu an toàn cháy nêu trong tiêu chuẩn về nhà ở riêng lẻ, các tài liệu chuẩn khác để thiết kế an toàn cháy và tuân thủ các quy định pháp luật có liên quan.

b) Các nhà công cộng có chiều cao PCCC đến 150 m và không quá 3 tầng hầm (trừ các công trình trực tiếp sử dụng làm nơi thờ cúng, tín ngưỡng; các công trình di tích); các loại sân thể thao ngoài trời có khán đài;

c) Các nhà sản xuất, nhà kho có chiều cao PCCC đến 50 m và không quá 1 tầng hầm;

d) Các nhà cung cấp cơ sở, tiện ích hạ tầng kỹ thuật có chiều cao PCCC đến 50 m và không quá 1 tầng hầm;

e) Các nhà phục vụ giao thông vận tải có chiều cao PCCC đến 50 m và không quá 3 tầng hầm;

f) Các nhà phục vụ nông nghiệp và phát triển nông thôn (trừ nhà ươm, nhà kính trồng cây và tương tự).

Quy chuẩn này cũng có thể được xem xét áp dụng đối với các nhà không thuộc phạm vi điều chỉnh của quy chuẩn này nếu các yêu cầu trong quy chuẩn này phù hợp với nhà đó.

Đối với các nhà đứng độc lập (trừ các nhà thuộc nhóm F5 và các nhà đã nêu tại CHÚ THÍCH của đoạn 2) điểm 1.1.2) có chiều cao dưới 7 tầng, chiều cao PCCC dưới 25 m và khối tích dưới 5 000 m3), nếu không thể tuân thủ các quy định của quy chuẩn này thì căn cứ trên công năng cụ thể của nhà cũng có thể áp dụng các tài liệu chuẩn để thiết kế an toàn cháy và tuân thủ các quy định pháp luật có liên quan."""
    text = clean_section(text, "muc-1-1-2", "### 1.1.2  Quy chuẩn này áp dụng đối với các nhà sau:", body_1_1_2)

    # 1.1.4 Partial Renovation & Scope
    body_1_1_4 = """1.1.4 Quy chuẩn này áp dụng khi xây dựng mới các nhà thuộc phạm vi điều chỉnh của quy chuẩn này; hoặc chỉ áp dụng đối với các bộ phận, khu vực trực tiếp được cải tạo sửa chữa, trong các trường hợp sau:

a) Cải tạo, sửa chữa thay đổi công năng của tầng nhà, khoang cháy hoặc nhà dẫn đến nâng cao các yêu cầu an toàn cháy đối với tầng nhà, khoang cháy và nhà;

b) Cải tạo, sửa chữa làm thay đổi các giải pháp thoát nạn của tầng nhà, khoang cháy hoặc nhà theo hướng làm giảm số lượng lối thoát nạn hoặc cầu thang thoát nạn;

c) Cải tạo, sửa chữa làm tăng hạng nguy hiểm cháy và cháy nổ của tầng nhà, khoang cháy hoặc nhà;

d) Cải tạo, sửa chữa tăng quy mô dẫn đến nâng cao các yêu cầu an toàn cháy đối với tầng nhà, khoang cháy và nhà.

Trường hợp nhà, khoang cháy hoặc tầng nhà được cải tạo, sửa chữa không thể đáp ứng các yêu cầu của quy chuẩn này thì áp dụng 1.1.10."""
    text = clean_section(text, "muc-1-1-4", "### 1.1.4  Phạm vi áp dụng khi cải tạo, sửa chữa", body_1_1_4)

    # 1.1.5 Special functional buildings
    body_1_1_5 = """1.1.5  Quy chuẩn này không áp dụng cho các nhà có công năng đặc biệt (các nhà và công trình thuộc dây chuyền công nghệ của các cơ sở năng lượng: nhà máy thủy điện, nhiệt điện, điện nguyên tử; điện gió, điện mặt trời, điện địa nhiệt, điện thủy triều, điện rác, điện sinh khối; điện khí blogas; điện đồng phát, tháp kiểm soát không lưu; công trình hầm giao thông; tháp đèn biển; nhà sản xuất hoặc bảo quản các chất và vật liệu nổ; các kho chứa dầu mỏ và sản phẩm dầu mỏ, khí đốt tự nhiên, các loại khí dễ cháy, cũng như các chất tự cháy; cửa hàng kinh doanh xăng dầu, chất lỏng dễ cháy, khí đốt; nhà sản xuất hoặc kho hóa chất độc hại; công trình quốc phòng, an ninh; phần ngầm của công trình tàu điện ngầm; công trình hầm mỏ, và các nhà có đặc điểm tương tự)."""
    text = clean_section(text, "muc-1-1-5", "### 1.1.5  Quy chuẩn này không áp dụng cho các nhà có công năng đặc biệt", body_1_1_5)

    # 1.1.7 Foreign standards
    body_1_1_7 = """1.1.7  Cho phép sử dụng các tài liệu chuẩn của nước ngoài trên cơ sở bảo đảm nguyên tắc quy định tại 1.5 của quy chuẩn này và các quy định pháp luật của Việt Nam về phòng cháy, chữa cháy cùng các quy định về áp dụng tiêu chuẩn của nước ngoài trong hoạt động xây dựng ở Việt Nam."""
    text = clean_section(text, "muc-1-1-7", "### 1.1.7  Sử dụng các tài liệu chuẩn của nước ngoài", body_1_1_7)

    # 1.1.10 Engineering Argumentation
    body_1_1_10 = """1.1.10  Trong một số trường hợp riêng biệt, có thể xem xét bổ sung, thay thế một số yêu cầu của quy chuẩn này đối với công trình cụ thể bằng các yêu cầu an toàn cháy phù hợp khác theo tài liệu chuẩn hoặc có luận chứng kỹ thuật phù hợp."""
    text = clean_section(text, "muc-1-1-10", "### 1.1.10  Giải pháp bổ sung, thay thế theo tài liệu chuẩn hoặc luận chứng kỹ thuật", body_1_1_10)

    # 1.1.11 Local Regulations (Verbatim SĐ1)
    body_1_1_11 = """1.1.11  Các địa phương được ban hành quy chuẩn kỹ thuật địa phương để thay thế, sửa đổi hoặc bổ sung một số quy định tại các phần 3, 4, 5, 6 và các phụ lục của quy chuẩn này cho phù hợp với điều kiện đặc thù của địa phương, trên cơ sở tuân thủ quy định pháp luật về tiêu chuẩn, quy chuẩn kỹ thuật và pháp luật về phòng cháy chữa cháy."""
    text = clean_section(text, "muc-1-1-11", "### 1.1.11  Quy chuẩn kỹ thuật địa phương", body_1_1_11)

    # 1.3 Repealed
    body_1_3 = """*(Nội dung điểm 1.3 đã được bãi bỏ theo quy định tại Thông tư 09/2023/TT-BXD)*"""
    text = clean_section(text, "muc-1-3", "### 1.3  Quy định chung đối với nhà và công trình hiện hữu", body_1_3, is_repeal=True)

    # 1.4.5: sàn ngăn cháy
    if 'id="muc-1-4-5"' in text and "hoặc các bộ phận khác có chức năng ngăn cháy" not in text:
        text = re.sub(r'(<a id="muc-1-4-5"[^>]*></a>.*?sàn ngăn cháy)(?!\s*;\s*hoặc các bộ phận khác)', r'\1; hoặc các bộ phận khác có chức năng ngăn cháy', text)
        print("  [OK] Updated Mục 1.4.5.")

    # 1.4.9: CHÚ THÍCH 4 (Verbatim SĐ1)
    if 'id="muc-1-4-9"' in text:
        note_4_149 = "\n\nCHÚ THÍCH 4: Trong trường hợp các mặt đường tiếp cận nhà có cao độ khác nhau thì nhà có thể có các chiều cao PCCC khác nhau tùy thuộc vào phương án thiết kế an toàn cháy cụ thể."
        m_149 = re.search(r'(<a\s+id=[\"\x27]muc-1-4-9[\"\x27][^>]*></a>.*?)(?=\n(?:#{1,4}\s*)?<a\s+id=|\n#{1,4}\s+[0-9A-Z]|\Z)', text, flags=re.DOTALL)
        if m_149 and "Trong trường hợp các mặt đường tiếp cận nhà có cao độ khác nhau" not in m_149.group(1):
            sec_149 = m_149.group(1) + note_4_149
            text = text[:m_149.start(1)] + sec_149 + text[m_149.end(1):]
            print("  [OK] Added CHÚ THÍCH 4 to Mục 1.4.9.")

    # 1.4.11: Cửa nắp hút khói
    body_1_4_11 = """1.4.11  Cửa nắp hút khói (cửa trời hoặc cửa chớp)

Bộ phận (mở được khi có cháy) được điều khiển tự động và từ xa hoặc luôn mở sẵn, che các lỗ mở trên các kết cấu bao che bên ngoài của không gian nhà (hoặc gian phòng) mà được bảo vệ bằng hệ thống thông gió hút xả khói theo cơ chế tự nhiên."""
    text = clean_section(text, "muc-1-4-11", "#### 1.4.11  Cửa nắp hút khói (cửa trời hoặc cửa chớp)", body_1_4_11)

    # 1.4.21a: Gian phòng chung (Verbatim SĐ1)
    if 'id="muc-1-4-21a"' not in text:
        item_1_4_21a = """<a id="muc-1-4-21a"></a>
#### 1.4.21a  Gian phòng chung

> *[Sửa đổi bởi Thông tư 09/2023/TT-BXD (Sửa đổi 1:2023), hiệu lực 01/12/2023]*

Gian phòng có công năng dùng để tổ chức sự kiện (ví dụ: hội họp, hội thảo, trình diễn, thể thao và tương tự), có sự tập trung cùng lúc một nhóm người, trong một khoảng thời gian được ấn định cụ thể. Nhóm người này có đặc điểm chung là không quen thuộc với địa điểm được tập trung (không thường xuyên hoặc không định kỳ có mặt). Các văn phòng, gian phòng sản xuất, các gian phòng khác mà được sử dụng chủ yếu cho người trong nội bộ tòa nhà thì không được coi là các gian phòng chung (ví dụ: phòng họp nội bộ, phòng ăn nội bộ, phòng sinh hoạt chung nội bộ và tương tự).
"""
        text = re.sub(r'(<a id="muc-1-4-21"[^>]*></a>.*?)(?=\n(?:#{1,4}\s*)?<a id="muc-1-4-22"|\n#### 1\.4\.22)', r'\1\n' + item_1_4_21a + '\n', text, flags=re.DOTALL)
        print("  [OK] Inserted Mục 1.4.21a (Verbatim SĐ1).")
    else:
        body_1_4_21a = """Gian phòng có công năng dùng để tổ chức sự kiện (ví dụ: hội họp, hội thảo, trình diễn, thể thao và tương tự), có sự tập trung cùng lúc một nhóm người, trong một khoảng thời gian được ấn định cụ thể. Nhóm người này có đặc điểm chung là không quen thuộc với địa điểm được tập trung (không thường xuyên hoặc không định kỳ có mặt). Các văn phòng, gian phòng sản xuất, các gian phòng khác mà được sử dụng chủ yếu cho người trong nội bộ tòa nhà thì không được coi là các gian phòng chung (ví dụ: phòng họp nội bộ, phòng ăn nội bộ, phòng sinh hoạt chung nội bộ và tương tự)."""
        text = clean_section(text, "muc-1-4-21a", "#### 1.4.21a  Gian phòng chung", body_1_4_21a)

    # 1.4.22: rename
    text = re.sub(r'1\.4\.22\s+Gian phòng có người làm việc thường xuyên(?!\s*\(hoặc thường xuyên có người\))', '1.4.22  Gian phòng có người làm việc thường xuyên (hoặc thường xuyên có người)', text)

    # 1.4.23: Hành lang bên
    body_1_4_23 = """1.4.23  Hành lang bên

Hành lang mà ở một phía có thông gió với bên ngoài qua các lỗ mở thông với không khí bên ngoài khi có cháy, với chiều cao thông thủy tính từ đỉnh của tường chắn ở mép hành lang lên phía trên không nhỏ hơn 1,2 m.

CHÚ THÍCH: Kích thước các lỗ mở trên tường ngoài của hành lang bên bảo đảm một trong các yêu cầu sau:

- Khi hành lang bên được ngăn cách với các gian phòng liền kề bằng các bộ phận ngăn cháy theo quy định của quy chuẩn thì tổng diện tích các lỗ mở không được nhỏ hơn 15 % diện tích sàn của hành lang bên và khoảng cách từ một điểm bất kỳ trên hành lang bên đến mép gần nhất của lỗ mở bất kỳ không được lớn hơn 9 m, đo theo phương ngang.

- Khi hành lang bên không được ngăn cách với các gian phòng liền kề bằng các bộ phận ngăn cháy thì tổng diện tích các lỗ mở không được nhỏ hơn 50 % diện tích sàn của hành lang bên và khoảng cách từ một điểm bất kỳ trên hành lang bên đến mép gần nhất của lỗ mở bất kỳ không được lớn hơn 9 m."""
    text = clean_section(text, "muc-1-4-23", "#### 1.4.23  Hành lang bên", body_1_4_23)

    # 1.4.26: Hệ thống hút xả khói
    body_1_4_26 = """1.4.26  Hệ thống hút xả khói

Hệ thống được điều khiển tự động và từ xa, hoặc luôn sẵn sàng hoạt động khi có cháy, có tác dụng xả khói và các sản phẩm cháy qua cửa thu khói ra ngoài trời."""
    text = clean_section(text, "muc-1-4-26", "#### 1.4.26  Hệ thống hút xả khói", body_1_4_26)

    # 1.4.32a: Khối đế
    if 'id="muc-1-4-32a"' not in text:
        item_1_4_32a = """<a id="muc-1-4-32a"></a>
#### 1.4.32a  Khối đế

> *[Sửa đổi bởi Thông tư 09/2023/TT-BXD (Sửa đổi 1:2023), hiệu lực 01/12/2023]*

Phần dưới của nhà (có thể bao gồm một số tầng dưới cùng của nhà), thường được thiết kế vươn ra so với kết cấu chịu lực của khối tháp bên trên và thường được sử dụng vào các mục đích thương mại, dịch vụ.
"""
        text = re.sub(r'(<a id="muc-1-4-32"[^>]*></a>.*?)(?=\n(?:#{1,4}\s*)?<a id="muc-1-4-33"|\n#### 1\.4\.33)', r'\1\n' + item_1_4_32a + '\n', text, flags=re.DOTALL)
        print("  [OK] Inserted Mục 1.4.32a.")

    # 1.4.33a: Lối ra ngoài trực tiếp
    if 'id="muc-1-4-33a"' not in text:
        item_1_4_33a = """<a id="muc-1-4-33a"></a>
#### 1.4.33a  Lối ra ngoài trực tiếp

> *[Sửa đổi bởi Thông tư 09/2023/TT-BXD (Sửa đổi 1:2023), hiệu lực 01/12/2023]*

Cửa hoặc lối đi qua các vùng an toàn trong nhà (cùng tầng với lối ra ngoài trực tiếp) để dẫn ra ngoài nhà (ra khỏi các tường bao che của nhà) đến khu vực thoáng mà con người có thể di tản an toàn.

CHÚ THÍCH: Một số trường hợp có thể được coi là lối đi qua các vùng an toàn trong nhà để dẫn ra ngoài nhà như sau:

a) Đi qua khu vực không có tải trọng cháy hoặc có nguy cơ cháy thấp (ví dụ khu vực này có thể có quầy lễ tân, bàn ghế gỗ, kim loại, quạt cây, hoặc các đồ vật tương tự với số lượng hạn chế), khu vực này được ngăn cách với các hành lang và các gian phòng tiếp giáp (nếu có) bằng vách ngăn cháy loại 1 có cửa đi với cơ cấu tự đóng và khe cửa được chèn kín, hoặc ngăn cách bằng giải pháp khác tương đương (ví dụ: giải pháp nêu tại đoạn b) của 4.35, hoặc dùng màn ngăn cháy);

b) Đi qua lối đi hở, có thông khí với ngoài trời (ví dụ hành lang bên, ram dốc), được ngăn cách với các gian phòng, khu vực liền kề bởi bộ phận ngăn cháy làm bằng vật liệu không cháy với giới hạn chịu lửa ít nhất El 30 đối với nhà có bậc chịu lửa I, và phải làm bằng vật liệu không cháy hoặc cháy yếu (Ch1) với giới hạn chịu lửa ít nhất El 15 đối với nhà có bậc chịu lửa II, III, IV;

c) Đi qua các khu vực khác được coi là an toàn đối với con người.
"""
        text = re.sub(r'(<a id="muc-1-4-33"[^>]*></a>.*?)(?=\n(?:#{1,4}\s*)?<a id="muc-1-4-34"|\n#### 1\.4\.34)', r'\1\n' + item_1_4_33a + '\n', text, flags=re.DOTALL)
        print("  [OK] Inserted Mục 1.4.33a.")

    # 1.4.49a: Sảnh thông tầng
    if 'id="muc-1-4-49a"' not in text:
        item_1_4_49a = """<a id="muc-1-4-49a"></a>
#### 1.4.49a  Sảnh thông tầng

> *[Sửa đổi bởi Thông tư 09/2023/TT-BXD (Sửa đổi 1:2023), hiệu lực 01/12/2023]*

Không gian thông tầng của nhà, liên kết từ hai tầng trở lên, thường có bố trí các cửa vào phòng, các lối đi hoặc hành lang thông tầng mở nhìn vào không gian này, có thể có bố trí thang bộ (hở), thang cuốn, hoặc thang máy. Không gian này có thể được sử dụng làm sảnh, tiền sảnh, khu vực thương mại dịch vụ hoặc các công năng tương tự.
"""
        text = re.sub(r'(<a id="muc-1-4-49"[^>]*></a>.*?)(?=\n(?:#{1,4}\s*)?<a id="muc-1-4-50"|\n#### 1\.4\.50)', r'\1\n' + item_1_4_49a + '\n', text, flags=re.DOTALL)
        print("  [OK] Inserted Mục 1.4.49a.")

    # 1.4.50: Tầng lửng
    body_1_4_50 = """1.4.50  Tầng lửng

Tầng trung gian giữa các sàn hoặc giữa một sàn với mái, có diện tích sàn không vượt quá một nửa diện tích sàn tầng ngay bên dưới.

CHÚ THÍCH: Khi tầng lửng có diện tích sàn không quá 300 m2 và được sử dụng với các mục đích: chỉ dùng cho việc bố trí các thiết bị kỹ thuật; hoặc chỉ dùng để phục vụ các mục đích quản trị, điều hành, phụ trợ nội bộ của gian phòng, khoang cháy, tầng nhà ngay bên dưới nó (không dùng cho các mục đích thương mại, công cộng, nơi làm việc thường xuyên của công nhân) thì cho phép không tính tầng lửng này vào số tầng của nhà, không áp dụng các quy định đối với tầng lửng trong quy chuẩn này và chỉ cần bảo đảm đường thoát nạn dẫn trực tiếp xuống sàn tầng ngay bên dưới."""
    text = clean_section(text, "muc-1-4-50", "#### 1.4.50  Tầng lửng", body_1_4_50)

    # 1.5.4: Tiêu chuẩn nước ngoài
    body_1_5_4 = """1.5.4  Trong một số trường hợp cụ thể, nếu áp dụng tiêu chuẩn an toàn cháy của nước ngoài thì phải tuân thủ đầy đủ các yêu cầu an toàn cháy của tiêu chuẩn nước ngoài đó, hoặc lựa chọn áp dụng các quy định của tiêu chuẩn nước ngoài nếu các quy định đó phù hợp với các nguyên tắc quy định tại 1.5 của quy chuẩn này và các quy định pháp luật của Việt Nam về phòng cháy, chữa cháy cùng các quy định về áp dụng tiêu chuẩn của nước ngoài trong hoạt động xây dựng ở Việt Nam."""
    text = clean_section(text, "muc-1-5-4", "### 1.5.4  Áp dụng tiêu chuẩn an toàn cháy của nước ngoài", body_1_5_4)

    # 1.5.5 and 1.5.6 (Insert after 1.5.4 if not present)
    if 'id="muc-1-5-5"' not in text:
        item_1_5_5_6 = """<a id="muc-1-5-5"></a>
### 1.5.5  Sai số cho phép trong thi công xây dựng

> *[Sửa đổi bởi Thông tư 09/2023/TT-BXD (Sửa đổi 1:2023), hiệu lực 01/12/2023]*

Cho phép áp dụng sai số đối với các kích thước hình học trong quá trình thi công xây dựng công trình khi các kích thước này không thể đạt được độ chính xác tuyệt đối do điều kiện thực tế của việc thi công xây dựng. Nếu trong các tài liệu chuẩn không quy định sai số cho phép đối với kích thước cụ thể thì cho phép lấy sai số thi công là ± 5 %.

<a id="muc-1-5-6"></a>
### 1.5.6  Xác định các thông số kỹ thuật theo công năng thực tế

> *[Sửa đổi bởi Thông tư 09/2023/TT-BXD (Sửa đổi 1:2023), hiệu lực 01/12/2023]*

Đối với các nhà, công trình, khoang cháy hoặc gian phòng mà việc xác định các thông số kỹ thuật để phục vụ thiết kế an toàn cháy theo công năng nêu trong hồ sơ thiết kế chưa rõ ràng hoặc công năng thực tế khi đưa vào sử dụng có sự khác biệt so với hồ sơ thiết kế thì các thông số kỹ thuật này phải được xác định dựa trên công năng sử dụng thực tế của nhà, công trình, khoang cháy hoặc gian phòng đó.
"""
        text = re.sub(r'(<a id="muc-1-5-4"[^>]*></a>.*?)(?=\n(?:#{1,4}\s*)?<a id="chuong-2"|\n##\s+2|\n###\s+2)', r'\1\n' + item_1_5_5_6 + '\n', text, flags=re.DOTALL)
        print("  [OK] Inserted Mục 1.5.5 and 1.5.6.")

    # 2.3.2.2 CHÚ THÍCH
    if 'id="muc-2-3-2-2"' in text and "Bảng 4 (trừ cột 6 của Bảng 4)" not in text:
        text = re.sub(r'(<a id="muc-2-3-2-2"[^>]*></a>.*?CHÚ THÍCH:\s*)(.*?)(?=\n\n(?:#{1,4}\s*)?<a id=|\n\n###|\Z)', r'\1Các kết cấu chịu lực của sàn tầng lửng như nêu tại CHÚ THÍCH của 1.4.50, sàn công tác và các giá đỡ nhiều tầng trong các gian phòng sản xuất, phải có giới hạn chịu lửa không nhỏ hơn R 15. Giới hạn chịu lửa của các bộ phận chịu lực khác của nhà lấy theo Bảng 4 (trừ cột 6 của Bảng 4).', text, flags=re.DOTALL)
        print("  [OK] Updated Mục 2.3.2.2.")

    # Bảng 4: Notes
    if 'id="bang-4"' in text and "CHÚ THÍCH 7:" not in text:
        notes_b4 = """\n\nCHÚ THÍCH 7: Đối với các nhà nhóm F5 hạng C có bậc chịu lửa I, cho phép lấy giới hạn chịu lửa của các bộ phận chịu lực của mái (kèo, dầm, xà gồ) không nhỏ hơn R 30, nếu nhà thuộc một trong các trường hợp sau:
- Nhà 1 tầng, được trang bị hệ thống chữa cháy tự động;
- Nhà 1 tầng, có trang bị hệ thống báo cháy tự động và diện tích khoang cháy không vượt quá 25 000 m2;
- Nhà có từ 2 đến 3 tầng, được trang bị hệ thống chữa cháy tự động và diện tích khoang cháy không vượt quá 10 000 m2.

CHÚ THÍCH 8: Không quy định giới hạn chịu lửa của bản thang và chiếu thang trong buồng thang bộ được bảo vệ bởi các tường trong có giới hạn chịu lửa đáp ứng yêu cầu của Bảng 4 tương ứng với bậc chịu lửa của nhà. Khi đó các bản thang và chiếu thang, cũng như vật liệu hoàn thiện bên trong buồng thang (nếu có) phải là vật liệu không cháy hoặc bảo đảm Ch1, BC1."""
        text = re.sub(r'(<a id="bang-4"[^>]*></a>.*?)(?=\n(?:#{1,4}\s*)?<a id="muc-2-4"|\n### 2\.4)', r'\1' + notes_b4 + '\n', text, flags=re.DOTALL)
        print("  [OK] Added CHÚ THÍCH 7 and 8 to Bảng 4.")

    # 2.5.3.3: kết cấu mái không áp mái
    body_2_5_3_3 = """2.5.3.3  Không quy định giới hạn chịu lửa của các cấu kiện không tham gia vào sự bảo đảm độ bền tổng thể và sự ổn định không gian cho nhà khi có cháy. Trường hợp kết cấu giàn, dầm, xà gồ của kết cấu mái của nhà không có tầng áp mái không tham gia vào sự bảo đảm độ bền tổng thể và sự ổn định không gian cho nhà khi có cháy thì giới hạn chịu lửa yêu cầu của các kết cấu này được xác định theo cột 6 của Bảng 4."""
    text = clean_section(text, "muc-2-5-3-3", "### 2.5.3.3  Cấu kiện không tham gia vào sự bảo đảm độ bền tổng thể và sự ổn định không gian", body_2_5_3_3)

    # 3.1.7: Basements
    body_3_1_7 = """3.1.7 Trong các nhà có từ 2 đến 3 tầng hầm, được phép bố trí phòng hút thuốc, các siêu thị và trung tâm thương mại, quán ăn, quán giải khát và các gian phòng công cộng khác nằm sâu hơn tầng hầm 1 khi thiết kế theo các tài liệu chuẩn được phép áp dụng, hoặc có luận chứng kỹ thuật theo 1.1.10.

Đối với bệnh viện và trường phổ thông, chỉ cho phép bố trí các công năng khám bệnh không có điều trị nội trú (khi đó không áp dụng 3.1.6 đối với bệnh viện), các công năng văn phòng, phụ trợ khác từ tầng bán hầm hoặc tầng hầm 1 (trong trường hợp không có tầng bán hầm) trở lên.

Tại tất cả các sàn tầng hầm, ít nhất phải có một lối vào buồng thang bộ thoát nạn đi qua sảnh ngăn khói được ngăn cách với không gian xung quanh bằng vách ngăn cháy loại 1 hoặc giải pháp tương đương khác. Các cửa đi phải là loại có cơ cấu tự đóng."""
    text = clean_section(text, "muc-3-1-7", "### 3.1.7  Bố trí công năng trong các tầng hầm", body_3_1_7)

    # 3.2.2: Lối đi chung qua sảnh
    if 'id="muc-3-2-2"' in text and "nhóm F1.2, F1.3, F2, F3, F4 có chiều cao PCCC dưới 28 m" not in text:
        add_3_2_2 = "\n\nĐối với nhà nhóm F1.2, F1.3, F2, F3, F4 có chiều cao PCCC dưới 28 m, trường hợp không thể bố trí được lối đi riêng ra bên ngoài mà phải đi qua sảnh chung thì lối vào buồng thang bộ chung từ các tầng hầm phải đi qua khoang đệm với giải pháp bao che giống như khoang đệm ngăn cháy loại 1, và phải có vách ngăn cháy loại 1 ngăn cách với phần còn lại của buồng thang bộ;"
        text = re.sub(r'(<a id="muc-3-2-2"[^>]*></a>.*?)(?=\n(?:#{1,4}\s*)?<a id="muc-3-2-3"|\n### 3\.2\.3)', r'\1' + add_3_2_2 + '\n', text, flags=re.DOTALL)
        print("  [OK] Updated Mục 3.2.2.")

    # 3.2.3 Roller shutters / sliding doors
    body_3_2_3 = """3.2.3  Các lối ra không được coi là lối ra thoát nạn nếu trên lối ra này có đặt cửa cuốn hoặc cửa quay.

Được sử dụng cửa trượt hoặc cửa xếp trên lối ra thoát nạn (trừ các trường hợp: cửa này có yêu cầu về giới hạn chịu lửa, hoặc có yêu cầu về việc cửa phải tự đóng kín sau khi mở, hoặc trong các nhà nhóm F1.3, cơ sở mầm non, trường tiểu học và tương đương), khi đó không áp dụng quy định về chiều mở cửa tại 3.2.10, và phải có biển thông báo/ghi chú về loại cửa và chiều mở của cửa."""
    text = clean_section(text, "muc-3-2-3", "### 3.2.3  Quy định về cửa cuốn, cửa trượt, cửa xếp trên lối ra thoát nạn", body_3_2_3)

    # 3.2.5: Gian phòng tầng hầm > 15 người
    if 'id="muc-3-2-5"' in text:
        text = re.sub(r'(<a id="muc-3-2-5"[^>]*></a>.*?b\)\s*)(.*?)(?=\n\s*c\))', r'\1Các gian phòng trong các tầng hầm và tầng nửa hầm có mặt đồng thời hơn 15 người;', text, flags=re.DOTALL)
        print("  [OK] Updated Mục 3.2.5.")

    # 3.2.6.2: Lối thoát nạn khẩn cấp
    if 'id="muc-3-2-6-2"' in text and "lối ra ban công hoặc lô gia" in text:
        text = re.sub(r'(<a id="muc-3-2-6-2"[^>]*></a>.*?a\)\s*)(.*?)(?=\n\s*b\))', r'\1Lối ra ban công hoặc lô gia, mà ở đó có khoảng tường đặc với chiều rộng không nhỏ hơn 1,2 m tính từ mép ban công (lô gia) đến ô cửa sổ (hoặc cửa đi mở ra ban công/lô gia) hoặc không nhỏ hơn 1,6 m giữa các ô cửa mở ra ban công (lô gia). Khoảng tường đặc này phải làm bằng vật liệu không cháy và có giới hạn chịu lửa không thấp hơn El 30 đối với nhà có bậc chịu lửa I, và không thấp hơn El 15 đối với nhà có bậc chịu lửa II, III, IV;', text, flags=re.DOTALL)
        text = re.sub(r'(<a id="muc-3-2-6-2"[^>]*></a>.*?d\)\s*)(.*?)(?=\n\s*###|\n\s*<a id=|\Z)', r'\1Lối ra cầu thang bộ loại 3 hoặc thang leo ngoài nhà dùng cho thoát nạn;', text, flags=re.DOTALL)
        print("  [OK] Updated Mục 3.2.6.2.")

    # 3.2.8: Bố trí phân tán các lối ra thoát nạn (Verbatim SĐ1)
    body_3_2_8 = """3.2.8  Khi có từ hai lối ra thoát nạn trở lên, chúng phải được bố trí phân tán và khi tính toán khả năng thoát nạn của các lối ra cần giả thiết là đám cháy đã ngăn cản không cho người sử dụng thoát nạn qua một trong những lối ra đó. Các lối ra còn lại phải bảo đảm khả năng thoát nạn an toàn cho tất cả số người có trong gian phòng, trên tầng hoặc trong nhà đó (xem Hình I.3).

Khi một gian phòng, một phần nhà hoặc một tầng của nhà yêu cầu phải có từ 2 lối ra thoát nạn trở lên thì ít nhất hai trong số những lối ra thoát nạn đó phải được bố trí phân tán, đặt cách nhau một khoảng bằng hoặc lớn hơn một nửa chiều dài của đường chéo lớn nhất của mặt bằng gian phòng, phần nhà hoặc tầng nhà đó. Khoảng cách giữa hai lối ra thoát nạn được đo theo đường thẳng nối giữa hai cạnh xa nhất của chúng và phải lớn hơn hoặc bằng 7 m. Trường hợp khoảng cách này nhỏ hơn 7 m thì khoảng cách giữa hai lối ra thoát nạn được đo theo đường thẳng nối giữa hai cạnh gần nhất của chúng (xem Hình I.4 a), b), c)).

Nếu nhà được bảo vệ toàn bộ bằng hệ thống chữa cháy tự động Sprinkler, thì khoảng cách này có thể giảm xuống còn 1/3 chiều dài đường chéo lớn nhất của mặt bằng các gian phòng, phần nhà hoặc tầng nhà trên (xem Hình I.4 d)).

Khi có hai buồng thang thoát nạn nối với nhau bằng một hành lang trong hoặc hành lang bên thì khoảng cách giữa hai lối ra thoát nạn (cửa vào buồng thang thoát nạn) được đo dọc theo đường di chuyển theo hành lang đó (xem Hình I.5). Hành lang này phải được bảo vệ theo quy định tại 3.3.5."""
    text = clean_section(text, "muc-3-2-8", "### 3.2.8  Bố trí phân tán các lối ra thoát nạn", body_3_2_8)

    # 3.2.9: Cửa hai cánh tự đóng lần lượt
    if 'id="muc-3-2-9"' in text:
        text = re.sub(r'Cửa hai cánh phải được lắp cơ cấu tự đóng sao cho các cánh được đóng lần lượt\.', 'Cửa hai cánh nếu có yêu cầu về giới hạn chịu lửa thì phải được lắp cơ cấu tự đóng sao cho các cánh được đóng lần lượt.', text)
        print("  [OK] Updated Mục 3.2.9.")

    # 3.2.11: repeal sentence 2 of paragraph 1
    if 'id="muc-3-2-11"' in text:
        p_3_2_11 = r'(Trong các nhà có chiều cao PCCC lớn hơn 15 m, các cánh cửa nói trên, ngoại trừ các cửa của căn hộ, phải là cửa đặc hoặc cửa với kính cường lực\.)'
        if re.search(p_3_2_11, text):
            text = re.sub(p_3_2_11, r'*(Đoạn văn này đã được bãi bỏ theo Thông tư 09/2023/TT-BXD)*', text)
            print("  [OK] Repealed sentence 2 of paragraph 1 at Mục 3.2.11.")

    # 3.3.1: replace TCVN 3890 with tài liệu chuẩn
    body_3_3_1 = """3.3.1  Các đường thoát nạn phải được chiếu sáng và chỉ dẫn phù hợp với các yêu cầu tại tài liệu chuẩn."""
    text = clean_section(text, "muc-3-3-1", "### 3.3.1  Các đường thoát nạn phải được chiếu sáng và chỉ dẫn phù hợp với các yêu cầu tại tài liệu chuẩn", body_3_3_1)

    # 3.3.2: Khoảng cách thoát nạn giới hạn cho phép (Verbatim SĐ1)
    body_3_3_2 = """3.3.2  Khoảng cách thoát nạn giới hạn cho phép (Phụ lục G) trên mỗi tầng được đo dọc theo tâm đường thoát nạn, bắt đầu từ tâm của cửa các gian phòng hoặc từ chỗ xa nhất có thể có người trong phòng (tùy thuộc vào việc có ngăn cháy giữa gian phòng và đường thoát nạn hay không) đến tâm của lối ra thoát nạn gần nhất của mỗi tầng (ví dụ: cửa ra ngoài nhà, cửa vào buồng thang bộ hoặc cửa ra cầu thang bộ loại 3, mép bậc đầu tiên của cầu thang bộ loại 2 trên tầng đó nếu cầu thang loại 2 là cầu thang thoát nạn, cửa vào khoang cháy lân cận, hoặc đến lối ra thoát nạn khác). Khoảng cách này phải được hạn chế tùy thuộc vào:

- Nhóm nguy hiểm cháy theo công năng và bậc chịu lửa của nhà và công trình;

- Hạng nguy hiểm cháy và cháy nổ của gian phòng;

- Số người thoát nạn;

- Thông số hình học của các gian phòng và các đường thoát nạn;

- Cấp nguy hiểm cháy kết cấu của nhà.

_CHÚ THÍCH: Các yêu cầu cụ thể về khoảng cách thoát nạn được quy định tại Phụ lục G._"""
    text = clean_section(text, "muc-3-3-2", "### 3.3.2  Khoảng cách thoát nạn giới hạn cho phép", body_3_3_2)

    # 3.3.5: Bao che hành lang thoát nạn và vách ngăn khói 2,5 m (Verbatim SĐ1)
    body_3_3_5 = """3.3.5  Trong các hành lang trên lối ra thoát nạn nêu tại 3.2.1, ngoại trừ những trường hợp nói riêng trong quy chuẩn, không cho phép bố trí: thiết bị nhô ra khỏi mặt phẳng của tường trên độ cao nhỏ hơn 2 m; các ống dẫn khi cháy và ống dẫn các chất lỏng cháy được, cũng như các tủ tường, trừ các tủ thông tin liên lạc và tủ đặt họng nước chữa cháy.

Các hành lang, sảnh, phòng chung trên đường thoát nạn phải được bao che bằng các bộ phận ngăn cháy phù hợp quy định trong các quy chuẩn cho từng loại công trình Bộ phận ngăn cháy bao che đường thoát nạn của nhà có bậc chịu lửa I phải làm bằng vật liệu không cháy với giới hạn chịu lửa ít nhất El 30, và của nhà có bậc chịu lửa II, III, IV phải làm bằng vật liệu không cháy hoặc cháy yếu (Ch1) với giới hạn chịu lửa ít nhất El 15. Riêng nhà có bậc chịu lửa II của hạng nguy hiểm cháy và cháy nổ D, E (xem Phụ lục C) có thể bao che hành lang bằng tường kính.

Riêng nhà có hạng nguy hiểm cháy và cháy nổ D, E có thể bao che hành lang bằng tường kính hoặc bộ phận bao che từ vật liệu không cháy. Không yêu cầu giới hạn chịu lửa của tường ngăn và các ô cửa giữa các gian phòng và hành lang bên (trừ các gian phòng nhóm F5 hạng A, B, C hoặc bếp).

Đối với các tầng nhà có hành lang, gian phòng không được bao che bằng các bộ phận ngăn cháy theo quy định tại điểm 3.3.5 hoặc không tuân thủ yêu cầu tại 3.3.4 thì khoảng cách giới hạn cho phép của đường thoát nạn (Phụ lục G) phải tính từ điểm xa nhất có thể có người của gian phòng trên tầng nhà đó. Riêng các nhà kinh doanh dịch vụ karaoke, vũ trường phải bảo đảm việc ngăn cách hành lang, gian phòng trên đường thoát nạn bằng các bộ phận ngăn cháy như quy định ở trên. Các nhà nhóm F1.3 phải tuân thủ quy định tại 4.5.

Các hành lang dài hơn 60 m phải được phân chia bằng các vách ngăn cháy loại 2 (hoặc bằng các vách ngăn khói, màn ngăn khói, có mép dưới cách sàn hành lang tối đa 2,5 m) thành các đoạn có chiều dài được xác định theo yêu cầu bảo vệ chống khói nêu tại Phụ lục D, nhưng không được vượt quá 60 m. Các cửa đi trong các vách ngăn cháy này phải phù hợp với các yêu cầu tại 3.2.1.1.

Khi các cánh cửa đi của gian phòng mở nhô ra hành lang, thì chiều rộng của đường thoát nạn theo hành lang được lấy bằng chiều rộng thông thủy của hành lang trừ đi:

- Một nửa chiều rộng phần nhỏ ra của cánh cửa (tính cho cửa nhỏ ra nhiều nhất) - khi cửa được bố trí một bên hành lang;

- Cả chiều rộng phần nhô ra của cánh cửa (tính cho cửa nhô ra nhiều nhất) - khi các cửa được bố trí hai bên hành lang. Yêu cầu này không áp dụng cho hành lang tầng (sảnh chung) nằm giữa cửa ra từ căn hộ và cửa ra dẫn vào buồng thang bộ trong các đơn nguyên nhà nhóm F1.3."""
    text = clean_section(text, "muc-3-3-5", "### 3.3.5  Bao che hành lang thoát nạn và phân chia đoạn hành lang", body_3_3_5)

    # 3.4.1: Chiều rộng bản thang
    if 'id="muc-3-4-1"' in text and "nhà nhóm F1.2, F1.3, F2, F3, F4 có tổng số người thoát nạn" not in text:
        text = re.sub(r'(<a id="muc-3-4-1"[^>]*></a>.*?0,9 m - cho tất cả các trường hợp còn lại\.)', r'\1\n\n- 0,7 m - cho các cầu thang bộ thoát nạn trong các nhà nhóm F1.2, F1.3, F2, F3, F4 có tổng số người thoát nạn trên tất cả các tầng không quá 15 người.', text, flags=re.DOTALL)
        print("  [OK] Updated Mục 3.4.1.")

    # 3.4.4: Thang cong và bậc thang chéo (Verbatim SĐ1)
    body_3_4_4 = """3.4.4  Được sử dụng thang cong toàn phần hoặc một phần, thang với các bậc thang chéo khi đáp ứng một trong hai điều kiện sau: 1) mỗi bậc thang có một phần mặt bậc thỏa mãn các điều kiện nêu tại 3.4.1 và 3.4.2; hoặc 2) thỏa mãn các điều kiện nêu dưới đây đối với nhóm nhà cụ thể. Đối với nhà nhóm F1.4, không áp dụng quy định tại 3.3.7.

Trong các nhà thuộc nhóm nguy hiểm cháy theo công năng F1.2, F1.3, F2, F3, F4, F5 cho phép bố trí cầu thang cong trên đường thoát nạn khi bảo đảm tất cả những điều kiện sau:

- Chiều cao của thang không quá 9,0 m;

- Chiều rộng của vế thang phù hợp với các quy định trong quy chuẩn này;

- Bán kính cong nhỏ nhất không nhỏ hơn 2 lần chiều rộng vế thang;

- Chiều cao cổ bậc nằm trong khoảng từ 150 mm đến 190 mm;

- Chiều rộng phía trong của mặt bậc (đo cách đầu nhỏ nhất của bậc 270 mm) không nhỏ hơn 220 mm;

- Chiều rộng đo tại giữa chiều dài của mặt bậc không nhỏ hơn 250 mm;

- Chiều rộng phía ngoài của mặt bậc (đo cách đầu to nhất của bậc 270 mm) không quá 450 mm;

- Tổng của 2 lần chiều cao cổ bậc với chiều rộng phía trong mặt bậc không nhỏ hơn 480 mm và với chiều rộng phía ngoài của mặt bậc không lớn hơn 800 mm.

Trong các nhà nhóm F1.2, F1.3, F2, F3, F4, F5 với chiều cao PCCC không quá 15 m và số người tối đa trên mỗi tầng không quá 15 người, tại mỗi chiếu nghỉ hoặc góc xoay bản thang không quá 90° cho phép bố trí tối đa 3 bậc thang chéo (rẻ quạt)."""
    text = clean_section(text, "muc-3-4-4", "### 3.4.4  Bố trí cầu thang cong và bậc thang chéo trên đường thoát nạn", body_3_4_4)

    # 3.4.5: Chiếu nghỉ cầu thang
    body_3_4_5 = """3.4.5  Trên lối ra thoát nạn không cho phép bố trí các cầu thang xoắn ốc (toàn phần hoặc từng phần mà không đáp ứng 3.4.4). Chiều rộng của chiếu thang bộ không được nhỏ hơn chiều rộng của bản thang. Chiều rộng của chiếu nghỉ giữa các bản thang buồng thang bộ phải không nhỏ hơn chiều rộng của bản thang và không nhỏ hơn 1 m. Không quy định chiều rộng này đối với chiếu nghỉ giữa các bản thang của cầu thang loại 2, loại 3."""
    text = clean_section(text, "muc-3-4-5", "### 3.4.5  Chiều rộng chiếu thang và chiếu nghỉ cầu thang", body_3_4_5)

    # 3.4.8: Chiếu sáng buồng thang bộ và lỗ thoát khói tum thang (Verbatim SĐ1)
    body_3_4_8 = """3.4.8  Các buồng thang bộ phải được bảo đảm chiếu sáng tự nhiên hoặc nhân tạo.

a) Trường hợp chiếu sáng tự nhiên:

Trừ buồng thang bộ loại L2 và phần cầu thang tại tầng hầm, tầng bán hầm, việc bảo đảm chiếu sáng có thể được thực hiện bằng các lỗ lấy ánh sáng với diện tích không nhỏ hơn 1,2 m2 trên các tường ngoài ở mỗi tầng.

Các buồng thang bộ loại L2 phải có lỗ lấy ánh sáng trên mái có diện tích không nhỏ hơn 4 m2 với khoảng hở giữa các vế thang có chiều rộng không nhỏ hơn 0,7 m hoặc giếng lấy sáng theo suốt chiều cao của buồng thang bộ với diện tích mặt cắt ngang không nhỏ hơn 2 m2.

Cho phép bố trí không quá 50 % buồng thang bộ bên trong không có các lỗ lấy ánh sáng, dùng để thoát nạn, trong các trường hợp sau:

- Các nhà thuộc nhóm F2, F3 và F4: đối với buồng thang loại N2 hoặc N3 có áp suất không khí dương khi cháy;

- Các nhà thuộc nhóm F5 hạng C có chiều cao PCCC tới 28 m, còn hạng D và E không phụ thuộc chiều cao PCCC của nhà: đối với buồng thang loại N3 có áp suất không khí dương khi cháy.

b) Trường hợp chiếu sáng nhân tạo:

Trường hợp không bố trí được các lỗ cửa như quy định tại đoạn a) của 3.4.8 thì các buồng thang bộ thoát nạn phải được trang bị chiếu sáng nhân tạo, được cấp điện như chú thích tại 3.4.1.3 bảo đảm nguyên tắc duy trì liên tục nguồn điện cấp cho hệ thống chiếu sáng hoạt động ổn định khi có cháy xảy ra, và ánh sáng phải đủ để người thoát nạn theo các buồng thang này có thể nhìn rõ đường thoát nạn và không bị lóa mắt.

Nếu là buồng thang bộ thông thường thì phải bố trí các lỗ thoát khói trên tum thang với tổng diện tích tối thiểu bằng 10 % diện tích phủ bì (tính cả tường bao che) của sàn buồng thang (không yêu cầu bố trí lỗ thoát khói nếu nhà có tối thiểu hai cầu thang thoát nạn hoặc một cầu thang thoát nạn nhưng có các lối thoát nạn khẩn cấp khác như quy định tại 3.2.6.2)."""
    text = clean_section(text, "muc-3-4-8", "### 3.4.8  Chiếu sáng buồng thang bộ và giải pháp thoát khói tum thang", body_3_4_8)

    # 3.4.11: Bản thang loại 3 dốc 60°
    if 'id="muc-3-4-11"' in text and "chiều rộng bản thang không nhỏ hơn 0,7 m" not in text:
        add_3_4_11 = "\n\nCho phép sử dụng cầu thang bộ loại 3 với góc nghiêng đến 60°, chiều rộng bản thang không nhỏ hơn 0,7 m cho nhà thuộc mọi nhóm nguy hiểm cháy theo công năng có chiều cao PCCC không quá 15 m và số người lớn nhất trên mỗi tầng không quá 15 người."
        text = re.sub(r'(<a id="muc-3-4-11"[^>]*></a>.*?)(?=\n(?:#{1,4}\s*)?<a id="muc-3-4-12"|\n### 3\.4\.12)', r'\1' + add_3_4_11 + '\n', text, flags=re.DOTALL)
        print("  [OK] Updated Mục 3.4.11.")

    # 3.4.13: Cửa vào buồng thang bộ không nhiễm khói (Verbatim SĐ1)
    body_3_4_13 = """3.4.13  Cửa vào buồng thang bộ không nhiễm khói loại N1 phải đi qua khoang đệm hoặc đi qua lối đi hở (ban công, lô gia, hành lang bên) được thông gió tự nhiên với bên ngoài trời. Khoang đệm hoặc lối đi hở phải tuân thủ các quy định tại 3.4.14 hoặc tài liệu chuẩn áp dụng.

CHÚ THÍCH: Yêu cầu về ngăn cách đối với các phần nhà có bậc chịu lửa, cấp nguy hiểm cháy hoặc công năng khác nhau tuân thủ 2.4.3.3."""
    text = clean_section(text, "muc-3-4-1-3", "### 3.4.13  Cửa vào buồng thang bộ không nhiễm khói loại N1", body_3_4_13)

    # 3.4.14: Chiều rộng lối đi hở dẫn vào buồng thang N1
    body_3_4_14 = """3.4.14  Lối đi hở dẫn vào buồng thang bộ không nhiễm khói loại N1 phải có chiều rộng thông thủy không nhỏ hơn 1,2 m và chiều cao của lan can (tường chắn) không nhỏ hơn 1,2 m. Chiều rộng của phần tường đặc giữa các ô cửa mở vào lối đi hở không được nhỏ hơn 1,2 m. Không quy định chiều rộng phần tường đặc này nếu các cửa đi là cửa ngăn cháy loại 1."""
    text = clean_section(text, "muc-3-4-14", "### 3.4.14  Lối đi hở dẫn vào buồng thang bộ không nhiễm khói loại N1", body_3_4_14)

    # 3.5.10: Chiều rộng lối thoát nạn
    body_3_5_10 = """3.5.10  Chiều rộng thông thủy của lối thoát nạn được xác định theo tính toán thoát nạn nhưng không được nhỏ hơn các giá trị quy định tại 3.2.9."""
    text = clean_section(text, "muc-3-5-10", "### 3.5.10  Chiều rộng thông thủy của lối thoát nạn", body_3_5_10)

    # 4.5: Ngăn cách công năng và EI 45 / EI 15 (Verbatim SĐ1)
    body_4_5 = """4.5  Các bộ phận của nhà hoặc các gian phòng thuộc các nhóm nguy hiểm cháy theo công năng khác nhau phải được ngăn cách với nhau bằng bộ phận ngăn cháy có giới hạn chịu lửa tối thiểu El 45 đối với nhà có bậc chịu lửa I đến III; tối thiểu El 15 đối với nhà có bậc chịu lửa IV; hoặc giải pháp ngăn cháy tương đương khác, trừ khi có các quy định riêng trong quy chuẩn này hoặc tiêu chuẩn chuyên ngành.

Trong các nhà nhóm F1, F2, F3, F4, không yêu cầu ngăn cháy với các công năng khác đối với các gian phòng sau (trừ các trường hợp riêng được quy định trong quy chuẩn này hoặc tiêu chuẩn chuyên ngành): các gian phòng nhóm F5 hạng C4, E; các gian phòng kỹ thuật nước; các gian phòng ẩm ướt hoặc có nguy cơ cháy thấp; phòng kho diện tích tối đa 10 m2 không chứa các chất khí dễ cháy và chất lỏng dễ cháy; các gian phòng không có yêu cầu trang bị chữa cháy tự động hoặc báo cháy tự động theo tài liệu chuẩn; các khu vực chỉ phục vụ ăn uống (không có bếp nấu và kho lưu trữ thực phẩm); các phòng họp nội bộ; và các trường hợp tương tự khác.

Đối với một tầng nhà (hoặc một phần tầng nhà đã được ngăn cách với phần còn lại theo quy định của quy chuẩn này) có từ hai công năng khác nhau trở lên, nếu không ngăn cách các công năng theo quy định tại quy chuẩn này thì các yêu cầu an toàn cháy đối với tầng nhà (hoặc phần tầng nhà) này phải lấy theo yêu cầu cao nhất giữa các công năng. Phải ngăn cách các khu vực có nhóm nguy hiểm cháy theo công năng A, B, C với các khu vực có công năng ở hoặc công năng công cộng khác.

CHÚ THÍCH: Các yêu cầu cụ thể về ngăn chia khoang cháy và bộ phận ngăn cháy cho các nhóm nhà cụ thể được quy định tại Phụ lục A và Phụ lục H."""
    text = clean_section(text, "muc-4-5", "### 4.5  Ngăn cách giữa các bộ phận nhà có nhóm nguy hiểm cháy theo công năng khác nhau", body_4_5)

    # 4.23: Cửa ngăn cháy
    body_4_23 = """4.23  Các cửa ngăn cháy trên các bộ phận ngăn cháy phải là loại cửa tự đóng hoặc cửa mở tự động có liên động đóng khi có cháy. Cửa trên vách ngăn cháy loại 1 phải có giới hạn chịu lửa không thấp hơn El 60. Cửa trên vách ngăn cháy loại 2 phải có giới hạn chịu lửa không thấp hơn El 30. Cửa trên vách ngăn cháy loại 3 hoặc trên các vách ngăn khác có yêu cầu về giới hạn chịu lửa thì giới hạn chịu lửa của cửa không được thấp hơn El 15."""
    text = clean_section(text, "muc-4-23", "### 4.23  Cửa trên các bộ phận ngăn cháy", body_4_23)

    # 4.27: Thang bộ loại 2
    body_4_27 = """4.27  Khu vực có cầu thang bộ loại 2 (hở) phải được ngăn cách với các hành lang và các gian phòng lân cận bằng vách ngăn cháy loại 1, hoặc giải pháp tương đương khác phù hợp với tài liệu chuẩn áp dụng. Cửa đi trên vách ngăn này phải là cửa ngăn cháy có cơ cấu tự đóng."""
    text = clean_section(text, "muc-4-27", "### 4.27  Ngăn cách khu vực có cầu thang bộ loại 2", body_4_27)

    # 4.3.1 (4.31): Tài liệu chuẩn
    body_4_3_1 = """4.3.1  Việc trang bị hệ thống báo cháy và chữa cháy tự động phải tuân theo tài liệu chuẩn."""
    text = clean_section(text, "muc-4-3-1", "### 4.3.1  Trang bị hệ thống báo cháy và chữa cháy tự động", body_4_3_1)

    # 4.3.2.2 (4.32.2): Miễn áp dụng khoảng cách khi có chữa cháy tự động
    body_4_3_2_2 = """4.3.2.2  Cho phép không áp dụng các quy định tại 4.3.2.1 nếu nhà được trang bị chữa cháy tự động."""
    text = clean_section(text, "muc-4-3-2-2", "### 4.3.2.2  Miễn áp dụng quy định khoảng cách khi có chữa cháy tự động", body_4_3_2_2)

    # 4.3.3.3 (4.33.3): Lỗ mở tường ngoài góc hẹp
    body_4_3_3_3 = """4.3.3.3  Khi một phần tường ngoài của nhà nối tiếp với một phần khác của tường, tạo thành một góc nhỏ hơn 135° và khoảng cách theo phương nằm ngang giữa các mép gần nhất của các lỗ mở ở tường ngoài theo các hướng khác nhau của định góc, nhỏ hơn 4 m, thì trên phần tương ứng của tường, các lỗ mở phải có các cửa ngăn cháy có giới hạn chịu lửa không nhỏ hơn E 30 hoặc có hệ thống phun nước như quy định tại đoạn c) điểm 4.3.3.1."""
    text = clean_section(text, "muc-4-3-3-3", "### 4.3.3.3  Lỗ mở tường ngoài góc hẹp", body_4_3_3_3)

    # 4.3.3.4 (4.33.4): Miễn áp dụng đối với tường ngoài
    body_4_3_3_4 = """4.3.3.4  Cho phép không áp dụng các quy định tại 4.3.3 đối với nhà từ ba tầng trở xuống hoặc có chiều cao PCCC dưới 15 m, ga ra để xe nổi dạng hở, hoặc nhà được trang bị chữa cháy tự động."""
    text = clean_section(text, "muc-4-3-3-4", "### 4.3.3.4  Miễn áp dụng quy định đối với tường ngoài", body_4_3_3_4)

    # 4.3.4 (4.34): thay "và" bằng "hoặc"
    if 'id="muc-4-3-4"' in text:
        text = re.sub(r'(<a id="muc-4-3-4"[^>]*></a>.*?\([^\)]*Phụ lục E\)\s*)(và)(\s+chữa cháy tự động)', r'\1hoặc\3', text)
        print("  [OK] Updated Mục 4.3.4.")

    # 4.35: Sảnh thông tầng theo Phụ lục H
    if 'id="muc-4-35"' in text:
        text = re.sub(r'(<a id="muc-4-35"[^>]*></a>.*?d\)\s*)(.*?)(?=\n\s*e\)|\n\s*###|\n\s*<a id="muc-4-36")', r'\1Diện tích tầng trong phạm vi khoang cháy có sảnh thông tầng được xác định theo Phụ lục H.', text, flags=re.DOTALL)
        print("  [OK] Updated Mục 4.35 đoạn d).")

    # 5.1.1.1: Cấp nước chữa cháy hạ tầng kỹ thuật
    body_5_1_1_1 = """5.1.1.1  Việc trang bị cấp nước chữa cháy ngoài nhà phải được thực hiện khi đầu tư xây dựng hạ tầng kỹ thuật của các khu dân cư, đô thị, khu công nghiệp, khu chế xuất, khu công nghệ cao, cụm công nghiệp và các khu có đặc điểm tương tự.

Đối với các nhà khi nằm trong phạm vi phục vụ của các nguồn cấp nước chữa cháy ngoài nhà (bồn, bể, trụ nước chữa cháy ngoài nhà, hồ nước chữa cháy tự nhiên và nhân tạo và các nguồn nước tương tự khác) thì không yêu cầu bắt buộc phải trang bị cấp nước chữa cháy ngoài nhà.

CHÚ THÍCH: Việc trang bị cấp nước chữa cháy ngoài nhà có thể tham khảo TCVN 3890:2023."""
    text = clean_section(text, "muc-5-1-1-1", "### 5.1.1.1  Trang bị cấp nước chữa cháy ngoài nhà", body_5_1_1_1)

    # 5.1.1.3: Bãi bỏ "được trang bị phương tiện"
    body_5_1_1_3 = """5.1.1.3  Hệ thống đường ống nước chữa cháy của mạng ngoài nhà phải bảo đảm lưu lượng và áp suất nước yêu cầu."""
    text = clean_section(text, "muc-5-1-1-3", "### 5.1.1.3  Hệ thống đường ống nước chữa cháy ngoài nhà", body_5_1_1_3)

    # 5.1.1.4: Áp suất m cột nước
    body_5_1_1_4 = """5.1.1.4  Áp suất tự do tối thiểu trong đường ống nước chữa cháy áp suất thấp (đo ở vị trí cao độ bằng với mặt đất) khi chữa cháy phải không nhỏ hơn 10 m cột nước. Áp suất tự do tối thiểu trong mạng đường ống chữa cháy áp suất cao phải bảo đảm độ cao tia nước đặc không nhỏ hơn 10 m cột nước khi lưu lượng yêu cầu chữa cháy tối đa và lăng chữa cháy ở điểm cao nhất của tòa nhà. Áp suất tự do trong mạng đường ống kết hợp sinh hoạt hoặc sản xuất không nhỏ hơn 10 m cột nước và không lớn hơn 60 m cột nước."""
    text = clean_section(text, "muc-5-1-1-4", "### 5.1.1.4  Áp suất tự do tối thiểu trong đường ống nước chữa cháy", body_5_1_1_4)

    # Bảng 7: bãi bỏ CHÚ THÍCH 3
    if 'id="bang-7"' in text:
        p_b7_note3 = r'(\*\*CHÚ THÍCH 3:\*\*\s*Số đám cháy đồng thời và lưu lượng nước cho 1 đám cháy cho một vùng có số dân trên 1 triệu người.*?)(?=\n\n\*\*CHÚ THÍCH 4:|\n### <a id="bang-8")'
        if re.search(p_b7_note3, text, flags=re.DOTALL):
            text = re.sub(p_b7_note3, r'*(CHÚ THÍCH 3 đã được bãi bỏ theo Thông tư 09/2023/TT-BXD)*\n', text, flags=re.DOTALL)
            print("  [OK] Repealed CHÚ THÍCH 3 of Bảng 7.")

    # Bảng 10: Clean Table + Exact Title ("không có lỗ mở trên mái")
    body_bang_10 = """| Bậc chịu lửa của nhà | Cấp nguy hiểm cháy kết cấu của nhà | Hạng nguy hiểm cháy và cháy nổ của nhà | ≤ 50 | > 50 và ≤ 100 | > 100 và ≤ 200 | > 200 và ≤ 300 | > 300 và ≤ 400 | > 400 và ≤ 500 | > 500 và ≤ 600 | > 600 và ≤ 700 | > 700 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| I và II | S0, S1 | A, B, C | 20 | 30 | 40 | 50 | 60 | 70 | 80 | 90 | 100 |
| I và II | S0 | D, E | 10 | 15 | 20 | 25 | 30 | 35 | 40 | 45 | 50 |
| III | S0, S1 | A, B, C | 40 | 50 | 60 | 60 | 70 | 80 | 90 | 100 | 110 |
| III | S0, S1 | D, E | 20 | 35 | 40 | 40 | 45 | 45 | 50 | 50 | 60 |
| IV | S0, S1 | A, B, C | 50 | 60 | 65 | 70 | 80 | 90 | - | - | - |
| IV | S0, S1 | D, E | 35 | 45 | 55 | 60 | 65 | 70 | 75 | 80 | 90 |
| IV | S2, S3 | E | 40 | 50 | 60 | - | - | - | - | - | - |

_CHÚ THÍCH: Lỗ mở trên mái là các lỗ mở để thông gió hoặc lấy sáng đặt trên kết cấu mái của nhà (nóc gió (cửa trời); lỗ thường xuyên mở; lỗ mở khi có cháy; ô kính; tấm lợp lấy sáng, hoặc các lỗ mở tương tự) có diện tích không nhỏ hơn 2,5 % diện tích xây dựng của nhà đó._"""
    text = clean_section(text, "bang-10", "### <a id=\"bang-10\" name=\"bang-10\"></a>Bảng 10 - Lưu lượng nước cho chữa cháy ngoài nhà cho nhà nhóm F5 không có lỗ mở trên mái có chiều rộng trên 60 m", body_bang_10)

    # 5.1.3.3: Thời gian chữa cháy 1 giờ
    if 'id="muc-5-1-3-3"' in text and "thời gian chữa cháy của chúng lấy là 1 giờ" not in text:
        add_5_1_3_3 = "\n\n- Đối với các nhà có yêu cầu về lưu lượng cho cấp nước chữa cháy ngoài nhà quy định tại các bảng 8, 9, 10 đến 15 L/s (cho nhà nhóm F1, F2, F3, F4) và đến 20 L/s (cho nhà nhóm F5) thì thời gian chữa cháy của chúng lấy là 1 giờ."
        text = re.sub(r'(<a id="muc-5-1-3-3"[^>]*></a>.*?)(?=\n(?:#{1,4}\s*)?<a id="muc-5-1-3-4"|\n### 5\.1\.3\.4)', r'\1' + add_5_1_3_3 + '\n', text, flags=re.DOTALL)
        print("  [OK] Updated Mục 5.1.3.3.")

    # 5.1.3.4: Bể nước chữa cháy
    body_5_1_3_4 = """5.1.3.4  Lượng nước dự trữ cho chữa cháy ngoài nhà được phép tính toán kết hợp trong các bể nước chữa cháy của nhà hoặc chung cho các nhà trong cụm công trình."""
    text = clean_section(text, "muc-5-1-3-4", "### 5.1.3.4  Lượng nước dự trữ cho chữa cháy ngoài nhà", body_5_1_3_4)

    # 5.1.4.2: Khoảng cách trụ nước
    if 'id="muc-5-1-4-2"' in text and "trụ nước chữa cháy ngoài nhà phải bố trí cách mép đường không quá 5 m" not in text:
        text = re.sub(r'(<a id="muc-5-1-4-2"[^>]*></a>.*?- Các trụ nước chữa cháy ngoài nhà phải bố trí dọc theo đường giao thông.*?)(?=\n-|\n###|\Z)', r'\1 Các trụ nước chữa cháy ngoài nhà phải bố trí cách mép đường không quá 5 m và cách tường nhà không gần hơn 3 m;', text, flags=re.DOTALL)
        print("  [OK] Updated Mục 5.1.4.2.")

    # 5.1.4.7: Bán kính phục vụ hơn 400 m
    body_5_1_4_7 = """5.1.4.7  Khoảng cách từ các điểm của mạng lưới đường ống cấp nước chữa cháy (trụ nước chữa cháy ngoài nhà) hoặc từ các bồn, bể, hồ nước chữa cháy đến các nhà được bảo vệ không được vượt quá bán kính phục vụ của chúng:

- Đối với các trụ nước chữa cháy ngoài nhà: bán kính phục vụ xác định theo chiều dài đường vòi triển khai thực tế của lực lượng chữa cháy từ trụ nước đến vị trí lăng chữa cháy, nhưng không được vượt quá 200 m;

- Đối với các bồn, bể, hồ nước chữa cháy: khoảng cách di chuyển thực tế từ các bồn, bể, hồ này đến bãi đỗ xe hoặc bãi lấy nước không được lớn hơn 400 m khi có máy bơm chữa cháy di động hoặc xe chữa cháy hút nước trực tiếp từ các bồn, bể, hồ này; hoặc không vượt quá bán kính phục vụ của các trụ nước chữa cháy ngoài nhà nếu các bồn, bể, hồ này được kết nối với mạng đường ống cấp nước chữa cháy ngoài nhà có các trụ nước chữa cháy.

_CHÚ THÍCH: Trên mạng đường ống cho phép sử dụng các trụ nước chữa cháy kiểu nổi hoặc kiểu ngầm._"""
    text = clean_section(text, "muc-5-1-4-7", "### 5.1.4.7  Bán kính phục vụ của trụ nước và bồn bể chữa cháy", body_5_1_4_7)

    # 5.1.5.4: Bãi lấy nước thay bãi đỗ xe 12x12
    body_5_1_5_4 = """5.1.5.4  Các hồ ao để cho xe chữa cháy hút nước phải có lối tiếp cận và có bãi lấy nước với bề mặt bảo đảm tải trọng dành cho xe chữa cháy.

Khi xác định thể tích nước chữa cháy trong các bồn, bể thì cho phép tính cả việc nạp thêm vào bồn, bể trong thời gian chữa cháy nếu nó có hệ thống cấp nước bảo đảm quy định tại 5.1.2.7."""
    text = clean_section(text, "muc-5-1-5-4", "### 5.1.5.4  Lối tiếp cận và bãi lấy nước", body_5_1_5_4)

    # 5.1.5.6: Bổ sung nước cho bể
    body_5_1_5_6 = """5.1.5.6  Lượng nước dự trữ cho chữa cháy trong các bồn, bể phải được tính toán bổ sung trong quá trình chữa cháy nếu các bồn, bể này được cấp nước liên tục từ hệ thống cấp nước bên ngoài bảo đảm lưu lượng và áp suất theo tính toán."""
    text = clean_section(text, "muc-5-1-5-6", "### 5.1.5.6  Bổ sung nước cho bồn bể trong quá trình chữa cháy", body_5_1_5_6)

    # 5.1.5.7: Không yêu cầu họng chờ DN 80 nếu có bơm cố định
    if 'id="muc-5-1-5-7"' in text and "không yêu cầu họng chờ này nếu bồn, bể đã được trang bị máy bơm chữa cháy cố định" not in text:
        text = re.sub(r'(<a id="muc-5-1-5-7"[^>]*></a>.*?- Mỗi bồn, bể phải có ít nhất hai họng chờ.*?)(?=\n-|\n###|\Z)', r'\1 (không yêu cầu họng chờ này nếu bồn, bể đã được trang bị máy bơm chữa cháy cố định);', text, flags=re.DOTALL)
        print("  [OK] Updated Mục 5.1.5.7.")

    # 5.1.5.9: Van khóa tự động hoặc từ xa
    body_5_1_5_9 = """5.1.5.9  Các bồn, bể nước chữa cháy phải được trang bị các thiết bị kiểm tra mức nước tự động và truyền tín hiệu về phòng trực điều khiển chống cháy của nhà."""
    text = clean_section(text, "muc-5-1-5-9", "### 5.1.5.9  Kiểm tra mức nước trong bồn bể chữa cháy", body_5_1_5_9)

    # 5.1.5.10: Hố thu nước không nhỏ hơn 3 m3
    body_5_1_5_10 = """5.1.5.10  Khi không thể hút nước trực tiếp từ các bồn, bể, hồ chứa nước chữa cháy bằng xe chữa cháy hoặc máy bơm di động thì phải thiết kế các hố thu nước với thể tích không nhỏ hơn 3 m3. Thiết kế hố thu nước và đường ống nối từ bồn, bể, hồ chứa nước đến hố thu nước phải bảo đảm lưu lượng nước yêu cầu cho chữa cháy."""
    text = clean_section(text, "muc-5-1-5-10", "### 5.1.5.10  Hố thu nước chữa cháy", body_5_1_5_10)

    # 5.2.1: Cấp nước chữa cháy trong nhà
    body_5_2_1 = """5.2.1  Việc trang bị hệ thống cấp nước chữa cháy trong nhà phải tuân thủ các quy định tại tài liệu chuẩn và các quy định riêng của quy chuẩn này."""
    text = clean_section(text, "muc-5-2-1", "### 5.2.1  Trang bị hệ thống cấp nước chữa cháy trong nhà", body_5_2_1)

    # Bảng 11: Lưu lượng và số họng nước chữa cháy trong nhà
    if 'id="bang-11"' in text:
        body_b11 = """| Nhóm nguy hiểm cháy theo công năng của nhà | Chiều cao PCCC của nhà, m; hoặc số tầng | Khối tích của nhà, m3 | Số lượng họng nước chữa cháy cho mỗi điểm của nhà | Lưu lượng nước tối thiểu của mỗi họng nước, L/s |
| --- | --- | --- | --- | --- |
| F1.1 | - | Đến 5 000 | 1 | 2,5 |
| F1.1 | - | Trên 5 000 | 2 | 2,5 |
| F1.2, F4.3 | Đến 50 | Đến 25 000 | 1 | 2,5 |
| F1.2, F4.3 | Đến 50 | Trên 25 000 | 2 | 2,5 |
| F1.3 | Đến 50 | - | 1 | 2,5 |
| F1.3, F1.2, F4.3 | Trên 50 | - | 2 | 2,5 |
| F2, F3, F4 (trừ F4.3) | Đến 50 | Đến 25 000 | 1 | 2,5 |
| F2, F3, F4 (trừ F4.3) | Đến 50 | Trên 25 000 | 2 | 2,5 |
| F2, F3, F4 (trừ F4.3) | Trên 50 | - | 2 | 2,5 |
| F5 | Bậc I, II, III | Đến 50 000 | 1 | 2,5 |
| F5 | Bậc I, II, III | Trên 50 000 | 2 | 2,5 |
| F5 | Bậc IV, V | Đến 5 000 | 1 | 2,5 |
| F5 | Bậc IV, V | Trên 5 000 | 2 | 2,5 |

CHÚ THÍCH: Đối với các nhà và công trình không thuộc Bảng 11 thì áp dụng theo tài liệu chuẩn."""
        text = clean_section(text, "bang-11", "### <a id=\"bang-11\" name=\"bang-11\"></a>Bảng 11 - Số lượng họng nước và lưu lượng nước chữa cháy trong nhà", body_b11)

    # 5.2.6: Họng khô
    body_5_2_6 = """5.2.6  Cho phép thiết kế hệ thống họng khô để cấp nước chữa cháy trong nhà theo quy định của tài liệu chuẩn áp dụng."""
    text = clean_section(text, "muc-5-2-6", "### 5.2.6  Thiết kế hệ thống họng khô", body_5_2_6)

    # 5.2.11: CHÚ THÍCH 3 vòi dài đến 40 m
    if 'id="muc-5-2-11"' in text and "CHÚ THÍCH 3:" not in text:
        note_3_5211 = "\n\nCHÚ THÍCH 3: Cho phép tăng bán kính phục vụ của các họng nước chữa cháy bằng việc kết nối các vòi chữa cháy với tổng chiều dài đến 40 m. Khi đó các vòi phải treo ở dạng xếp trên giá đỡ và được kết nối sẵn với họng nước và lăng phun."
        text = re.sub(r'(<a id="muc-5-2-11"[^>]*></a>.*?)(?=\n(?:#{1,4}\s*)?<a id="muc-5-2-12"|\n### 5\.2\.12)', r'\1' + note_3_5211 + '\n', text, flags=re.DOTALL)
        print("  [OK] Added CHÚ THÍCH 3 to Mục 5.2.11.")

    # 5.3.1: Chữa cháy tự động theo tài liệu chuẩn
    body_5_3_1 = """5.3.1  Việc thiết kế, lắp đặt hệ thống chữa cháy tự động phải tuân thủ các quy định tại tài liệu chuẩn."""
    text = clean_section(text, "muc-5-3-1", "### 5.3.1  Thiết kế và lắp đặt hệ thống chữa cháy tự động", body_5_3_1)

    # 6.2.2.1: bãi quay xe hoặc phương án chữa cháy từ ngoài nhà
    body_6_2_2_1 = """6.2.2.1  Nhà nhóm F1, F2, F3 và F4 có chiều cao PCCC không quá 15 m không yêu cầu có bãi đỗ xe chữa cháy, tuy nhiên phải có đường cho xe chữa cháy tiếp cận đến điểm bất kỳ trên hình chiếu bằng của nhà không lớn hơn 60 m, hoặc có phương án chữa cháy phù hợp từ ngoài nhà."""
    text = clean_section(text, "muc-6-2-2-1", "### 6.2.2.1  Tiếp cận của đường cho xe chữa cháy", body_6_2_2_1)

    # 6.2.2.3: Bãi đỗ xe chữa cháy và khoảng cách tiếp cận (Verbatim SĐ1)
    body_6_2_2_3 = """6.2.2.3  Bãi đỗ xe chữa cháy phải bố trí tiếp cận đến các lối vào từ trên cao của nhà và đáp ứng các yêu cầu sau:

a) Bãi đỗ xe chữa cháy phải được bố trí tiếp cận đến ít nhất toàn bộ một mặt ngoài của mỗi khối nhà đối với nhà có chiều cao PCCC lớn hơn 50 m hoặc nhà có diện tích sàn lớn hơn 10 000 m2;

b) Đối với nhà có chiều cao PCCC từ trên 28 m đến 50 m (trừ nhà nhóm F1.3) bãi đỗ xe chữa cháy phải tiếp cận đến ít nhất 50 % chu vi của nhà;

CHÚ THÍCH: Nếu các lỗ thông tầng được bảo vệ chống cháy lan thì diện tích sàn cho phép tiếp cận được tính bằng diện tích một sàn lớn nhất trong số các sàn được nối thông tầng cộng với diện tích các lỗ thông tầng trong phạm vi được bảo vệ.

c) Đối với nhà nhóm F1.3 có chiều cao PCCC từ trên 28 m đến 50 m, cho phép chỉ bố trí bãi đỗ xe chữa cháy tiếp cận đến một mặt ngoài của nhà nếu bảo đảm các yêu cầu về bố trí đường cho xe chữa cháy và bãi đỗ xe chữa cháy tiếp cận được các gian phòng có người;

(chỉ yêu cầu có đường cho xe chữa cháy tiếp cận như 6.2.2.1 hoặc có phương án chữa cháy phù hợp khác đối với nhà F5 hạng A, B có tổng diện tích sàn đến 300 m2, nhà F5 hạng C, D, E có diện tích và chiều cao không vượt quá giới hạn cho phép lấy theo nhà có bậc chịu lửa V theo Phụ lục H).

d) Khoảng cách từ mép gần nhất của bãi đỗ xe chữa cháy đến tường ngoài của nhà phải nằm trong khoảng từ 2 m đến 10 m đối với nhà có chiều cao PCCC đến 28 m; và từ 5 m đến 10 m đối với nhà có chiều cao PCCC trên 28 m. Không quy định khoảng cách này khi không có yêu cầu cứu nạn từ trên cao và lực lượng chữa cháy có phương án khác để tiếp cận chữa cháy."""
    text = clean_section(text, "muc-6-2-2-3", "### 6.2.2.3  Yêu cầu bố trí bãi đỗ xe chữa cháy", body_6_2_2_3)

    # 6.3.5: CHÚ THÍCH đường và bãi đỗ xe
    if 'id="muc-6-3-5"' in text and "Cho phép kết hợp đường cho xe chữa cháy và bãi đỗ xe chữa cháy" not in text:
        note_635 = "\n\nCHÚ THÍCH: Cho phép kết hợp đường cho xe chữa cháy và bãi đỗ xe chữa cháy nếu đường giao thông đáp ứng đồng thời các yêu cầu đối với cả đường cho xe chữa cháy và bãi đỗ xe chữa cháy."
        text = re.sub(r'(<a id="muc-6-3-5"[^>]*></a>.*?)(?=\n(?:#{1,4}\s*)?<a id="muc-6-4"|\n### 6\.4)', r'\1' + note_635 + '\n', text, flags=re.DOTALL)
        print("  [OK] Added CHÚ THÍCH to Mục 6.3.5.")

    # 6.4: Thiết kế bãi quay xe
    body_6_4 = """6.4 Thiết kế bãi quay xe phải phù hợp với phương tiện chữa cháy ở địa phương."""
    text = clean_section(text, "muc-6-4", "### 6.4  Thiết kế bãi quay xe", body_6_4)

    # 6.1.2 (6.12): 75 mm gap and dry riser
    body_6_12 = """6.1.2 Giữa các bản thang và giữa các lan can tay vịn của bản thang phải có khe hở với chiều rộng thông thủy chiếu trên mặt bằng không nhỏ hơn 75 mm. Trường hợp không thể bảo đảm yêu cầu này thì tại mỗi tầng cần bố trí ít nhất một họng khô để cấp nước chữa cháy cho tầng đó. Không yêu cầu khe hở vế thang đối với cầu thang loại 3."""
    text = clean_section(text, "muc-6-1-2", "### 6.1.2  Khe hở giữa các bản thang và lan can", body_6_12)

    # 6.13: Bán kính phục vụ 60 m (Verbatim SĐ1)
    body_6_13 = """6.13  Mỗi khoang cháy của các nhà có chiều cao PCCC lớn hơn 28 m (lớn hơn 50 m đối với nhà nhóm F1.3), hoặc nhà có chiều sâu của sàn tầng hầm dưới cùng (tính đến cao độ của lối ra thoát nạn ra ngoài) lớn hơn 9 m phải có tối thiểu một thang máy chữa cháy.

_CHÚ THÍCH: Yêu cầu kỹ thuật khác như cáp điện, hệ thống điều khiển, truyền tín hiệu, liên lạc, thiết bị phục vụ bảo vệ chống cháy và những hệ thống tương tự phải bảo đảm theo các tiêu chuẩn kỹ thuật riêng được chọn lựa cho thang máy chữa cháy_

Việc bố trí và lắp đặt các thang máy chữa cháy phải bảo đảm những quy định cơ bản sau:

- Không được sử dụng các thang máy chủ yếu để vận chuyển hàng hóa để làm thang máy chữa cháy;

- Ở điều kiện bình thường, thang máy chữa cháy vẫn được sử dụng để chở người. Thang máy chữa cháy có thể được bố trí với một sảnh thang máy riêng hoặc trong một sảnh chung với các thang máy chở người và hợp lại với nhau bằng một hệ thống điều khiển tự động theo nhóm;

- Có số lượng được tính toán đủ để khoảng cách từ vị trí cửa các thang máy đó đến một điểm bất kỳ trên mặt bằng tầng mà nó phục vụ (bán kính phục vụ) không vượt quá 60 m;

- Nếu chỉ có một thang máy chữa cháy thì thang máy đó ít nhất phải đến được tất cả các tầng kề cận với tầng đang cháy của nhà;

- Nếu có nhiều thang máy chữa cháy được bố trí chung trong một giếng thang thì các thang máy có thể phục vụ cho các khu vực khác nhau của nhà với điều kiện phải thể hiện rõ vùng được phục vụ trên mỗi thang máy đó;

- Trong mọi trường hợp, hình thức phục vụ của các thang máy chữa cháy phải giống nhau và thông dụng, ví dụ thang máy chỉ phục vụ các tầng lẻ hoặc các tầng chẵn hoặc tất cả các tầng;

- Nếu có các tầng lánh nạn thì mỗi tầng đó phải được phục vụ bởi ít nhất một thang máy chữa cháy;

- Ở chế độ hoạt động bình thường, cửa các thang máy chữa cháy không được mở vào những tầng lánh nạn đó còn cửa giếng thang máy tại những tầng lánh nạn đó phải thường xuyên được khóa và chỉ được tự động mở khóa khi chuyển sang chế độ phục vụ lực lượng chữa cháy.

Trong trường hợp có cháy, các thang máy chữa cháy phải bảo đảm để người lính chữa cháy:

- Là người duy nhất được quyền kiểm soát và vận hành để cùng với trang thiết bị của mình tiếp cận đến đám cháy một cách dễ dàng, quen thuộc, an toàn và nhanh chóng;

- Được bảo vệ an toàn khi sử dụng trước tác động của lửa và khói bằng các giải pháp thích hợp, đặc biệt là khi ra khỏi các thang máy đó;

- Có lối đi thông thoáng và an toàn để tiếp cận đến các thang máy đó cũng như đến các sàn được những thang máy đó phục vụ;

- Không phải di chuyển quá hai tầng để tiếp cận đến tầng có thể bị cháy bất kỳ của nhà khi có từ 2 thang máy chữa cháy trở lên;

- Được bảo vệ trong các giếng thang máy riêng (không chung với các loại thang máy khác) và trong mỗi giếng thang máy như vậy chỉ được bố trí không quá 3 thang máy chữa cháy. Kết cấu bao che giếng thang máy phải có giới hạn chịu lửa không nhỏ hơn REI 120.

Sảnh thang máy chữa cháy là một khoang đệm bảo đảm tất cả các quy định sau:

- Có diện tích không nhỏ hơn 4 m2;

- Khi kết hợp với các sảnh của buồng thang bộ không nhiễm khói thì diện tích không nhỏ hơn 6 m2;

- Được bao che bằng các vách ngăn cháy loại 1;

- Có lắp đặt họng chờ cấp nước DN 65 dành cho lực lượng chữa cháy chuyên nghiệp;

- Việc bố trí thang máy chữa cháy phải dự tính được đường di chuyển của đội chữa cháy chuyên nghiệp và bảo đảm đội chữa cháy tiếp cận được tất cả các gian phòng trên tất cả các tầng của nhà;

- Sức chở của thang máy chữa cháy không được nhỏ hơn 630 kg đối với nhà chung cư nhóm F1.3 và không nhỏ hơn 1 000 kg đối với nhà sản xuất và nhà công cộng khác;

- Tốc độ di chuyển của thang máy chữa cháy không được nhỏ hơn H/60 (m/s), trong đó H là chiều cao nâng (m);

- Kết cấu bao che của cabin thang máy chữa cháy phải được làm từ vật liệu không cháy hoặc cháy yếu."""
    text = clean_section(text, "muc-6-13", "### 6.13  Bố trí và lắp đặt thang máy chữa cháy", body_6_13)

    # 6.14: Tiếp cận qua mái (Verbatim SĐ1)
    body_6_14 = """6.14  Trong các nhà có độ dốc mái đến 12 %, chiều cao đến diềm mái hoặc mép trên của tường ngoài (tường chắn) lớn hơn 10 m, cũng như trong các nhà có độ dốc mái lớn hơn 12 % và chiều cao đến diềm mái lớn hơn 7 m, nếu được thiết kế để lực lượng chữa cháy tiếp cận qua mái thì phải có lan can, tay vịn trên mái phù hợp tiêu chuẩn hiện hành. Các lan can, tay vịn loại này cũng phải được bố trí cho các mái phẳng, ban công, lôgia, hành lang bên ngoài, cầu thang bên ngoài loại hở, bản thang bộ và chiếu thang bộ mà không phụ thuộc vào chiều cao PCCC của nhà."""
    text = clean_section(text, "muc-6-14", "### 6.14  Lan can tay vịn trên mái", body_6_14)

    # 6.1.7.1: Bãi bỏ "theo A.4" (Verbatim SĐ1)
    body_6_1_7_1 = """6.1.7.1  Nhà ở và công trình công cộng cao trên 10 tầng; nhà có từ 2 đến 3 tầng hầm; công trình công cộng tập trung đông người (nhà hát, rạp chiếu phim, vũ trường, các quán karaoke mà phải bố trí từ 2 lối ra thoát nạn trở lên, và các nhà có mục đích sử dụng tương tự, với số người trên mỗi tầng, tính theo Bảng G.9 (Phụ lục G), vượt quá 50 người); gara (chỗ để ô-tô, xe máy, xe đạp), nhà sản xuất, kho có tổng diện tích sàn trên 18 000 m2 phải có phòng trực điều khiển chống cháy và có nhân viên có chuyên môn thường xuyên trực tại phòng điều khiển."""
    text = clean_section(text, "muc-6-1-7-1", "### 6.1.7.1  Yêu cầu đối với phòng trực điều khiển chống cháy", body_6_1_7_1)

    # 6.17.2: Lối ra trực tiếp thông với hành lang chính (Verbatim SĐ1)
    body_6_17_2 = """6.17.2  Phòng trực điều khiển chống cháy phải:

- Có diện tích đủ để bố trí các thiết bị theo yêu cầu phòng chống cháy của nhà nhưng không nhỏ hơn 6 m2;

- Có ít nhất một lối ra trực tiếp thông với hành lang chính để thoát nạn hoặc lối ra trực tiếp ra ngoài nhà, hoặc thông trực tiếp với cầu thang thoát nạn;

- Được ngăn cách với các phần khác của nhà bằng các bộ phận ngăn cháy loại 1;

- Có lắp đặt các thiết bị thông tin và đầu mối của hệ thống báo cháy liên hệ với tất cả các khu vực của nhà;

- Có bảng theo dõi, điều khiển các thiết bị chữa cháy, thiết bị khống chế khói và có sơ đồ mặt bằng bố trí các thiết bị phòng cháy chữa cháy của nhà."""
    text = clean_section(text, "muc-6-17-2", "### 6.17.2  Yêu cầu đối với phòng trực điều khiển chống cháy", body_6_17_2)

    # 7.4 Repealed Notice
    body_7_4 = """*(Nội dung điểm 7.4 đã được bãi bỏ theo quy định tại Thông tư số 09/2023/TT-BXD ngày 10/10/2023 của Bộ trưởng Bộ Xây dựng)*"""
    text = clean_section(text, "muc-7-4", "### 7.4  Phối hợp ban hành thông số kỹ thuật địa phương", body_7_4, is_repeal=True)

    return text


def consolidate_annexes():
    """Applies SĐ1 amendments to modular annexes in annexes/ directory."""
    # Annex A
    annex_a_file = ANNEXES_DIR / "phu_luc_a_quy_dinh_bo_sung_nhom_nha_cu_the.md"
    bak_a_file = ANNEXES_DIR / "phu_luc_a_quy_dinh_bo_sung_nhom_nha_cu_the.md.bak"
    if bak_a_file.exists():
        text_a = bak_a_file.read_text(encoding="utf-8")
        
        # A.1.2.1
        body_a_1_2_1 = """A.1.2.1 Khi xác định số lượng tầng của nhà thì mỗi sàn công tác, sàn đỡ thiết bị và sàn lửng nằm ở cao độ bất kỳ có diện tích lớn hơn 40 % diện tích một tầng của nhà đó, phải được tính như một tầng.

Diện tích một tầng của nhà trong phạm vi một khoang cháy được xác định theo chu vi bên trong của tường bao của tầng, không tính diện tích buồng thang bộ. Nếu trong diện tích đó có các sàn công tác, sàn đỡ thiết bị và sàn lửng thì đối với nhà 1 tầng phải cộng thêm diện tích của tất cả các sàn này; còn đối với nhà nhiều tầng (hoặc phần nhà nhiều tầng) thì diện tích khoang cháy của mỗi tầng phải cộng thêm diện tích các sàn công tác, sàn đỡ thiết bị và sàn lửng nằm trong tầng đó. Diện tích của thềm (cầu) xếp dỡ phía ngoài dùng cho phương tiện vận tải đường bộ và đường sắt không được tính vào diện tích của tầng nhà trong phạm vi khoang cháy. Diện tích các gian phòng có chiều cao thông từ 2 tầng trở lên, trong phạm vi một nhà nhiều tầng (gian phòng thông 2 tầng hoặc nhiều tầng) mà lỗ thông tầng không được bảo vệ ngăn cháy thì được tính vào diện tích tổng cộng của nhà trong phạm vi một tầng.

Diện tích xây dựng được xác định theo chu vi ngoài của nhà ở cao độ chân tường, bao gồm cả các phần nhô ra, đường đi qua dưới nhà, các phần nhà không có kết cấu ngăn che bên ngoài."""
        text_a = clean_section(text_a, "muc-A-1-2-1", "### A.1.2.1  Xác định số tầng và diện tích khoang cháy", body_a_1_2_1)

        # A.1.3.2: bãi bỏ đoạn 2
        p_a132 = r'(<a id="muc-A-1-3-2"[^>]*></a>.*?)(Cho phép không bố trí cửa thoát nạn từ các tầng.*?)(?=\n\n<a id="muc-A-1-3-3"|\Z)'
        if re.search(p_a132, text_a, flags=re.DOTALL):
            text_a = re.sub(p_a132, r'\1*(Đoạn văn này đã được bãi bỏ theo Thông tư 09/2023/TT-BXD)*\n', text_a, flags=re.DOTALL)

        # A.1.3.6
        body_a_1_3_6 = """A.1.3.6  Không cho phép bố trí các gian phòng chứa các chất và vật liệu nguy hiểm cháy nổ (hạng A, B) trong các tầng hầm và bán hầm."""
        text_a = clean_section(text_a, "muc-A-1-3-6", "### A.1.3.6  Bố trí gian phòng chứa chất nguy hiểm cháy nổ", body_a_1_3_6)

        # A.1.3.10 (Dual anchor: canonical A.1.3.10 and legacy A.1.3.1.0)
        body_a_1_3_10 = """A.1.3.10 Kho cất giữ hàng có hạng nguy hiểm cháy và cháy nổ C trên giá đỡ cao tầng phải được bố trí trong nhà 1 tầng có bậc chịu lửa I đến IV và cấp nguy hiểm cháy kết cấu của nhà S0. Trường hợp bố trí trong nhà nhiều tầng thì các giá đỡ cao tầng phải được bảo vệ bởi hệ thống chữa cháy tự động theo tài liệu chuẩn áp dụng.

Các giá đỡ hàng phải có sàn đỡ nằm ngang, đặc và làm từ vật liệu không cháy đặt cách nhau không quá 4 m theo chiều cao."""
        text_a = clean_section(text_a, "muc-A-1-3-1-0", "### A.1.3.10  Kho cất giữ hàng có hạng nguy hiểm cháy và cháy nổ C", body_a_1_3_10, dual_anchor="muc-A-1-3-10")

        # A.1.3.12 (Repealed)
        body_a_1_3_12 = """*(Nội dung điểm A.1.3.12 đã được bãi bỏ theo quy định tại Thông tư 09/2023/TT-BXD)*"""
        text_a = clean_section(text_a, "muc-A-1-3-1-2", "### A.1.3.12  Lỗ cửa sổ của nhà kho", body_a_1_3_12, is_repeal=True, dual_anchor="muc-A-1-3-12")

        # A.2.3: Bổ sung "(hoặc phân khoang cháy)"
        text_a = re.sub(r'(<a id="muc-A-2-3"[^>]*></a>.*?khoang cháy)(?!\s*\(hoặc phân khoang cháy\))', r'\1 (hoặc phân khoang cháy)', text_a)

        # A.2.4: Bổ sung vào cuối A.2.4 (Verbatim SĐ1)
        pat_a24 = r'((?:###\s*)?<a\s+id=[\"\x27]muc-[aA]-2-4[\"\x27][^>]*></a>.*?)(?=\n\n(?:#{1,4}\s*)?<a\s+id=[\"\x27]muc-[aA]-2-5[\"\x27]|\n\n###\s+A\.2\.5|\Z)'
        add_a24 = "\n\nCho phép bố trí các gian phòng tập trung đông người ở chiều cao PCCC cao hơn quy định trên khi có tính toán thoát nạn cho người theo tài liệu chuẩn (ví dụ [5]) bảo đảm nguyên tắc người thoát nạn an toàn ra ngoài nhà trước khi bị các yếu tố nguy hiểm cháy tác động."
        if "bảo đảm nguyên tắc người thoát nạn an toàn ra ngoài nhà trước khi bị các yếu tố nguy hiểm cháy tác động" not in text_a:
            text_a = re.sub(pat_a24, r'\1' + add_a24, text_a, count=1, flags=re.DOTALL)

        # A.2.11 (Dual anchor: canonical A.2.11 and legacy A.2.1.1)
        body_a_2_11 = """A.2.11 Các sảnh thang máy phải được ngăn cách với các hành lang và các phòng bên cạnh bằng các vách ngăn cháy hoặc giải pháp ngăn cháy khác có giới hạn chịu lửa theo quy định tại A.2.24, nếu các thang máy này có phục vụ tầng hầm, hoặc cửa giếng thang máy không phải là cửa ngăn cháy.

Vật liệu của các bộ phận cabin thang máy phải được cấu tạo như thang máy chữa cháy."""
        text_a = clean_section(text_a, "muc-A-2-1-1", "### A.2.11  Các sảnh thang máy", body_a_2_11, dual_anchor="muc-A-2-11")

        # A.2.12 (Dual anchor: canonical A.2.12 and legacy A.2.1.2)
        body_a_2_12 = """A.2.12 Phải bố trí thang máy chữa cháy trong các giếng thang riêng biệt, có sảnh thang máy độc lập. Trường hợp bố trí chung giếng thang và sảnh thang thì việc bảo vệ các giếng thang, sảnh thang chung này phải tuân thủ các yêu cầu tại A.2.24 như đối với thang máy chữa cháy. Lối ra từ thang máy này đi ra ngoài nhà không được bố trí đi qua sảnh chung (trừ khi sảnh chung này được ngăn cách với các khu vực xung quanh bằng các bộ phận ngăn cháy loại 1).

Số lượng thang máy chữa cháy cho mỗi khoang cháy phải được tính toán đủ để khoảng cách từ vị trí các thang máy đó đến một điểm bất kỳ trên mặt bằng tầng mà nó phục vụ không vượt quá 45 m.

Vật liệu ốp lát hoàn thiện bề mặt các cấu kiện bao che cabin áp dụng như cho các gian phòng theo quy định tại A.2.2.5."""
        text_a = clean_section(text_a, "muc-A-2-1-2", "### A.2.12  Thang máy chữa cháy trong các giếng thang riêng biệt", body_a_2_12, dual_anchor="muc-A-2-12")

        # A.2.14 (Dual anchor: canonical A.2.14 and legacy A.2.1.4)
        body_a_2_14 = """A.2.14 Các hành lang phải được phân chia thành các khoang ngăn cách nhau bằng vách ngăn cháy loại 1 và cửa ngăn cháy loại 2 có cơ cấu tự đóng, hoặc bằng các vách ngăn khói, màn ngăn khói từ vật liệu không cháy có mép dưới cách sàn hành lang tối đa 2,5 m. Chiều dài mỗi khoang hành lang phải bảo đảm như sau:

- Đối với khối căn hộ: không quá 30 m;

- Đối với khối nhà không phải là căn hộ: không quá 60 m."""
        text_a = clean_section(text_a, "muc-A-2-1-4", "### A.2.14  Phân chia hành lang thành các khoang", body_a_2_14, dual_anchor="muc-A-2-14")

        # A.2.20
        body_a_2_20 = """A.2.20 Nhà có chiều cao PCCC trên 100 m (trên 120 m nếu được trang bị báo cháy tự động và chữa cháy tự động) phải bố trí các khu vực lánh nạn tạm thời theo A.3.2."""
        text_a = clean_section(text_a, "muc-A-2-20", "### A.2.20  Khu vực lánh nạn tạm thời cho nhà cao trên 100 m", body_a_2_20)

        # A.2.25.5: Bổ sung điểm A.2.25.5
        if 'id="muc-A-2-25-5"' not in text_a:
            item_a_2_25_5 = """<a id="muc-A-2-25-5"></a><a id="muc-A-2-2-5-5"></a>
### A.2.25.5  Lối vào từ trên cao

> *[Sửa đổi bởi Thông tư 09/2023/TT-BXD (Sửa đổi 1:2023), hiệu lực 01/12/2023]*

Cho phép không bố trí các lối vào từ trên cao đối với các nhà thuộc nhóm F1.3 nếu các căn hộ đều có các phòng lánh nạn hoặc ban công, lô gia đáp ứng yêu cầu của quy chuẩn.
"""
            text_a = re.sub(r'(<a id="muc-A-2-2-5-4"[^>]*></a>.*?)(?=\n(?:#{1,4}\s*)?<a id="muc-A-2-2-6"|\n### A\.2\.2\.6|\n<a id="muc-A-3")', r'\1\n' + item_a_2_25_5 + '\n', text_a, flags=re.DOTALL)

        # A.3.1.8
        body_a_3_1_8 = """A.3.1.8  Chiều rộng thông thủy bản thang và chiếu thang của các buồng thang bộ loại N1, N3 tại phần ở của nhà phải không nhỏ hơn 1,05 m; buồng thang bộ loại N2 không nhỏ hơn 1,05 m với khoảng cách hở thông thủy giữa các bản thang không nhỏ hơn 75 mm."""
        text_a = clean_section(text_a, "muc-A-3-1-8", "### A.3.1.8  Chiều rộng thông thủy bản thang và chiếu thang buồng thang bộ", body_a_3_1_8)

        # A.3.1.13 (Dual anchor: canonical A.3.1.13 and legacy A.3.1.1.3)
        body_a_3_1_13 = """A.3.1.13  Trong các tầng hầm, các lối ra từ thang máy phải đi qua các khoang đệm ngăn cháy loại 1 có áp suất không khí dương khi cháy. Cửa đi của khoang đệm này phải là cửa ngăn cháy có cơ cấu tự đóng."""
        text_a = clean_section(text_a, "muc-A-3-1-1-3", "### A.3.1.13  Lối ra từ thang máy trong các tầng hầm", body_a_3_1_13, dual_anchor="muc-A-3-1-13")

        # A.3.1.16: Bãi bỏ đoạn e) và Dual Anchor muc-A-3-1-16 / muc-A-3-1-1-6
        body_a_3_1_16 = """A.3.1.16  Việc bảo vệ chống khói cho nhà, hệ thống báo cháy và chữa cháy tự động thực hiện theo các quy định bổ sung sau đây:

a) Tất cả các phòng không phải căn hộ (gara, phòng phụ trợ, phòng kỹ thuật, không gian công cộng, khoang chứa rác và các phòng có công năng tương tự) và ống đổ rác phải có đầu phun sprinkler (trừ các gian phòng kỹ thuật điện, điện tử có yêu cầu bố trí hệ thống hoặc thiết bị dập lửa thể khí);

b) Bên trên các cửa vào căn hộ phải lắp các sprinkler nối với đường ống cấp nước chữa cháy thông qua rơ le dòng;

c) Hệ thống báo cháy tự động phải báo rõ địa chỉ của từng căn hộ. Trong các phòng của căn hộ và các hành lang tầng, kể cả sảnh thang máy phải lắp đặt đầu báo khói. Trong mỗi căn hộ phải trang bị hệ thống loa truyền thanh để hướng dẫn thoát nạn, bảo đảm mọi người trong căn hộ có thể nghe rõ thông báo, hướng dẫn khí có sự cố;

d) Cần trang bị hệ thống báo cháy, thiết bị, phương tiện chữa cháy tự động trong các kênh, giếng kỹ thuật điện, thông tin liên lạc và giếng kỹ thuật khác có nguy hiểm cháy;

*(Đoạn e đã được bãi bỏ theo Thông tư 09/2023/TT-BXD)*"""
        text_a = clean_section(text_a, "muc-A-3-1-1-6", "### A.3.1.16  Việc bảo vệ chống khói cho nhà, hệ thống báo cháy và chữa cháy tự động", body_a_3_1_16, dual_anchor="muc-A-3-1-16")

        # A.3.2.1
        body_a_3_2_1 = """A.3.2.1  Các gian lánh nạn tạm thời phải được bảo vệ bằng các bộ phận ngăn cháy có giới hạn chịu lửa không thấp hơn quy định tại Bảng 4 tương ứng với bậc chịu lửa của nhà, và các cửa ngăn cháy loại 1 có cơ cấu tự đóng:

a) Gian lánh nạn phải được bố trí ở các tầng lánh nạn, với khoảng cách không quá 20 tầng giữa các tầng lánh nạn liền kề;"""
        text_a = clean_section(text_a, "muc-A-3-2-1", "### A.3.2.1  Bảo vệ các gian lánh nạn tạm thời", body_a_3_2_1)

        # A.3.2.2: Bổ sung điểm A.3.2.2
        if 'id="muc-A-3-2-2"' not in text_a:
            item_a_3_2_2 = """<a id="muc-A-3-2-2"></a>
### A.3.2.2  Khu vực lánh nạn trên mái

> *[Sửa đổi bởi Thông tư 09/2023/TT-BXD (Sửa đổi 1:2023), hiệu lực 01/12/2023]*

Cho phép bố trí khu vực lánh nạn tạm thời trên mái nhà nếu bảo đảm các yêu cầu sau: mái phải là mái bằng, kết cấu chịu lực của sàn mái phải có giới hạn chịu lửa tối thiểu REI 120, và khu vực lánh nạn trên mái phải được bao che bằng lan can an toàn cao tối thiểu 1,4 m.
"""
            text_a = re.sub(r'(<a id="muc-A-3-2-1"[^>]*></a>.*?)(?=\n(?:#{1,4}\s*)?<a id="muc-A-4"|\n### A\.4|\Z)', r'\1\n' + item_a_3_2_2 + '\n', text_a, flags=re.DOTALL)

        # A.4 (Repealed entire karaoke / discotheque section)
        body_a_4 = """*(Toàn bộ nội dung mục A.4 về Nhà kinh doanh dịch vụ karaoke, vũ trường đã được bãi bỏ theo quy định tại Sửa đổi 1:2023 QCVN 06:2022/BXD ban hành kèm theo Thông tư 09/2023/TT-BXD ngày 10/10/2023)*"""
        text_a = clean_section(text_a, "muc-A-4", "### A.4  Nhà kinh doanh dịch vụ karaoke, vũ trường (thuộc nhóm F2.1)", body_a_4, is_repeal=True)

        annex_a_file.write_text(text_a, encoding="utf-8")
        print("  [OK] Consolidated Phụ lục A.")

    # Annex C
    annex_c_file = ANNEXES_DIR / "phu_luc_c_hang_nguy_hiem_chay_va_chay_no.md"
    bak_c_file = ANNEXES_DIR / "phu_luc_c_hang_nguy_hiem_chay_va_chay_no.md.bak"
    if bak_c_file.exists():
        text_c = bak_c_file.read_text(encoding="utf-8")
        body_c_3_1 = """C.3.1 Phương pháp xác định các dấu hiệu để xếp nhà, công trình và gian phòng có công năng sản xuất và kho vào các hạng theo tính nguy hiểm cháy và cháy nổ được quy định trong các tiêu chuẩn, có thể áp dụng [8] và các tài liệu hướng dẫn liên quan để thực hiện.

Các thông số của chất cháy trong nhà và gian phòng có thể tham khảo các tài liệu chuẩn [3, 4, 5, 6, 8, 9] hoặc các tài liệu chuẩn khác."""
        text_c = clean_section(text_c, "muc-C-3-1", "### C.3.1  Phương pháp xác định các dấu hiệu để xếp hạng", body_c_3_1)

        text_c = re.sub(r'Khi không có các tính toán cụ thể để xếp hạng theo dấu hiệu.*?:', 'Khi không có các tính toán cụ thể để phân hạng nguy hiểm cháy và cháy nổ theo tiêu chuẩn, có thể tham khảo hạng nguy hiểm cháy và cháy nổ của một số nhà và gian phòng thuộc các phân xưởng, nhà kho, bộ phận sản xuất như sau:', text_c)

        if 'id="muc-c-3-2-2"' in text_c or 'id="muc-C-3-2-2"' in text_c:
            text_c = re.sub(r'(chất rắn)(?!\s*có tạo ra các bụi cháy được)', r'\1 có tạo ra các bụi cháy được và có khả năng tạo thành các hỗn hợp nguy hiểm nổ (theo Bảng C.1) khi có sự cố', text_c)

        annex_c_file.write_text(text_c, encoding="utf-8")
        print("  [OK] Consolidated Phụ lục C.")

    # Annex D
    annex_d_file = ANNEXES_DIR / "phu_luc_d_bao_ve_chong_khoi.md"
    bak_d_file = ANNEXES_DIR / "phu_luc_d_bao_ve_chong_khoi.md.bak"
    if bak_d_file.exists():
        text_d = bak_d_file.read_text(encoding="utf-8")
        
        # D.1.1
        body_d_1_1 = """D.1.1  Việc bảo vệ chống khói cho nhà và công trình nhằm ngăn chặn và (hoặc) hạn chế sự lan truyền khói và các sản phẩm cháy (sau đây gọi chung là khói) trong nhà, với mục đích:

- Tạo điều kiện an toàn cho người thoát nạn và bảo vệ tài sản khi xảy ra cháy;

- Tạo các điều kiện cần thiết cho lực lượng chữa cháy cứu người, phát hiện và khoanh vùng đám cháy trong nhà.

Nếu không có các quy định cụ thể về thời gian tiếp cận công trình của lực lượng chữa cháy và thời gian mà lực lượng chữa cháy sẽ hoạt động trong công trình để chữa cháy, và không có yêu cầu về bảo vệ tài sản khi xảy ra cháy, thì việc thiết kế bảo vệ chống khói của nhà cần bảo đảm mục tiêu tối thiểu là an toàn cho người thoát nạn ra ngoài."""
        text_d = clean_section(text_d, "muc-d-1-1", "### D.1.1  Mục đích bảo vệ chống khói", body_d_1_1)

        # D.1.2: thêm (hoặc lấy theo giá trị quy định trong tài liệu chuẩn áp dụng)
        text_d = re.sub(r'không thấp hơn 2 m(?!\s*\(hoặc lấy theo giá trị quy định)', 'không thấp hơn 2 m (hoặc lấy theo giá trị quy định trong tài liệu chuẩn áp dụng)', text_d)

        # D.1.3
        body_d_1_3 = """D.1.3 Các thiết bị của hệ thống hút xả khói và cấp không khí chống khói, không phụ thuộc vào cơ chế hoạt động (tự nhiên hoặc cưỡng bức), phải luôn bảo đảm hoạt động đúng thiết kế khi có cháy.

Các thiết bị của hệ thống bảo vệ chống khói (bao gồm cả các đường ống) phải được lắp đặt đúng quy định của nhà sản xuất, được kiểm tra định kỳ và bảo trì, bảo dưỡng thích hợp. Các trang bị phụ trợ để lắp đặt, treo các thiết bị phải bảo đảm duy trì khả năng hoạt động của thiết bị theo quy định của nhà sản xuất trong suốt thời gian khai thác sử dụng."""
        text_d = clean_section(text_d, "muc-d-1-3", "### D.1.3  Yêu cầu đối với thiết bị hệ thống bảo vệ chống khói", body_d_1_3)

        # D.1.5: thêm "hoạt động" trước "độc lập"
        text_d = re.sub(r'Hệ thống thông gió thoát khói phải độc lập', 'Hệ thống thông gió thoát khói phải hoạt động độc lập', text_d)

        # D.1.7
        body_d_1_7 = """D.1.7 Cho phép thay đổi các yêu cầu trong Phụ lục D này trên cơ sở có thiết kế bảo vệ chống khói phù hợp với tiêu chuẩn được phép áp dụng và thỏa mãn yêu cầu tại D.1.1."""
        text_d = clean_section(text_d, "muc-D-1-7", "### D.1.7  Thay đổi yêu cầu trong Phụ lục D", body_d_1_7)

        # D.1.8: TCVN 8664 (ISO 14644)
        text_d = re.sub(r'ISO 14644', 'TCVN 8664 (ISO 14644)', text_d)

        # D.2: Thoát khói & các chú thích
        body_d_2 = """D.2  Việc thoát khói khi có cháy phải được thực hiện từ các khu vực sau:

a) Từ các hành lang và sảnh của nhà ở, công cộng, hành chính - dịch vụ và nhà phụ trợ có chiều cao PCCC lớn hơn 28 m;

b) Từ các hành lang (thông với các buồng thang bộ thoát nạn) của các tầng hầm và tầng nửa hầm không có thông gió tự nhiên khi có cháy của nhà ở, công cộng, hành chính - dịch vụ, sản xuất và phụ trợ;

c) Từ các hành lang có chiều dài lớn hơn 15 m không có thông gió tự nhiên khi có cháy của nhà sản xuất, nhà kho và nhà công cộng từ 2 tầng trở lên thuộc bậc chịu lửa I đến IV;

CHÚ THÍCH: Không yêu cầu thiết kế thoát khói cho các hành lang có chiều dài lớn hơn 15 m mà không có thông gió tự nhiên khi có cháy trong các tầng của nhà thuộc nhóm F4 cao từ 6 tầng trở xuống, khi các tầng này được trang bị báo cháy tự động với đầu báo cháy khói, hoặc chữa cháy tự động.

d) Từ các sảnh chung và hành lang thông tầng không có thông gió tự nhiên khi có cháy;

e) Từ các gian phòng sản xuất hoặc kho có người làm việc thường xuyên thuộc hạng nguy hiểm cháy A, B, C;

f) Từ các gian phòng có người làm việc thường xuyên thuộc nhóm F1, F2, F3, F4 không có thông gió tự nhiên khi có cháy;

g) Từ các gian phòng lưu trữ hàng hóa với diện tích lớn hơn 50 m2 có người làm việc thường xuyên.

CHÚ THÍCH 4: Để thông gió tự nhiên khi có cháy cho các gian phòng hoặc hành lang, cũng có thể bố trí (phân bố tương đối đều) các ô cửa mở trên kết cấu bao che ngoài của gian phòng, hành lang ở độ cao không nhỏ hơn 2,2 m từ mặt sàn đến mép dưới của ô cửa và với tổng diện tích hữu hiệu không nhỏ hơn 2,5 % diện tích sàn của gian phòng, hành lang."""
        text_d = clean_section(text_d, "muc-D-2", "### D.2  Khu vực phải thực hiện thoát khói khi có cháy", body_d_2)

        # D.8
        body_d_8 = """D.8 Để thoát khói trực tiếp cho các gian phòng và hành lang của nhà một tầng có thể áp dụng hệ thống hút xả khói theo cơ chế tự nhiên (giải pháp thoát khói tự nhiên), hoặc theo cơ chế cưỡng bức. Trong các nhà nhiều tầng cần sử dụng hệ thống hút xả khói theo cơ chế cưỡng bức, hoặc có thể sử dụng giải pháp thoát khói tự nhiên nếu tính toán thoát khói cho phép, nhưng phải thỏa mãn yêu cầu tại D.1.1. Cho phép sử dụng giải pháp thoát khói tự nhiên đối với tầng trên cùng của nhà nhiều tầng, thông qua van khói, cửa nắp hút khói, hoặc các cửa trời mở, cửa chớp mở và không đón gió vào."""
        text_d = clean_section(text_d, "muc-D-8", "### D.8  Cơ chế hút xả khói và thoát khói tự nhiên", body_d_8)

        # D.9: Bổ sung CHÚ THÍCH 3 và CHÚ THÍCH 4
        if ('id="muc-d-9"' in text_d or 'id="muc-D-9"' in text_d) and "CHÚ THÍCH 3: Không yêu cầu chỉ tiêu I" not in text_d:
            notes_d9 = """\n\nCHÚ THÍCH 3: Không yêu cầu chỉ tiêu I đối với các đường ống và kênh dẫn khói và ống cấp không khí vào trong phạm vi một khoang cháy nếu thỏa mãn đồng thời các điều kiện sau: 1) việc dẫn khói và không khí trong các ống này không gây cháy các hệ thống kỹ thuật khác hoặc gây cháy tại các khu vực mà đường ống và kênh dẫn đi qua; 2) không làm tăng nhiệt độ không khí ở khu vực trên đường thoát nạn quá 65 °C.

Chú thích này được áp dụng cho tất cả các quy định khác của quy chuẩn này liên quan đến yêu cầu về giới hạn chịu lửa của đường ống, kênh dẫn khác (nếu có).

CHÚ THÍCH 4: Không yêu cầu giới hạn chịu lửa của đường ống, kênh dẫn khói và ống cấp không khí vào nếu thỏa mãn đồng thời các điều kiện sau: 1) ống được làm bằng thép mạ kẽm có chiều dày tối thiểu 1,2 mm; 2) toàn bộ chiều dài ống được bảo vệ bằng hệ thống sprinkler được thiết kế theo tài liệu chuẩn được áp dụng và các đầu phun được bố trí bên trên và bên dưới ống (không phụ thuộc vào kích thước ống); 3) ống và kết cấu treo, đỡ được thiết kế và thi công phù hợp với quy cách của đường ống quy định trong tiêu chuẩn áp dụng.

Chú thích này được áp dụng cho tất cả các quy định khác của quy chuẩn này liên quan đến yêu cầu về giới hạn chịu lửa của đường ống, kênh dẫn khác (nếu có)."""
            text_d = re.sub(r'((?:###\s*)?<a\s+id=[\"\x27]muc-[dD]-9[\"\x27][^>]*></a>.*?)(?=\n(?:#{1,4}\s*)?<a\s+id=[\"\x27]muc-[dD]-10[\"\x27]|\n###\s+D\.10|\Z)', r'\1' + notes_d9 + '\n', text_d, flags=re.DOTALL)
            print("  [OK] Added CHÚ THÍCH 3 and 4 to Mục D.9.")
            print("  [OK] Added CHÚ THÍCH 3 and 4 to Mục D.9.")

        # D.14.5
        body_d_14_5 = """D.14.5 Để bù lại khối tích khói đã bị hút ra khỏi khu vực được bảo vệ bởi hệ thống hút xả khói, phải thiết kế cấp không khí vào theo cơ chế tự nhiên hoặc cưỡng bức:

a) Cấp không khí theo cơ chế tự nhiên: sử dụng các ô cửa, cửa sổ, hoặc khe hở khác có thể thông với không khí bên ngoài (mở khi có cháy). Các ô cửa, cửa sổ, khe hở phải được bố trí ở phần dưới của khu vực được bảo vệ. Tổng diện tích thông khí của các lỗ mở (phần ô cửa, cửa sổ, khe hở nằm dưới biên dưới của tầng khói) phải được xác định phù hợp với D.4 và đáp ứng yêu cầu vận tốc dòng không khí đi qua các lỗ cửa không vượt quá 6 m/s (không yêu cầu vận tốc này đối với các lỗ mở để bù không khí mà con người không thoát nạn qua đó);

b) Cấp không khí vào theo cơ chế cưỡng bức: sử dụng hệ thống cấp không khí vào với lưu lượng và áp suất bảo đảm bù lại lượng khói đã bị hút ra ngoài."""
        text_d = clean_section(text_d, "muc-D-14-5", "### D.14.5  Cấp không khí bù", body_d_14_5)

        annex_d_file.write_text(text_d, encoding="utf-8")
        print("  [OK] Consolidated Phụ lục D.")

    # Annex E
    annex_e_file = ANNEXES_DIR / "phu_luc_e_khoang_cach_pccc.md"
    bak_e_file = ANNEXES_DIR / "phu_luc_e_khoang_cach_pccc.md.bak"
    if bak_e_file.exists():
        text_e = bak_e_file.read_text(encoding="utf-8")
        
        # Bảng E.1 CHÚ THÍCH 6
        if 'id="bang-E-1"' in text_e or 'id="bang-e-1"' in text_e:
            text_e = re.sub(
                r'CHÚ THÍCH 6:.*?(?=\n\n(?:#{1,4}\s*)?<a id=|\n\n###|\Z)',
                """CHÚ THÍCH 6: Không quy định khoảng cách giữa các nhà và công trình công cộng khi tổng diện tích đất xây dựng (gồm cả diện tích đất không xây dựng giữa chúng) không vượt quá diện tích tầng cho phép lớn nhất trong phạm vi của một khoang cháy (xem Phụ lục H). Trong trường hợp nhà thuộc nhóm F1.1, F4.1 thì không được bố trí các phòng kho, bếp ăn tại khu vực tiếp giáp giữa hai nhà.

Diện tích đất không xây dựng giữa hai nhà là diện tích hình chiếu bằng giới hạn bởi hai tường bao đối diện của hai nhà và các đường nối hai điểm góc đối diện nhau của hai nhà.

Chú thích này không áp dụng cho các cơ sở kinh doanh khí đốt, chất lỏng cháy và chất lỏng dễ bắt cháy, cũng như các chất và vật liệu có khả năng nổ và cháy khi tác dụng với nước, ô xi trong không khí hoặc giữa chúng với nhau.""",
                text_e, flags=re.DOTALL
            )

        # E.2
        text_e = re.sub(r'trong một cơ sở công nghiệp', 'sản xuất, nhà kho', text_e)

        # E.3 Heading
        text_e = re.sub(
            r'###\s+E\.3\s+Xác định diện tích lỗ mở không được bảo vệ chống cháy.*?\n',
            '### <a id="muc-E-3"></a>E.3  Khoảng cách phòng cháy chống cháy xác định theo đường ranh giới\n',
            text_e
        )

        # E.3.1
        text_e = re.sub(r'để xác định', 'được xác định tương ứng với', text_e)

        # E.3.2
        text_e = re.sub(
            r'đo theo phương ngang vuông góc 90° từ tường ngoài nhà',
            'đo vuông góc theo phương ngang từ mặt ngoài tường ngoài nhà (hoặc từ mép ngoài của bộ phận cháy được gần nhất trong nhà, bao gồm cả nội thất)',
            text_e
        )

        # E.3.3
        body_e_3_3 = """E.3.3  Tỷ lệ tổng diện tích lớn nhất của các lỗ mở không được bảo vệ chống cháy so với tổng diện tích bề mặt tường đối diện với đường ranh giới được xác định theo các bảng E.4a và E.4b. Giới hạn chịu lửa của phần tường được bảo vệ chống cháy được quy định tại Bảng E.3.

Khi tường ngoài có yêu cầu về giới hạn chịu lửa theo Bảng E.3 thì tổng diện tích các lỗ mở không được bảo vệ chống cháy không được vượt quá các giá trị cho phép tại Bảng E.4a hoặc Bảng E.4b. Khi tường ngoài không có yêu cầu về giới hạn chịu lửa theo Bảng E.3 thì diện tích các lỗ mở không cần tuân thủ Bảng E.4a hoặc Bảng E.4b.

Cho phép nhân đôi diện tích lỗ mở không được bảo vệ chống cháy nếu nhà đang xét được trang bị chữa cháy tự động. Cho phép sử dụng giải pháp khác ngăn cháy lan như quy định tại đoạn b) điểm 4.35 đối với các ô cửa từ E 60 trở xuống.

_CHÚ THÍCH: Trong mọi trường hợp, phải tuân thủ cả yêu cầu chống cháy lan theo mặt ngoài nhà tại 4.3.2, 4.3.3._"""
        text_e = clean_section(text_e, "muc-e-3-3", "### E.3.3  Tỷ lệ tổng diện tích lớn nhất của các lỗ mở không được bảo vệ chống cháy", body_e_3_3, dual_anchor="muc-E-3-3")

        annex_e_file.write_text(text_e, encoding="utf-8")
        print("  [OK] Consolidated Phụ lục E.")

    # Annex G
    annex_g_file = ANNEXES_DIR / "phu_luc_g_khoang_cach_va_chieu_rong_thoat_nan.md"
    bak_g_file = ANNEXES_DIR / "phu_luc_g_khoang_cach_va_chieu_rong_thoat_nan.md.bak"
    if bak_g_file.exists():
        text_g = bak_g_file.read_text(encoding="utf-8")
        
        # G.1.2.1 repeal CHÚ THÍCH
        text_g = re.sub(r'_CHÚ THÍCH:.*?_', '*(CHÚ THÍCH đã được bãi bỏ theo Thông tư 09/2023/TT-BXD)*', text_g)

        # Bảng G2a: Bãi bỏ chữ "buồng" tại điểm 1
        text_g = re.sub(r'buồng thang bộ', 'thang bộ', text_g, count=1)

        # G.3: Bổ sung ", hoặc xác định theo tài liệu chuẩn khác (ví dụ [5])"
        text_g = re.sub(r'Bảng G\.9(?!\s*,\s*hoặc xác định theo tài liệu chuẩn khác)', 'Bảng G.9, hoặc xác định theo tài liệu chuẩn khác (ví dụ [5])', text_g)

        annex_g_file.write_text(text_g, encoding="utf-8")
        print("  [OK] Consolidated Phụ lục G.")

    # Annex H
    annex_h_file = ANNEXES_DIR / "phu_luc_h_bac_chiu_lua_va_khoang_chay.md"
    bak_h_file = ANNEXES_DIR / "phu_luc_h_bac_chiu_lua_va_khoang_chay.md.bak"
    if bak_h_file.exists():
        text_h = bak_h_file.read_text(encoding="utf-8")
        
        # H.2.1
        text_h = re.sub(r'và khách sạn kiểu căn hộ như nhà ở', 'dạng căn hộ', text_h)

        # H.2.4.4
        pat_h244 = r'((?:###\s*)?(?:<a\s+id=[\"\x27]muc-H-2-4-4[\"\x27][^>]*></a>\s*)?###\s+H\.2\.4\.4\s+.*?)(?=\n(?:#{1,4}\s*)?<a\s+id=|\n###\s+[0-9A-Z]|\Z)'
        body_h_2_4_4 = """<a id="muc-H-2-4-4"></a>
### H.2.4.4  Bố trí các phòng trên tầng 3 nhà trẻ, mẫu giáo, mầm non

> *[Sửa đổi bởi Thông tư 09/2023/TT-BXD (Sửa đổi 1:2023), hiệu lực 01/12/2023]*

H.2.4.4 Trên tầng 3 của nhà trẻ, mẫu giáo, mầm non cho phép bố trí các phòng dành cho lớp lớn, phòng học nhạc và thể chất, phòng chơi, phòng phục vụ. Khi đó các phòng có diện tích lớn hơn 50 m2 thì phải có một trong các lối ra thoát nạn dẫn trực tiếp vào thang bộ thoát nạn hoặc đi qua hành lang thoát nạn vào thang bộ thoát nạn.

Trong nhà trẻ, mẫu giáo, mầm non, các hành lang nối các buồng thang bộ cần được ngăn cách với các phòng bằng vách ngăn cháy không thấp hơn loại 2. Các cửa vào các phòng phải được chèn kín."""
        if re.search(pat_h244, text_h, flags=re.DOTALL):
            text_h = re.sub(pat_h244, body_h_2_4_4, text_h, count=1, flags=re.DOTALL)
            print("  [OK] Updated Mục H.2.4.4.")

        # Bảng H.6 CHÚ THÍCH (Verbatim SĐ1)
        chuthich_h6_old = "_CHÚ THÍCH: Số tầng nhà được xác định bằng số các tầng trên mặt đất, không tính tầng kỹ thuật trên cùng._"
        chuthich_h6_new = "_CHÚ THÍCH: Số tầng nhà được xác định bằng số các tầng trên mặt đất, không tính tầng kỹ thuật trên cùng. Đối với trường trung học cơ sở và trung học phổ thông hoặc tương đương, chiều cao PCCC lớn nhất cho phép của nhà được lấy đến 25 m (7 tầng) nếu nhà có tối thiểu hai thang thoát nạn bảo đảm yêu cầu của quy chuẩn này._"
        if chuthich_h6_old in text_h:
            text_h = text_h.replace(chuthich_h6_old, chuthich_h6_new, 1)
            print("  [OK] Updated CHÚ THÍCH of Bảng H.6.")
        else:
            text_h = re.sub(
                r'(###\s+<a\s+id=[\"\x27]bang-h-6[\"\x27].*?_?CHÚ THÍCH:[^\n]+)(?=\n(?:#{1,4}\s*)?<a|\n###|\Z)',
                r'\1 Đối với trường trung học cơ sở và trung học phổ thông hoặc tương đương, chiều cao PCCC lớn nhất cho phép của nhà được lấy đến 25 m (7 tầng) nếu nhà có tối thiểu hai thang thoát nạn bảo đảm yêu cầu của quy chuẩn này.',
                text_h, flags=re.DOTALL
            )
            print("  [OK] Updated CHÚ THÍCH of Bảng H.6 via regex.")

        # H.2.9.1
        body_h_2_9_1 = """H.2.9.1 Nhà bệnh viện (nhóm F1.1) cần được bố trí trong các nhà đứng độc lập hoặc trong khoang cháy riêng với chiều cao PCCC không quá 28 m (hoặc 9 tầng).

Trường hợp bố trí các công năng chính của bệnh viện (nhóm F1.1) vượt quá chiều cao PCCC 28 m (hoặc quá 9 tầng, nhưng tối đa 50 m), phải tuân thủ đồng thời các yêu cầu sau:
- Bậc chịu lửa của nhà phải là bậc I;
- Toàn bộ nhà được trang bị hệ thống chữa cháy tự động;
- Các buồng thang bộ thoát nạn phải là buồng thang không nhiễm khói loại N1 hoặc N2;
- Mỗi tầng nhà phải có ít nhất một thang máy chữa cháy phục vụ."""
        text_h = clean_section(text_h, "muc-H-2-9-1", "### H.2.9.1  Bố trí nhà bệnh viện (nhóm F1.1)", body_h_2_9_1)

        # H.2.10.1
        body_h_2_10_1 = """H.2.10.1 Chiều cao PCCC của nhà khám bệnh đa khoa ngoại trú (nhóm F3.4) tối đa 28 m (hoặc 9 tầng). Bậc chịu lửa của nhà từ 2 tầng trở lên không được thấp hơn bậc II, cấp nguy hiểm cháy kết cấu không thấp hơn S0.

Trường hợp bố trí các công năng đa khoa ngoại trú (nhóm F3.4) vượt quá chiều cao PCCC 28 m (hoặc quá 9 tầng, nhưng tối đa 50 m), phải tuân thủ đồng thời các yêu cầu bổ sung như quy định tại H.2.9.1."""
        text_h = clean_section(text_h, "muc-H-2-10-1", "### H.2.10.1  Chiều cao PCCC của nhà khám bệnh đa khoa ngoại trú", body_h_2_10_1)

        # H.2.10.3 (Repealed)
        body_h_2_10_3 = """*(Nội dung điểm H.2.10.3 đã được bãi bỏ theo quy định tại Thông tư 09/2023/TT-BXD)*"""
        text_h = clean_section(text_h, "muc-H-2-10-3", "### H.2.10.3  Gian phòng khám đa khoa ngoại trú", body_h_2_10_3, is_repeal=True)

        # H.2.11.1 (Dual anchor: canonical H.2.11.1 and legacy H.2.1.1.1)
        body_h_2_11_1 = """H.2.11.1  Các nhà ngủ của cơ sở điều dưỡng không được cao quá 28 m (hoặc 9 tầng). Trường hợp cao quá 28 m (hoặc quá 9 tầng) phải tuân thủ các yêu cầu bổ sung như quy định tại H.2.9.1. Bậc chịu lửa của nhà từ 2 tầng trở lên không được thấp hơn bậc II, cấp nguy hiểm cháy kết cấu không thấp hơn S0."""
        text_h = clean_section(text_h, "muc-H-2-1-1-1", "### H.2.11.1  Chiều cao PCCC của nhà ngủ cơ sở điều dưỡng", body_h_2_11_1, dual_anchor="muc-H-2-11-1")

        # H.2.12.4
        if 'id="muc-H-2-12-4"' in text_h or 'id="muc-h-2-12-4"' in text_h:
            add_h2124 = "\n\nKhông yêu cầu giới hạn chịu lửa của mái hiên, mái che phần phụ, mái che hành lang, sảnh ngoài nhà như quy định tại H.2.12.1 và H.2.12.4 nếu mái không khai thác sử dụng, hoặc không có nguy cơ cháy lan từ các khu vực dưới mái lên khối nhà chính."
            text_h = re.sub(r'(<a id="muc-H-2-12-4"[^>]*></a>.*?)(?=\n(?:#{1,4}\s*)?<a id="muc-H-2-12-5"|\n### H\.2\.12\.5)', r'\1' + add_h2124 + '\n', text_h, flags=re.DOTALL)

        # H.2.12.10: Bổ sung điểm H.2.12.10
        if 'id="muc-H-2-12-10"' not in text_h:
            item_h_2_12_10 = """<a id="muc-H-2-12-10"></a><a id="muc-H-2-1-2-1-0"></a>
### H.2.12.10  Xác định chiều cao PCCC theo số tầng trên mặt đất

> *[Sửa đổi bởi Thông tư 09/2023/TT-BXD (Sửa đổi 1:2023), hiệu lực 01/12/2023]*

Chiều cao PCCC lớn nhất cho phép của nhà tại các bảng H.5, H.6 và H.7 có thể xác định không theo giá trị mét, mà theo số tầng trên mặt đất không kể tầng kỹ thuật trên cùng (giá trị trong ngoặc đơn tại cột 4 của các bảng, nếu có) khi nhà được trang bị hệ thống báo cháy tự động hoặc hệ thống chữa cháy tự động.
"""
            text_h = re.sub(r'(<a\s+id=[\"\x27]muc-H-2-1?-2-9[\"\x27][^>]*></a>.*?)(?=\n###\s+<a\s+id=[\"\x27]bang-h-8[\"\x27]|\n<a\s+id=[\"\x27]bang-h-8[\"\x27]|\n###\s+Bảng H\.8|\Z)', r'\1\n\n' + item_h_2_12_10 + '\n', text_h, flags=re.DOTALL)
            print("  [OK] Inserted Mục H.2.12.10.")

        # Bảng H.8 CHÚ THÍCH 2
        text_h = re.sub(
            r'(\*\*CHÚ THÍCH 2:\*\*.*?)(?=\n\n(?:#{1,4}\s*)?<a id=|\n\n###|\Z)',
            r'\1 Trường hợp nhà được trang bị hệ thống báo cháy tự động hoặc hệ thống chữa cháy tự động, hoặc nếu nhà có tối thiểu hai cầu thang thoát nạn thỏa mãn yêu cầu của quy chuẩn này thì chiều cao bố trí các gian phòng trên tuân thủ Bảng H.8.',
            text_h, flags=re.DOTALL
        )

        # H.4.1: Thay theo A.2.1 bằng theo A.1.2
        text_h = re.sub(r'theo A\.2\.1', 'theo A.1.2', text_h)

        # Bảng H.9: Cập nhật các ô sửa đổi
        text_h = re.sub(r'\| C \| IV \| S0, S1 \| 1 \| 25 \| - \|', '| C | IV | S0, S1 | 1 | 25 | 1 400 5) |', text_h)
        text_h = re.sub(r'\| C \| IV \| S2, S3 \| 1 \| 18 \| - \|', '| C | IV | S2, S3 | 1 | 18 | 1 100 5) |', text_h)

        # Bảng H.10: Cập nhật các ô sửa đổi
        text_h = re.sub(r'\| C \| IV \| S0, S1 \| 1 \| 25 \| - \|', '| C | IV | S0, S1 | 1 | 25 | 1 400 2) |', text_h)
        text_h = re.sub(r'\| C \| IV \| S2, S3 \| 1 \| 18 \| - \|', '| C | IV | S2, S3 | 1 | 18 | 1 100 2) |', text_h)

        # Bảng H.11: Cập nhật các ô sửa đổi
        text_h = re.sub(r'\| E \| IV \| S0, S1 \| 1 \| 12 \|', '| E | IV | S0, S1 | 1 | Không quy định |', text_h)

        # H.5.2
        body_h_5_2 = """H.5.2  Đối với các nhà kho có sàn công tác, sàn đỡ thiết bị và sàn lửng thì số tầng và diện tích tầng trong phạm vi một khoang cháy xác định tương tự như nhà sản xuất đã được quy định tại H.4.1. Khi có các lỗ mở trên sàn giữa các tầng thì tổng diện tích các tầng này không được vượt quá giá trị quy định tại Bảng H.11."""
        text_h = clean_section(text_h, "muc-H-5-2", "### H.5.2  Nhà kho có sàn công tác, sàn đỡ thiết bị và sàn lửng", body_h_5_2)

        # H.6.2
        text_h = re.sub(
            r'-\s+Trong các nhà thuộc nhóm nguy hiểm cháy theo công năng F1\.1, F1\.2, F2 đến F4 với các gian thông tầng để bố trí cầu thang hở.*?vách ngăn cháy loại 1\.',
            '- Trong các nhà thuộc nhóm nguy hiểm cháy theo công năng F1.1, F1.2, F2 đến F4 với các gian thông tầng để bố trí cầu thang hở, thang cuốn, sảnh thông tầng và các công năng khác, diện tích một sàn trong phạm vi một khoang cháy là tổng diện tích của tầng dưới cùng của gian thông tầng và của các hành lang, lối đi bộ và các gian phòng của tất cả các tầng phía trên của gian thông tầng trong phạm vi không gian được ngăn cách bởi các vách ngăn cháy loại 1.',
            text_h
        )

        # H.7: Bổ sung điểm H.7
        if 'id="muc-H-7"' not in text_h:
            item_h_7 = """<a id="muc-H-7"></a>
### H.7  Các yêu cầu an toàn cháy bổ sung trong một số trường hợp khác

> *[Sửa đổi bởi Thông tư 09/2023/TT-BXD (Sửa đổi 1:2023), hiệu lực 01/12/2023]*

H.7.1 Trong trường hợp phần nhà có công năng xác định (và các công năng phụ trợ cho công năng chính) được ngăn cách thành một khoang cháy riêng thì các yêu cầu của Phụ lục H được áp dụng cho phần nhà (khoang cháy) đó. Các công năng độc lập khác được phép áp dụng các yêu cầu an toàn cháy theo công năng riêng của chúng.

H.7.2 Đối với các nhà hỗn hợp có từ hai nhóm nguy hiểm cháy theo công năng trở lên, nếu các khu vực công năng khác nhau không được ngăn cách thành các khoang cháy riêng thì bậc chịu lửa, cấp nguy hiểm cháy kết cấu, chiều cao PCCC và diện tích sàn lớn nhất cho phép của một tầng trong phạm vi khoang cháy phải lấy theo yêu cầu khắt khe nhất của các công năng có trong nhà.
"""
            text_h = text_h.strip() + "\n\n" + item_h_7 + "\n"

        annex_h_file.write_text(text_h, encoding="utf-8")
        print("  [OK] Consolidated Phụ lục H.")


def run_consolidation():
    print("=" * 80)
    print("QCVN 06:2022/BXD DETERMINISTIC LIVING STANDARD CONSOLIDATION ENGINE")
    print("=" * 80)
    print(f"Master file:    {MASTER_FILE}")
    print(f"Backup file:    {BAK_FILE}")
    print(f"Amendment file: {AMENDMENT_FILE}")
    
    if not BAK_FILE.exists():
        print(f"Creating backup baseline from {MASTER_FILE} -> {BAK_FILE}")
        shutil.copyfile(MASTER_FILE, BAK_FILE)
    
    # Load from clean 2022 backup baseline to guarantee zero residual drift
    print("Loading pristine baseline from backup...")
    base_text = BAK_FILE.read_text(encoding="utf-8")
    
    # Consolidate master Chapters 1-7
    print("\nConsolidating Master Chapters 1-7...")
    consolidated_text = consolidate_master(base_text)
    MASTER_FILE.write_text(consolidated_text, encoding="utf-8")
    print(f"Successfully updated master living standard: {MASTER_FILE} ({len(consolidated_text)} chars / {len(consolidated_text.encode('utf-8'))} bytes)")
    
    # Consolidate Annexes
    print("\nConsolidating Modular Annexes...")
    consolidate_annexes()
    
    print("\n" + "=" * 80)
    print("Consolidation complete! Master and Annexes are now living standard.")
    print("=" * 80)


if __name__ == "__main__":
    run_consolidation()
