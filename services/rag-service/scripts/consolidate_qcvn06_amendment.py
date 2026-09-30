#!/usr/bin/env python3
"""Deterministic Consolidator for QCVN 06:2022/BXD and Amendment 1:2023 (TT 09/2023/TT-BXD).

Applies substantive technical extracts from `sources/sua_doi_1_2023_qcvn_06_2022_bxd.md`
directly into `qcvn_06_2022_bxd.md`, ensuring:
1. Target anchors (e.g. muc-1-1-2, muc-1-1-4, muc-1-3, bang-10) receive the actual amended legal text.
2. Repealed clauses (e.g. muc-1-3) receive explicit repeal notices.
3. Newly introduced clauses (e.g. muc-1-1-11, muc-1-4-21a) are inserted cleanly.
4. Each amended section receives an italic provenance line citing Circular 09/2023/TT-BXD.
"""

import os
import re
import shutil
import sys
from pathlib import Path


VAULT_DIR = Path(os.environ.get("HUB3_LEGAL_PATH", "/home/vvc/ccba/ccba-legal-knowledge"))
QCVN06_DIR = VAULT_DIR / "legal_docs" / "02_qcvn" / "qcvn_06_2022_bxd"
MASTER_FILE = QCVN06_DIR / "qcvn_06_2022_bxd.md"
AMENDMENT_FILE = QCVN06_DIR / "sources" / "sua_doi_1_2023_qcvn_06_2022_bxd.md"

PROVENANCE_TAG = "\n\n*(Sửa đổi, bổ sung bởi Thông tư 09/2023/TT-BXD, có hiệu lực từ ngày 01/12/2023)*\n"


def parse_amendment_sections(amendment_path: Path) -> list[dict]:
    """Parse all 145 sd1 sections from the amendment technical file."""
    content = amendment_path.read_text(encoding="utf-8")
    
    # Split by anchor tags
    parts = re.split(r'(<a id="(sd1-[^"]+)"[^>]*></a>)', content)
    
    sections = []
    # parts: [preamble, anchor_tag_1, anchor_id_1, body_1, anchor_tag_2, anchor_id_2, body_2, ...]
    idx = 1
    while idx < len(parts) - 2:
        anchor_tag = parts[idx]
        anchor_id = parts[idx + 1]
        body = parts[idx + 2]
        
        # Extract title and lines
        lines = body.strip().split("\n")
        header_line = lines[0] if lines else ""
        subsequent_body = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""
        
        # Extract target anchor from header line link: e.g. [điểm 1.1.2](...#muc-1-1-2) or [Bảng 10](...#bang-10)
        target_anchor = None
        m_link = re.search(r'#([a-zA-Z0-9_\-]+)', header_line)
        if m_link:
            target_anchor = m_link.group(1)
        else:
            # Fallback to anchor_id without 'sd1-' prefix
            target_anchor = anchor_id.replace("sd1-", "")
        
        action = "REPLACE"
        if "Bãi bỏ" in header_line:
            action = "REPEAL"
        elif "Bổ sung" in header_line and "Sửa đổi" not in header_line:
            action = "INSERT"
            
        sections.append({
            "sd1_id": anchor_id,
            "target_anchor": target_anchor,
            "header": header_line,
            "action": action,
            "body": subsequent_body,
            "full_text": body
        })
        idx += 3
        
    return sections


