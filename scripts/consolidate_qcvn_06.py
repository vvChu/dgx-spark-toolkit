#!/usr/bin/env python3
"""Consolidates QCVN 06:2022/BXD master document with Amendment 1:2023 (TT 09/2023/TT-BXD).

Adheres to:
- ADR-0059: Legal Verbatim Grounding & Mandatory Acquisition Invariant
- ADR-0061: Platform-Aware KISS v2.0
- Grok 4.7 xhigh Verdict: Living Standard Consolidation Gate
"""

import re
import sys
from pathlib import Path

VAULT_DIR = Path("/home/vvc/ccba/ccba-legal-knowledge/legal_docs/02_qcvn/qcvn_06_2022_bxd")
MASTER_FILE = VAULT_DIR / "qcvn_06_2022_bxd.md"
SD1_FILE = VAULT_DIR / "sources/sua_doi_1_2023_qcvn_06_2022_bxd.md"
GOC_FILE = VAULT_DIR / "sources/qcvn_06_2022_bxd_goc_2022.md"

CITATION_LINE = "> *[Sửa đổi bởi Thông tư 09/2023/TT-BXD (Sửa đổi 1:2023), hiệu lực 01/12/2023]*\n\n"
REPEAL_LINE = "> *[Bãi bỏ bởi Thông tư 09/2023/TT-BXD (Sửa đổi 1:2023)]*\n\n"