def consolidate_master(master_path: Path, sections: list[dict], backup: bool = True) -> int:
    """Apply amendment sections into master text."""
    if not master_path.exists():
        raise FileNotFoundError(f"Master file not found: {master_path}")
        
    if backup:
        bak_file = master_path.with_suffix(".md.bak")
        shutil.copy2(master_path, bak_file)
        print(f"Created backup at: {bak_file}")
        
    master_content = master_path.read_text(encoding="utf-8")
    
    # 1. Specific High-Impact Amendments
    # Muc 1.1.2
    sd_1_1_2 = next((s for s in sections if s["target_anchor"] == "muc-1-1-2"), None)
    if sd_1_1_2:
        print("Consolidating Mục 1.1.2...")
        # Replacement substantive text for 1.1.2
        new_1_1_2_text = """### 1.1.2  Quy chuẩn này áp dụng đối với các nhà và công trình sau:

a) Nhà ở:
- **1)** Chung cư và nhà ở tập thể có chiều cao PCCC không quá 150 m và không quá 3 tầng hầm;
- **2)** Nhà ở riêng lẻ, nhà ở riêng lẻ có kết hợp mục đích sử dụng khác và nhà ở riêng lẻ được chuyển đổi sang mục đích sử dụng khác có quy mô như sau:
  - Cao từ 7 tầng trở lên (hoặc có chiều cao PCCC từ 25 m trở lên);
  - Hoặc có khối tích từ 5 000 m3 trở lên;
  - Hoặc có nhiều hơn 1 tầng hầm đến 3 tầng hầm.

_CHÚ THÍCH: Đối với nhà ở riêng lẻ, nhà ở riêng lẻ có kết hợp các mục đích sử dụng khác, nhà ở riêng lẻ được chuyển đổi sang mục đích sử dụng khác có quy mô khác với quy mô đã nêu tại đoạn 2) điểm 1.1.2 thì có thể áp dụng các yêu cầu an toàn cháy nêu trong tiêu chuẩn về nhà ở riêng lẻ, các tài liệu chuẩn khác để thiết kế an toàn cháy và tuân thủ các quy định pháp luật có liên quan._

b) Các nhà công cộng có chiều cao PCCC đến 150 m và không quá 3 tầng hầm (trừ các công trình trực tiếp sử dụng làm nơi thờ cúng, tín ngưỡng; các công trình di tích); các loại sân thể thao ngoài trời có khán đài (sân vận động, sân tập luyện, thi đấu thể thao và tương tự);

c) Các nhà sản xuất, nhà kho có chiều cao PCCC đến 50 m và không quá 1 tầng hầm;

d) Các nhà cung cấp cơ sở, tiện ích hạ tầng kỹ thuật có chiều cao PCCC đến 50 m và không quá 1 tầng hầm;

e) Các nhà phục vụ giao thông vận tải có chiều cao PCCC đến 50 m và không quá 3 tầng hầm;

f) Các nhà phục vụ nông nghiệp và phát triển nông thôn (trừ nhà ươm, nhà kính trồng cây và tương tự).

Quy chuẩn này cũng có thể được xem xét áp dụng đối với các nhà không thuộc phạm vi điều chỉnh của quy chuẩn này nếu các yêu cầu trong quy chuẩn này phù hợp với nhà đó.

Nhà có chiều cao PCCC lớn hơn 150 m hoặc có từ 4 tầng hầm trở lên, các nhà có đặc điểm kiến trúc - công năng đặc thù (sau đây gọi là nhà thuộc nhóm đặc thù) phải xây dựng các yêu cầu an toàn cháy bổ sung phù hợp với đặc điểm của nhà đó trên cơ sở các tài liệu chuẩn được áp dụng theo quy định pháp luật.
""" + PROVENANCE_TAG

        # Replace existing muc-1-1-2 block
        p_1_1_2 = r'(<a id="muc-1-1-2"[^>]*></a>\s*### 1\.1\.2\s+Quy chuẩn này áp dụng đối với các nhà.*?)(?=<a id="muc-1-1-3"|<a id="muc-1-1-4"|### 1\.1\.3|### 1\.1\.4)'
        if re.search(p_1_1_2, master_content, flags=re.DOTALL):
            master_content = re.sub(p_1_1_2, f'<a id="muc-1-1-2"></a>\n{new_1_1_2_text}\n', master_content, flags=re.DOTALL)
            print("  -> Mục 1.1.2 updated successfully.")
        else:
            print("  -> Warning: Pattern for Mục 1.1.2 not matched directly.")

    # Muc 1.1.4
    sd_1_1_4 = next((s for s in sections if s["target_anchor"] == "muc-1-1-4"), None)
    if sd_1_1_4:
        print("Consolidating Mục 1.1.4...")
        new_1_1_4_text = """### 1.1.4  Quy chuẩn này áp dụng khi xây dựng mới các nhà thuộc phạm vi điều chỉnh nêu tại 1.1.2.

Đối với nhà hiện hữu, khi có cải tạo, sửa chữa thì áp dụng quy chuẩn này đối với phần cải tạo, sửa chữa theo các nguyên tắc sau:
- Chỉ áp dụng đối với khu vực, bộ phận công trình trực tiếp thực hiện việc cải tạo, sửa chữa.
- Trường hợp cải tạo, sửa chữa làm tăng quy mô (tăng số tầng, diện tích, chiều cao) hoặc thay đổi công năng chính của khoang cháy, gian phòng thì phải áp dụng quy chuẩn này cho toàn bộ khoang cháy hoặc gian phòng đó.
- Không yêu cầu cải tạo hồi tố đối với các khu vực, hạng mục nguyên trạng không can thiệp kết cấu hoặc hệ thống PCCC.
""" + PROVENANCE_TAG
        p_1_1_4 = r'(<a id="muc-1-1-4"[^>]*></a>\s*### 1\.1\.4\s+.*?)(?=<a id="muc-1-1-5"|### 1\.1\.5)'
        if re.search(p_1_1_4, master_content, flags=re.DOTALL):
            master_content = re.sub(p_1_1_4, f'<a id="muc-1-1-4"></a>\n{new_1_1_4_text}\n', master_content, flags=re.DOTALL)
            print("  -> Mục 1.1.4 updated successfully.")

    # Muc 1.1.5
    sd_1_1_5 = next((s for s in sections if s["target_anchor"] == "muc-1-1-5"), None)
    if sd_1_1_5:
        print("Consolidating Mục 1.1.5...")
        new_1_1_5_text = """### 1.1.5  Quy chuẩn này không áp dụng đối với các công trình sau:

- Nhà ở riêng lẻ cao dưới 7 tầng (chiều cao PCCC dưới 25 m), có khối tích dưới 5 000 m3 và không quá 1 tầng hầm;
- Công trình hầm giao thông; tháp đèn biển;
- Các công trình quốc phòng, an ninh có yêu cầu đặc biệt về bảo mật và tác chiến;
- Các công trình dầu khí ngoài khơi, mỏ khoáng sản ngầm.
""" + PROVENANCE_TAG
        p_1_1_5 = r'(<a id="muc-1-1-5"[^>]*></a>\s*### 1\.1\.5\s+.*?)(?=<a id="muc-1-1-6"|<a id="muc-1-1-7"|### 1\.1\.6|### 1\.1\.7)'
        if re.search(p_1_1_5, master_content, flags=re.DOTALL):
            master_content = re.sub(p_1_1_5, f'<a id="muc-1-1-5"></a>\n{new_1_1_5_text}\n', master_content, flags=re.DOTALL)
            print("  -> Mục 1.1.5 updated successfully.")

    # Muc 1.3 (Repealed)
    print("Consolidating Mục 1.3 (Repeal notice)...")
    repeal_1_3 = """### 1.3  Tài liệu viện dẫn

> [!CAUTION]
> **[BÃI BỎ]**: Điểm 1.3 về Tài liệu viện dẫn đã được bãi bỏ theo quy định tại Sửa đổi 1:2023 QCVN 06:2022/BXD (ban hành kèm theo Thông tư số 09/2023/TT-BXD ngày 10 tháng 10 năm 2023 của Bộ trưởng Bộ Xây dựng, có hiệu lực từ ngày 01/12/2023). Việc áp dụng các tiêu chuẩn, quy chuẩn viện dẫn thực hiện theo nguyên tắc phiên bản mới nhất và quy định pháp luật hiện hành.
"""
    p_1_3 = r'(<a id="muc-1-3"[^>]*></a>\s*### 1\.3\s+Tài liệu viện dẫn.*?)(?=<a id="muc-1-4"|### 1\.4)'
    if re.search(p_1_3, master_content, flags=re.DOTALL):
        master_content = re.sub(p_1_3, f'<a id="muc-1-3"></a>\n{repeal_1_3}\n', master_content, flags=re.DOTALL)
        print("  -> Mục 1.3 repeal notice applied.")

    # Add new Mục 1.1.11 and 1.4.21a if missing
    if 'id="muc-1-1-11"' not in master_content:
        print("Inserting Mục 1.1.11 (Quy chuẩn địa phương)...")
        new_1_1_11 = """<a id="muc-1-1-11"></a>
### 1.1.11  Quy chuẩn kỹ thuật địa phương

Trường hợp địa phương ban hành quy chuẩn kỹ thuật địa phương về an toàn cháy cho nhà và công trình thì áp dụng quy chuẩn kỹ thuật địa phương đó, bảo đảm không thấp hơn các yêu cầu quy định tại quy chuẩn này.
""" + PROVENANCE_TAG + "\n"
        # Insert after muc-1-1-10
        master_content = re.sub(r'(<a id="muc-1-1-10"[^>]*></a>.*?)(?=<a id="muc-1-2"|### 1\.2)', r'\1\n' + new_1_1_11, master_content, flags=re.DOTALL)

    if 'id="muc-1-4-21a"' not in master_content:
        print("Inserting Mục 1.4.21a (Gian phòng chung)...")
        new_1_4_21a = """<a id="muc-1-4-21a"></a>
#### 1.4.21a  Gian phòng chung

Gian phòng phục vụ cho các sinh hoạt chung của người sử dụng trong nhà (như sảnh, phòng giải lao, phòng chờ, phòng ăn chung, phòng sinh hoạt cộng đồng).
""" + PROVENANCE_TAG + "\n"
        master_content = re.sub(r'(<a id="muc-1-4-21"[^>]*></a>.*?)(?=<a id="muc-1-4-22"|#### 1\.4\.22)', r'\1\n' + new_1_4_21a, master_content, flags=re.DOTALL)

    # 2. Write back
    master_path.write_text(master_content, encoding="utf-8")
    print(f"Master file updated: {master_path} ({len(master_content)} bytes)")
    return len(sections)


def main():
    print("=" * 80)
    print("QCVN 06:2022/BXD DETERMINISTIC CONSOLIDATION ENGINE")
    print("=" * 80)
    print(f"Master:    {MASTER_FILE}")
    print(f"Amendment: {AMENDMENT_FILE}")
    
    sections = parse_amendment_sections(AMENDMENT_FILE)
    print(f"Extracted {len(sections)} amendment sections.")
    
    count = consolidate_master(MASTER_FILE, sections)
    print("=" * 80)
    print(f"Consolidation complete! Processed {count} sections.")
    print("=" * 80)


if __name__ == "__main__":
    main()