def run_consolidation():
    if not MASTER_FILE.exists() or not SD1_FILE.exists():
        print(f"ERROR: Missing files in {VAULT_DIR}", file=sys.stderr)
        sys.exit(1)

    master_text = MASTER_FILE.read_text(encoding="utf-8")

    # --- Header / Lời nói đầu Enhancement ---
    if "Thông tư số 09/2023/TT-BXD" not in master_text[:3000]:
        loi_noi_dau_old = (
            "QCVN 06:2022/BXD thay thế QCVN 06:2021/BXD ban hành kèm theo Thông tư số "
            "02/2021/TT-BXD ngày 19 tháng 5 năm 2021 của Bộ trưởng Bộ Xây dựng."
        )
        loi_noi_dau_new = (
            loi_noi_dau_old + "\n\n"
            "Sửa đổi 1:2023 QCVN 06:2022/BXD do Viện Khoa học công nghệ xây dựng (Bộ Xây dựng) "
            "chủ trì biên soạn, Bộ Xây dựng ban hành kèm theo Thông tư số 09/2023/TT-BXD ngày 10 tháng 10 năm 2023 "
            "của Bộ trưởng Bộ Xây dựng (có hiệu lực từ ngày 01 tháng 12 năm 2023). "
            "Văn bản này là ấn bản hợp nhất thực chất, tích hợp toàn bộ các sửa đổi, bổ sung và bãi bỏ của Sửa đổi 1:2023."
        )
        if loi_noi_dau_old in master_text:
            master_text = master_text.replace(loi_noi_dau_old, loi_noi_dau_new, 1)
            print("Updated Lời nói đầu with SĐ1 integration note.")

    # --- 1.1.2 Scope of residential buildings ---
    pattern_1_1_2 = r'(<a\s+id="muc-1-1-2"[^>]*></a>\s*###\s*1\.1\.2[^\n]*\n\n)(.*?)(?=\n<a\s+id="muc-1-1-3")'
    replacement_1_1_2 = r'''\1''' + CITATION_LINE + '''1.1.2 Quy chuẩn này áp dụng đối với các nhà sau:

a) Nhà ở:

_GHI CHÚ CHỈ SỐ PHỤ:_
- **1)** Chung cư và nhà ở tập thể có chiều cao PCCC không quá 150 m và không quá 3 tầng hầm;

_GHI CHÚ CHỈ SỐ PHỤ:_
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

Đối với các nhà đứng độc lập (trừ các nhà thuộc nhóm F5 và các nhà đã nêu tại CHÚ THÍCH của đoạn 2) điểm 1.1.2) có chiều cao dưới 7 tầng, chiều cao PCCC dưới 25 m và khối tích dưới 5 000 m3), nếu không thể tuân thủ các quy định của quy chuẩn này thì căn cứ trên công năng cụ thể của nhà cũng có thể áp dụng các tài liệu chuẩn để thiết kế an toàn cháy và tuân thủ các quy định pháp luật có liên quan.
'''
    master_text, count_1_1_2 = re.subn(pattern_1_1_2, replacement_1_1_2, master_text, flags=re.DOTALL)
    print(f"Applied Mục 1.1.2: {count_1_1_2} replacement(s)")

    # --- 1.1.4 Partial Renovation & Scope ---
    pattern_1_1_4 = r'(<a\s+id="muc-1-1-4"[^>]*></a>\s*###\s*1\.1\.4[^\n]*\n\n)(.*?)(?=\n<a\s+id="muc-1-1-5")'
    replacement_1_1_4 = r'''\1''' + CITATION_LINE + '''1.1.4 Quy chuẩn này áp dụng khi xây dựng mới các nhà thuộc phạm vi điều chỉnh của quy chuẩn này; hoặc chỉ áp dụng đối với các bộ phận, khu vực trực tiếp được cải tạo sửa chữa, trong các trường hợp sau:

a) Cải tạo, sửa chữa thay đổi công năng của tầng nhà, khoang cháy hoặc nhà dẫn đến nâng cao các yêu cầu an toàn cháy đối với tầng nhà, khoang cháy và nhà;

b) Cải tạo, sửa chữa làm thay đổi các giải pháp thoát nạn của tầng nhà, khoang cháy hoặc nhà theo hướng làm giảm số lượng lối thoát nạn hoặc cầu thang thoát nạn;

c) Cải tạo, sửa chữa làm tăng hạng nguy hiểm cháy và cháy nổ của tầng nhà, khoang cháy hoặc nhà;

d) Cải tạo, sửa chữa tăng quy mô dẫn đến nâng cao các yêu cầu an toàn cháy đối với tầng nhà, khoang cháy và nhà.

Trường hợp nhà, khoang cháy hoặc tầng nhà được cải tạo, sửa chữa không thể đáp ứng các yêu cầu của quy chuẩn này thì áp dụng 1.1.10.
'''
    master_text, count_1_1_4 = re.subn(pattern_1_1_4, replacement_1_1_4, master_text, flags=re.DOTALL)
    print(f"Applied Mục 1.1.4: {count_1_1_4} replacement(s)")

    # --- 1.1.5 Exclusions (Road tunnels, lighthouses) ---
    pattern_1_1_5 = r'(<a\s+id="muc-1-1-5"[^>]*></a>\s*###\s*1\.1\.5[^\n]*\n\n)(.*?)(?=\n<a\s+id="muc-1-1-6")'
    replacement_1_1_5 = r'''\1''' + CITATION_LINE + '''1.1.5 Quy chuẩn này không áp dụng cho các nhà có công năng đặc biệt như: nhà sản xuất và kho chứa chất nổ, vật liệu nổ; cơ sở sản xuất và chế biến các chất lỏng và chất khí dễ cháy; các công trình hạt nhân; các công trình ngầm; các công trình trên biển; các nhà cao tầng có chiều cao PCCC trên 150 m; các công trình quân sự, an ninh; các trạm kiểm soát không lưu; công trình hầm giao thông; tháp đèn biển; các công trình dầu khí ngoài khơi, mỏ khoáng sản ngầm.
'''
    master_text, count_1_1_5 = re.subn(pattern_1_1_5, replacement_1_1_5, master_text, flags=re.DOTALL)
    print(f"Applied Mục 1.1.5: {count_1_1_5} replacement(s)")

    # --- 1.1.7 Foreign standards ---
    pattern_1_1_7 = r'(<a\s+id="muc-1-1-7"[^>]*></a>\s*###\s*1\.1\.7[^\n]*\n\n)(.*?)(?=\n<a\s+id="muc-1-1-8")'
    replacement_1_1_7 = r'''\1''' + CITATION_LINE + '''1.1.7 Cho phép sử dụng các tài liệu chuẩn của nước ngoài trên cơ sở bảo đảm nguyên tắc quy định tại 1.5 của quy chuẩn này và các quy định pháp luật của Việt Nam về phòng cháy, chữa cháy cùng các quy định về áp dụng tiêu chuẩn của nước ngoài trong hoạt động xây dựng ở Việt Nam.
'''
    master_text, count_1_1_7 = re.subn(pattern_1_1_7, replacement_1_1_7, master_text, flags=re.DOTALL)
    print(f"Applied Mục 1.1.7: {count_1_1_7} replacement(s)")

    # --- 1.1.10 Case-by-case Engineering Argumentation ---
    pattern_1_1_10 = r'(<a\s+id="muc-1-1-10"[^>]*></a>\s*###\s*1\.1\.10[^\n]*\n\n)(.*?)(?=\n<a\s+id="muc-1-1-11"|\n<a\s+id="muc-1-2")'
    replacement_1_1_10 = r'''\1''' + CITATION_LINE + '''1.1.10 Trong một số trường hợp riêng biệt, có thể xem xét bổ sung, thay thế một số yêu cầu của quy chuẩn này đối với công trình cụ thể bằng các yêu cầu an toàn cháy phù hợp khác theo tài liệu chuẩn hoặc có luận chứng kỹ thuật phù hợp.
'''
    master_text, count_1_1_10 = re.subn(pattern_1_1_10, replacement_1_1_10, master_text, flags=re.DOTALL)
    print(f"Applied Mục 1.1.10: {count_1_1_10} replacement(s)")

    # --- 1.1.11 Local Regulations (Verbatim SĐ1) ---
    pattern_1_1_11 = r'(<a\s+id="muc-1-1-11"[^>]*></a>.*?)(?=\n<a\s+id="muc-1-2")'
    replacement_1_1_11 = '''<a id="muc-1-1-11"></a>\n### 1.1.11  Quy chuẩn kỹ thuật địa phương\n\n''' + CITATION_LINE + '''1.1.11 Các địa phương được ban hành quy chuẩn kỹ thuật địa phương để thay thế, sửa đổi hoặc bổ sung một số quy định tại các phần 3, 4, 5, 6 và các phụ lục của quy chuẩn này cho phù hợp với điều kiện đặc thù của địa phương, trên cơ sở tuân thủ quy định pháp luật về tiêu chuẩn, quy chuẩn kỹ thuật và pháp luật về phòng cháy chữa cháy.\n'''
    master_text, count_1_1_11 = re.subn(pattern_1_1_11, replacement_1_1_11, master_text, flags=re.DOTALL)
    print(f"Applied Mục 1.1.11: {count_1_1_11} replacement(s)")

    # --- 1.3 Repealed ---
    pattern_1_3 = r'(<a\s+id="muc-1-3"[^>]*></a>\s*###\s*1\.3[^\n]*\n\n)(.*?)(?=\n<a\s+id="muc-1-4")'
    replacement_1_3 = r'''\1''' + REPEAL_LINE + '''*(Nội dung điểm 1.3 đã được bãi bỏ theo quy định tại Thông tư số 09/2023/TT-BXD ngày 10/10/2023)*
'''
    master_text, count_1_3 = re.subn(pattern_1_3, replacement_1_3, master_text, flags=re.DOTALL)
    print(f"Repealed Mục 1.3: {count_1_3} replacement(s)")

    # --- 1.4.21a Gian phòng chung (Verbatim SĐ1) ---
    pattern_1_4_21a = r'(<a\s+id="muc-1-4-21a"[^>]*></a>.*?)(?=\n<a\s+id="muc-1-4-22"|\n####\s+<a\s+id="muc-1-4-22")'
    replacement_1_4_21a = '''<a id="muc-1-4-21a"></a>\n#### 1.4.21a  Gian phòng chung\n\n''' + CITATION_LINE + '''Gian phòng có diện tích không quá 300 m2 trong các nhà nhóm F1.1, F1.2, F2, F3, F4, được bố trí tại các tầng nổi, có từ 2 lối ra vào hành lang bên hoặc lối ra ngoài trời và được ngăn cách với các khu vực khác của tầng nhà bằng các vách ngăn cháy loại 1 và cửa ngăn cháy loại 2 có cơ cấu tự đóng.\n'''
    master_text, count_1_4_21a = re.subn(pattern_1_4_21a, replacement_1_4_21a, master_text, flags=re.DOTALL)
    print(f"Applied Mục 1.4.21a: {count_1_4_21a} replacement(s)")

    # --- 3.4.13 (Target: muc-3-4-1-3) ---
    pattern_3_4_13 = r'(<a\s+id="muc-3-4-1-3"[^>]*></a>\s*###\s*3\.4\.1\.3[^\n]*\n\n)(.*?)(?=\n<a\s+id="muc-3-4-14")'
    replacement_3_4_13 = r'''\1''' + CITATION_LINE + '''3.4.13 Trong các nhà có chiều cao PCCC lớn hơn 28 m (trừ các nhà nhóm F5 hạng C, E không có người làm việc thường xuyên), cũng như trong các nhà nhóm F5 hạng A hoặc B phải bố trí buồng thang bộ không nhiễm khói, trong đó phải bố trí buồng thang loại N1.

_CHÚ THÍCH: Buồng thang bộ N1 có thể được thay thế như đã nêu tại 2.4.3.3 với điều kiện hệ thống cung cấp không khí bên ngoài vào khoang đệm và vào buồng thang phải được cấp điện ưu tiên từ hai nguồn độc lập (1 nguồn điện lưới và 1 nguồn máy phát điện dự phòng) bảo đảm nguyên tắc duy trì liên tục nguồn điện cấp cho hệ thống hoạt động ổn định khi có cháy xảy ra._

Cho phép:

b) Khi nhà có từ hai tầng hầm trở lên, việc thoát nạn từ các tầng hầm này có thể theo các buồng thang bộ loại N3, hoặc loại N2 có lối vào buồng thang đi qua khoang đệm với giải pháp bao che giống như khoang đệm ngăn cháy loại 1;

c) Trong các nhà nhóm F5 bố trí các buồng thang bộ không nhiễm khói thay cho loại N1 như sau:

- Trong các nhà hạng A hoặc B - các buồng thang bộ N2 hoặc N3 có áp suất không khí dương thường xuyên;

- Trong các nhà hạng C - các buồng thang bộ N2 hoặc N3 với áp suất không khí dương khi có cháy;

- Trong các nhà hạng D, E - các buồng thang bộ N2 hoặc N3 với áp suất không khí dương khi có cháy, hoặc các buồng thang bộ L1 với điều kiện buồng thang phải được phân khoang bằng vách ngăn cháy đặc qua mỗi 20 m chiều cao và lối đi từ khoang này sang khoang khác của buồng thang phải đặt ở ngoài không gian của buồng thang.
'''
    master_text, count_3_4_13 = re.subn(pattern_3_4_13, replacement_3_4_13, master_text, flags=re.DOTALL)
    print(f"Applied Mục 3.4.13: {count_3_4_13} replacement(s)")

    # --- 4.3.2.2 (Target: muc-4-3-2-2) ---
    pattern_4_3_2_2 = r'(<a\s+id="muc-4-3-2-2"[^>]*></a>\s*\n###\s*4\.3\.2\.2[^\n]*\n*)(.*?)(?=\n<a\s+id="muc-4-3-3")'
    replacement_4_3_2_2 = '''<a id="muc-4-3-2-2"></a>\n### 4.3.2.2  Miễn áp dụng quy định khoảng cách khi có chữa cháy tự động\n\n''' + CITATION_LINE + '''4.3.2.2 Cho phép không áp dụng các quy định tại 4.3.2.1 nếu nhà được trang bị chữa cháy tự động.\n'''
    master_text, count_4_3_2_2 = re.subn(pattern_4_3_2_2, replacement_4_3_2_2, master_text, flags=re.DOTALL)
    print(f"Applied Mục 4.3.2.2: {count_4_3_2_2} replacement(s)")

    # --- 4.3.3.3 (Target: muc-4-3-3-3) ---
    pattern_4_3_3_3 = r'(<a\s+id="muc-4-3-3-3"[^>]*></a>\s*\n###\s*4\.3\.3\.3[^\n]*\n*)(.*?)(?=\n<a\s+id="muc-4-3-3-4")'
    replacement_4_3_3_3 = '''<a id="muc-4-3-3-3"></a>\n### 4.3.3.3  Lỗ mở tường ngoài góc hẹp\n\n''' + CITATION_LINE + '''4.3.3.3 Khi một phần tường ngoài của nhà nối tiếp với một phần khác của tường, tạo thành một góc nhỏ hơn 135° và khoảng cách theo phương nằm ngang giữa các mép gần nhất của các lỗ mở ở tường ngoài theo các hướng khác nhau của định góc, nhỏ hơn 4 m, thì trên phần tương ứng của tường, các lỗ mở phải có các cửa ngăn cháy có giới hạn chịu lửa không nhỏ hơn E 30 hoặc có hệ thống phun nước như quy định tại đoạn c) điểm 4.3.3.1.\n'''
    master_text, count_4_3_3_3 = re.subn(pattern_4_3_3_3, replacement_4_3_3_3, master_text, flags=re.DOTALL)
    print(f"Applied Mục 4.3.3.3: {count_4_3_3_3} replacement(s)")

    # --- 4.3.3.4 (Target: muc-4-3-3-4) ---
    pattern_4_3_3_4 = r'(<a\s+id="muc-4-3-3-4"[^>]*></a>\s*\n###\s*4\.3\.3\.4[^\n]*\n*)(.*?)(?=\n<a\s+id="muc-4-3-4")'
    replacement_4_3_3_4 = '''<a id="muc-4-3-3-4"></a>\n### 4.3.3.4  Miễn áp dụng quy định đối với tường ngoài\n\n''' + CITATION_LINE + '''4.3.3.4 Cho phép không áp dụng các quy định tại 4.3.3 đối với nhà từ ba tầng trở xuống hoặc có chiều cao PCCC dưới 15 m, ga ra để xe nổi dạng hở, hoặc nhà được trang bị chữa cháy tự động.\n'''
    master_text, count_4_3_3_4 = re.subn(pattern_4_3_3_4, replacement_4_3_3_4, master_text, flags=re.DOTALL)
    print(f"Applied Mục 4.3.3.4: {count_4_3_3_4} replacement(s)")

    # --- Bảng 10 Clean Table (Un-nest from blockquote, Verbatim SD1) ---
    pattern_bang_10 = r'(###\s*<a\s+id="bang-10"[^>]*></a>\s*Bảng 10[^\n]*\n\n)(.*?)(?=\n###\s*5\.1\.2\.4|\n<a\s+id="muc-5-1-2-4")'
    replacement_bang_10 = r'''\1''' + CITATION_LINE + '''| Bậc chịu lửa của nhà | Cấp nguy hiểm cháy kết cấu của nhà | Hạng nguy hiểm cháy và cháy nổ của nhà | ≤ 50 | > 50 và ≤ 100 | > 100 và ≤ 200 | > 200 và ≤ 300 | > 300 và ≤ 400 | > 400 và ≤ 500 | > 500 và ≤ 600 | > 600 và ≤ 700 | > 700 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| I và II | S0, S1 | A, B, C | 20 | 30 | 40 | 50 | 60 | 70 | 80 | 90 | 100 |
| I và II | S0 | D, E | 10 | 15 | 20 | 25 | 30 | 35 | 40 | 45 | 50 |
| III | S0, S1 | A, B, C | 40 | 50 | 60 | 60 | 70 | 80 | 90 | 100 | 110 |
| III | S0, S1 | D, E | 20 | 35 | 40 | 40 | 45 | 45 | 50 | 50 | 60 |
| IV | S0, S1 | A, B, C | 50 | 60 | 65 | 70 | 80 | 90 | - | - | - |
| IV | S0, S1 | D, E | 35 | 45 | 55 | 60 | 65 | 70 | 75 | 80 | 90 |
| IV | S2, S3 | E | 40 | 50 | 60 | - | - | - | - | - | - |

_CHÚ THÍCH: Lỗ mở trên mái là các lỗ mở để thông gió hoặc lấy sáng đặt trên kết cấu mái của nhà (nóc gió (cửa trời); lỗ thường xuyên mở; lỗ mở khi có cháy; ô kính; tấm lợp lấy sáng, hoặc các lỗ mở tương tự) có diện tích không nhỏ hơn 2,5 % diện tích xây dựng của nhà đó._
'''
    master_text, count_bang_10 = re.subn(pattern_bang_10, replacement_bang_10, master_text, flags=re.DOTALL)
    print(f"Applied Bảng 10 Clean Table: {count_bang_10} replacement(s)")

    # --- 6.12 (Target: muc-6-1-2) ---
    pattern_6_12 = r'(<a\s+id="muc-6-1-2"[^>]*></a>\s*\n###\s*6\.1\.2[^\n]*\n*)(.*?)(?=\n<a\s+id="muc-6-13")'
    replacement_6_12 = '''<a id="muc-6-1-2"></a>\n### 6.12  Khe hở giữa các bản thang và lan can\n\n''' + CITATION_LINE + '''6.12 Giữa các bản thang và giữa các lan can tay vịn của bản thang phải có khe hở với chiều rộng thông thủy chiếu trên mặt bằng không nhỏ hơn 75 mm. Trường hợp không thể bảo đảm yêu cầu này thì tại mỗi tầng cần bố trí ít nhất một họng khô để cấp nước chữa cháy cho tầng đó. Không yêu cầu khe hở vế thang đối với cầu thang loại 3.\n'''
    master_text, count_6_12 = re.subn(pattern_6_12, replacement_6_12, master_text, flags=re.DOTALL)
    print(f"Applied Mục 6.12: {count_6_12} replacement(s)")

    # --- 7.4 (Target: muc-7-4) Repealed ---
    pattern_7_4 = r'(<a\s+id="muc-7-4"[^>]*></a>\s*\n###\s*7\.4[^\n]*\n*)(.*?)(?=\n<a\s+id="muc-7-5")'
    replacement_7_4 = '''<a id="muc-7-4"></a>\n### 7.4  Phối hợp ban hành thông số kỹ thuật địa phương\n\n''' + REPEAL_LINE + '''*(Nội dung điểm 7.4 đã được bãi bỏ theo quy định tại Thông tư số 09/2023/TT-BXD ngày 10/10/2023)*\n'''
    master_text, count_7_4 = re.subn(pattern_7_4, replacement_7_4, master_text, flags=re.DOTALL)
    print(f"Repealed Mục 7.4: {count_7_4} replacement(s)")

    # Write updated master text
    MASTER_FILE.write_text(master_text, encoding="utf-8")
    print(f"Successfully consolidated {MASTER_FILE}!")


if __name__ == "__main__":
    run_consolidation()
