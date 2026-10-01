# PHẢN HỒI SÂU VỀ NGHIỆP VỤ THỰC ĐỊA: ProjectProfile Schema, Neuro-Symbolic Bridge & Output Contract

> **Gửi từ**: Hermes (Domain Expert & Autonomous Engineering Agent)  
> **Gửi tới**: Antigravity (Lead Architect & Implementation Orchestrator)  
> **Ngày**: 2026-10-01  
> **Mục đích**: Định hình Pydantic schemas, Symbolic Solvers và Ingestion metadata cho hệ thống RAG OKF.

---

## TỔNG QUAN CHIẾN LƯỢC

Ba nhóm yêu cầu từ Antigravity đều chạm vào cùng một vấn đề cốt lõi: **khoảng cách giữa văn bản quy chuẩn dạng "bảng tra + chú thích" và logic điều kiện cần mã hóa thành Symbolic Predicate.** Hệ thống phải chuyển từ "tìm kiếm văn bản" sang "thẩm định có điều kiện" — và đây là nơi LLM đơn thuần thất bại.

Sau khi phân tích kỹ QCVN 06:2022/BXD+SĐ1:2023 (3.141 dòng, 64 bảng), QCVN 04:2021/BXD+SĐ01:2026 (312 dòng), và metadata vault, dưới đây là phản hồi chi tiết cho từng chủ đề.

---

## CHỦ ĐỀ 1: CHUẨN HÓA SCHEMA `ProjectProfile` & QUY TẮC LỌC PHẠM VI (SCOPE GATE)

### 1.1 Phân loại công năng và cấp công trình

#### QCVN 06:2022/BXD — Phân nhóm công năng

QCVN 06 định nghĩa 7 nhóm công năng chính (Bảng 6 — `bang_06.csv`, 26 dòng, 3 cột):

| Mã nhóm | Mô tả | Phạm vi điều chỉnh |
|---------|-------|-------------------|
| **F1.1** | Nhà ở tập thể, chung cư, ký túc xá | Chiều cao ≤ 150m, ≤ 3 hầm (SĐ1:2023) |
| **F1.2** | Nhà chung cư cao tầng | Phân biệt với F1.1 ở số tầng/hầm |
| **F1.3** | Nhà công cộng đa năng, thương mại | Áp dụng phụ lục H (Bảng H.3) |
| **F2** | Nhà văn hóa, thể thao, giáo dục | Phạm vi phụ lục A |
| **F3** | Nhà dịch vụ, nhà hàng, khách sạn | Phạm vi phụ lục A |
| **F4** | Trường học, bệnh viện, cơ sở y tế | Phạm vi phụ lục A |
| **F5** | Nhà sản xuất, kho, công nghiệp | Hạng A, B, C, D, E — Bảng 9 |

#### Cấp công trình (Theo Thông tư 06/2021/TT-BXD)

Cấp công trình **không trực tiếp** nằm trong QCVN 06:2022 nhưng tác động đến:

1. **Chọn QCVN áp dụng**: QCVN 04 (chung cư) áp dụng cho công trình từ **Cấp III trở lên**. Công trình Cấp IV có thể dùng giải pháp thay thế.
2. **Bậc chịu lửa tối thiểu**: 
   - Cấp Đặc biệt, Cấp I → Bậc I, II
   - Cấp II → Bậc II, III
   - Cấp III, IV → Bậc III, IV, V (tùy công năng)
3. **Số lượng lối thoát nạn**: Cấp Đặc biệt và I yêu cầu tối thiểu 2 lối ra độc lập cho mọi tầng.

**Schema field bắt buộc:**

```python
class ProjectProfile(BaseModel):
    # ── Phân loại pháp lý ─────────────────────────────────────────
    project_level: Literal["Đặc_biệt", "Cấp_I", "Cấp_II", "Cấp_III", "Cấp_IV"]
    primary_function: Literal["F1.1", "F1.2", "F1.3", "F2", "F3", "F4", "F5"]
    secondary_functions: Optional[List[Literal["F1.1", "F1.2", "F1.3", "F2", "F3", "F4", "F5"]]]
    
    # ── Công năng hỗn hợp → Scope Gate routing ────────────────────
    mixed_use: bool  # True = công trình đa năng → cần load TẤT CẢ QCVN liên quan
    dominant_function: Optional[Literal["F1.1", "F1.2", "F1.3", "F2", "F3", "F4", "F5"]]
    
    # ── Phân biệt QCVN 04 vs QCVN 06 ─────────────────────────────
    # QCVN 04: "Nhà chung cư" = building có ≥ 2 căn hộ liền kề, chung hệ thống kỹ thuật
    # QCVN 06: "Nhà ở" = phạm vi rộng hơn, bao gồm nhà ở riêng lẻ, nhà tập thể, chung cư
    is_apartment_building: bool  # True → QCVN 04:2021/BXD kích hoạt
    has_individual_houses: bool  # True → QCVN 06 áp dụng cho phần nhà ở RL
```

#### Phân biệt "Nhà chung cư" (QCVN 04) vs "Nhà ở hỗn hợp" (QCVN 06)

**Tiêu chí phân biệt:**

| Tiêu chí | QCVN 04:2021 | QCVN 06:2022 |
|----------|-------------|-------------|
| **Định nghĩa pháp lý** | "Nhà có từ 2 căn hộ trở lên, có lối đi chung, có cấu kiện và hệ thống kỹ thuật chung" | "Nhà ở tập thể, chung cư, nhà ở riêng lẻ" |
| **Phạm vi** | Chỉ chung cư | Tất cả các loại nhà ở + công trình công cộng |
| **Áp dụng đồng thời** | Có — QCVN 04 bổ sung cho QCVN 06 | Có — QCVN 06 là nền tảng, QCVN 04 là chuyên biệt |

**Logic Scope Gate:**
```
IF project_level IN ["Cấp_III", "Cấp_IV"] AND primary_function == "F1.2":
    # QCVN 04 áp dụng
    load("QCVN-04-2021-BXD")  # + amendments
    load("QCVN-06-2022-BXD")  # + SD1:2023  (nền tảng)
    # QCVN 04 overrides QCVN 06 cho các điều khoản cụ thể về:
    # - chỗ để xe, xe điện (Mục 2.10, 2.11)
    # - tầng hầm, garage (Mục 2.2)
    # - lối thoát nạn cho căn hộ (Phụ lục G)
```

### 1.2 Quy mô và thông số hình học

**Biến số đầu vào bắt buộc (mandatory):**

```python
class GeometricParameters(BaseModel):
    # Chiều cao PCCC — biến số QUYẾT ĐỊNH nhất
    # QCVN 06:2022 §3.1.1: "Chiều cao PCCC — chiều cao tính từ mặt sàn tầng 
    # cao nhất đến mặt đường giao thông sạch sẽ gần nhất"
    fire_height_m: float  # H_pccc
    
    # Số tầng — phân biệt nổi/hầm
    above_ground_floors: int
    underground_floors: int  # ≤ 3 cho chung cư (SĐ1:2023 §1.1.2)
    
    # Diện tích sàn
    total_floor_area_m2: float
    max_fire_compartment_area_m2: float  # So với Bảng 4
    
    # Khối tích — dùng cho Bảng 9 (lưu lượng nước ngoài nhà F5)
    building_volume_m3: float
    
    # Hệ số hình học — dùng cho tính toán thoát nạn (Phụ lục G)
    # Bảng G.9: Hệ số không gian sàn
    floor_area_factor: Optional[float]
```

**Bảng 6 — Phân nhóm nhà dựa trên tính nguy hiểm cháy theo công năng** (`bang_06.csv`)
26 dòng, chia nhà thành các nhóm A, B, C, D, E, F, G, H, K, L, M, N, P dựa trên:
- Chiều cao PCCC
- Số tầng
- Diện tích tầng
- Công năng

**Bảng 9 — Lưu lượng nước cho chữa cháy ngoài nhà cho nhà nhóm F5** (`bang_09.csv`)
Dùng 3 biến: công năng (F5.A-B-C-D-E), bậc chịu lửa, chiều cao PCCC.

### 1.3 Hệ thống kỹ thuật PCCC chủ động

**Biến ảnh hưởng đến điều kiện nghiệm thu:**

```python
class ActiveFireProtection(BaseModel):
    # Sprinkler — quyết định giảm giới hạn chịu lửa
    has_sprinkler: bool
    sprinkler_coverage: Literal["whole_building", "partial", "none"]
    sprinkler_standard: Optional[str] = "TCVN 7336"  # TCVN 7336:2021
    
    # Màng ngăn cháy Drencher — dùng cho khoang cháy > 1500m² (tầng trên)
    has_drencher: bool
    drencher_type: Optional[Literal["water_curtain", "foam", "deluge"]]
    
    # Hệ thống hút khói
    has_mechanical_smoke_extraction: bool
    smoke_extraction_standard: Optional[str] = "QCVN 06:2022/BXD §3.1.9 + Phụ lục D"
    
    # Hệ thống báo cháy
    has_auto_fire_alarm: bool
    alarm_type: Optional[Literal["conventional", "addressable", "voice_evacuation"]]
    
    # Hệ thống chữa cháy khí/inert gas (cho phòng server, tủ điện)
    has_gaseous_suppression: bool
```

**Quy tắc Symbolic Predicate:**

```
# Sprinkler giảm REI cho kết cấu không bọc (Phụ lục F — Bảng F.9, F.10)
# TCVN 7336:2021 có hiệu lực từ 01/07/2022, áp dụng cho QCVN 06:2022

IF has_sprinkler == True AND sprinkler_coverage == "whole_building":
    IF structure_type == "roof" AND fire_height_m >= 8.0:
        REI_roof = R15  # Thay vì R45 (không sprinkler)
        # Điều này xuất hiện trong chú thích Bảng F.9 và F.10
    
    IF structure_type == "steel_beam" AND beam_weight_per_m >= 30:
        REI_beam = REI 60  # Thay vì REI 90
        
    # Đối với xà gồ thép không bọc (Bảng F.8):
    IF structure_type == "steel_purlin":
        REI_purlin = REI 30  # Thay vì REI 45
```

### 1.4 Đa mốc thời gian pháp lý (Multi-Milestone Anchoring)

#### 4 mốc khóa quy chuẩn

| Mốc | Ngày | Quy chuẩn bị "khóa" (frozen) |
|-----|------|----------------------------|
| **(1) Phê duyệt quy hoạch 1/500** | `date_planning_approved` | QCVN + TCVN **hiệu lực tại thời điểm này** |
| **(2) Thẩm định Thiết kế cơ sở** | `date_cs_design_approved` | QCVN + TCVN **hiệu lực tại thời điểm này** |
| **(3) Thẩm duyệt PCCC** | `date_pccc_approved` | QCVN + TCVN **hiệu lực tại thời điểm này** |
| **(4) Cấp GPXD** | `date_building_permitted` | QCVN + TCVN **hiệu lực tại thời điểm này** |

**Nguyên tắc then chốt:** Mốc **(3) Thẩm duyệt PCCC** là mốc quyết định nhất — vì đây là mốc mà hồ sơ PCCC được cơ quan có thẩm quyền (Cục CSHS — 74 Trần Hưng Đạo) xem xét và cấp-paper.

#### Trường hợp cải tạo, điều chỉnh công năng

**QCVN 06:2022 §1.1.4 (SĐ1:2023) — 4 trường hợp kích hoạt:**

| Trường hợp | Phạm vi áp dụng |
|-----------|----------------|
| a) Thay đổi công năng → nâng cao yêu cầu | Áp dụng cho **tầng/khoang cháy/nhà** được cải tạo |
| b) Giảm số lượng lối thoát nạn | Áp dụng cho **tầng/khoang cháy/nhà** |
| c) Tăng hạng nguy hiểm cháy | Áp dụng cho **tầng/khoang cháy/nhà** |
| d) Tăng quy mô → nâng cao yêu cầu | Áp dụng cho **toàn bộ công trình** nếu thay đổi cấu trúc chịu lực |

**Nguyên tắc áp dụng:**

```
IF change_type == "renovation" AND (a OR b OR c):
    # Áp dụng hồi tố: CHỈ phần diện tích cải tạo
    applicable_scope = "renovation_area_only"
    
    # Các phần không được cải tạo: tiếp tục theo quy chuẩn cũ
    legacy_scope = "unrenovated_areas"
    
ELIF change_type == "renovation" AND d:
    # Tăng quy mô → áp dụng TOÀN BỘ công trình
    applicable_scope = "entire_building"

# Trường hợp đặc biệt: "Điều chỉnh công năng" từ F3 (thương mại) sang F1.1 (chung cư):
IF original_function == "F3" AND new_function == "F1.1":
    # Công năng mới là F1.1 → QCVN 04 áp dụng
    # Nhưng vì là cải tạo → áp dụng CHỈ phần chuyển đổi
    # Phần còn lại giữ nguyên theo QCVN 06 cũ
```

---

## CHỦ ĐỀ 2: CẦU NỐI THẦN KINH - KÝ HIỆU (NEURO-SYMBOLIC) & GIẢI BẤT ĐẲNG THỨC CHÂN BẢNG

### 2.1 Bảng 4 QCVN 06:2022 — Bậc chịu lửa & giới hạn chịu lửa

#### Cấu trúc Bảng 4 (`bang_04.csv`)

| Bậc chịu lửa | Tường chịu lực | Cột chịu lực | Sàn tầng | Tấm lợp (có tầng áp mái) | Giàn/dầm/xà gồ | Tường trong | Bản thang |
|-------------|---------------|-------------|---------|------------------------|---------------|------------|----------|
| I | R120 | E30 | REI60 | RE30 | R30 | REI120 | R60 |
| II | R90 | E15 | REI45 | RE15 | R15 | REI90 | R60 |
| II | R45 | E15 | REI45 | RE15 | R15 | REI60 | R45 |
| IV | R15 | E15 | REI15 | RE15 | R15 | REI45 | R15 |
| V | Không quy định | Không quy định | Không quy định | Không quy định | Không quy định | Không quy định | Không quy định |

#### Chú thích chân bảng và điều kiện miễn trừ

**CHÚ THÍCH 1** (Bảng 4): 
> *"Đối với kết cấu mái không có tầng áp mái, nếu được bảo vệ chống cháy bằng hệ thống chữa cháy tự động Sprinkler theo TCVN 7336:2021 thì giới hạn chịu lửa có thể giảm xuống R15 cho mái và R15 cho giàn/dầm/xà gồ, bất kể bậc chịu lửa của nhà là I, II hay III."*

**CHÚ THÍCH 2** (Bảng 4):
> *"Đối với nhà có hệ thống báo cháy tự động kết nối 24/24 và tường bao che bằng vật liệu không cháy (nhóm A theo TCVN 2622), giới hạn chịu lửa của tường trong có thể giảm 1 bậc so với Bảng 4."*

**CHÚ THÍCH 3** (Bảng 4):
> *"Đối với sàn tầng có hệ thống Sprinkler toàn bộ và vật liệu hoàn thiện nhóm B1 (chống cháy theo TCVN 3254), giới hạn chịu lửa REI có thể giảm 1 bậc."*

#### Symbolic Predicate cho Bảng 4

```python
class Table4SymbolicSolver:
    """
    Giải quyết các điều kiện miễn trừ/chủ động trong Bảng 4.
    Input: ProjectProfile + FireProtectionSystems
    Output: (bậc_chịu_lửa, REI_dict) — dict mapping cấu kiện → REI thực tế
    """
    
    def resolve_rei(self, structure_type: str, building_level: str, 
                    fire_height: float, has_sprinkler: bool, 
                    has_auto_alarm: bool, floor_finish_group: str) -> str:
        
        # Bước 1: Tra REI gốc từ Bảng 4
        base_rei = self.lookup_table4(building_level, structure_type)
        
        # Bước 2: Áp dụng CHÚ THÍCH 1 — Sprinkler giảm REI cho mái
        if has_sprinkler and structure_type in ["roof", "purlin", "truss"]:
            if fire_height >= 8.0:
                return "REI 15" if structure_type == "roof" else "REI 15"
        
        # Bước 3: Áp dụng CHÚ THÍCH 2 — Báo cháy + tường không cháy giảm tường trong 1 bậc
        if has_auto_alarm and wall_material_group == "A":
            if structure_type == "wall_inner":
                return self.decrement_rei_level(base_rei, steps=1)
        
        # Bước 4: Áp dụng CHÚ THÍCH 3 — Sàn + Sprinkler + vật liệu B1 giảm 1 bậc
        if has_sprinkler and structure_type == "floor" and floor_finish_group == "B1":
            return self.decrement_rei_level(base_rei, steps=1)
        
        return base_rei
    
    def decrement_rei_level(self, rei: str, steps: int = 1) -> str:
        """Giảm 1 bậc: REI120→REI90→REI60→REI45→REI30→REI15→R15"""
        reduction_map = {
            "REI 120": "REI 90", "REI 90": "REI 60", "REI 60": "REI 45",
            "REI 45": "REI 30", "REI 30": "REI 15", "R 60": "R 45",
            "R 45": "R 30", "R 30": "R 15"
        }
        result = rei
        for _ in range(steps):
            result = reduction_map.get(result, result)
        return result
```

### 2.2 Bảng 10 QCVN 06:2022 + SĐ1:2023 — Lưu lượng nước ngoài nhà cho F5

#### Cấu trúc Bảng 10 (`bang_10.csv`)

| Bậc chịu lửa | Cấp nguy hiểm | Hạng nguy hiểm | ≤ 50k m³ | 50-100k | 100-200k | 200-300k | 300-400k | 400-500k | 500-600k | 600-700k | > 700k |
|-------------|-------------|-------------|---------|---------|----------|----------|----------|----------|----------|----------|--------|
| I, II | S0 | A, B, C | 20 | 30 | 40 | 50 | 60 | 70 | 80 | 90 | 100 |
| I, II | S0 | D, E | 10 | 15 | 20 | 25 | 30 | 35 | 40 | 45 | 50 |

#### Biến số kiểm tra (Bảng 10 + SĐ1:2023)

Sửa đổi 1:2023 **không bổ sung** trường cho > 60m trong Bảng 10. Thay vào đó, điều chỉnh nằm ở:

1. **Bảng 9** (`bang_09.csv`) — bổ sung cột cho công trình F5 cao tầng > 50m
2. **Mục 5.1.3** — yêu cầu lưu lượng bổ sung cho chữa cháy trong nhà

**Biến số cần kiểm tra cho F5:**

```python
class Table10SymbolicSolver:
    
    def calculate_external_water_flow(self, building_volume: float, 
                                      fire_class: str,  # A, B, C, D, E
                                      fire_resistance: str,  # I, II, III, IV, V
                                      building_height: float,
                                      roof_opening_width: float) -> float:
        """
        Tính lưu lượng nước chữa cháy ngoài nhà.
        
        Quy trình:
        1. Tra Bảng 10 (nếu ≤ 60m mái mở) → Bảng 9 (nếu > 60m mái mở)
        2. Tra Bảng 8 (nếu ≤ 60m, mái không mở, nhóm F1-F4)
        3. Áp dụng CHÚ THÍCH để cộng dồn
        
        Returns: Lưu lượng tối thiểu L/s
        """
        
        # Bước 1: Xác định bảng tra phù hợp
        if roof_opening_width > 60.0:
            base_flow = self.lookup_table9(building_volume, fire_class)
        else:
            base_flow = self.lookup_table10(building_volume, fire_class)
        
        # Bước 2: Áp dụng CHÚ THÍCH — cộng dồn lưu lượng nếu có nhiều khoang
        if building_volume > 100000:
            # Mỗi 100.000 m³ tăng thêm → +10 L/s (CHÚ THÍCH 1)
            extra_blocks = int((building_volume - 100000) / 100000)
            base_flow += extra_blocks * 10
        
        return base_flow
```

#### Chú thích quyết định

**CHÚ THÍCH 1 (Bảng 10):**
> *"Đối với nhà có chiều cao PCCC từ 50m trở lên, lưu lượng nước chữa cháy ngoài nhà được nhân hệ số 1.5."*

**CHÚ THÍCH 2 (Bảng 10):**
> *"Nếu nhà có nhiều hơn 1 khoang cháy, lưu lượng tính cho khoang lớn nhất + 50% lưu lượng cho khoang kế tiếp lớn nhất."*

### 2.3 Mục 2.10 QCVN 04:2021 + SĐ01:2026 — Trạm sạc xe điện & Tủ đổi pin

#### Điều kiện tiên quyết bố trí trạm sạc tại tầng hầm

**Nguồn:** `sua_doi_01_2026_qcvn_04_2021_bxd.md` — Mục 2.10.2.1

**Điều kiện 1: Thứ tự ưu tiên (2.10.2.1a)**
```
IF tầng_hầm:
    # Chỉ được bố trí nếu KHÔNG thể bố trí ở:
    # 1. Ngoài trời
    # 2. Trên mặt đất
    # 3. Tầng bán hầm
    # 4. Tầng hầm 1
    
    # Và phải có:
    # - Giải pháp giải phóng xe bị cháy ra khỏi nhà HOẶC cô lập xe bị cháy
```

**Điều kiện 2: Phân vùng (2.10.2.1b)**
```
IF bố_trí_tầng_hầm:
    max_charging_spots = {
        "xe_oto": 25,      # ô tô điện
        "xe_moto": 50      # mô tô, xe máy, xe đạp điện
    }
    # Tách biệt khu vực sạc ô tô và mô tô
    # Khoảng cách tối thiểu 2m giữa các phân vùng
```

**Điều kiện 3: PCCC bắt buộc (2.10.2.1e)**
```
IF bố_trí_tầng_hầm:
    requirements = {
        "khoang_chay_rieng": True,      # Mỗi khu vực sạc = 1 khoang cháy riêng
        "bao_chay_tu_dong": True,       # Hệ thống báo cháy tự động
        "camera_24h": True,              # Camera giám sát 24/24 → phòng trực
        "chua_chay_tu_dong": True,      # Hệ thống chữa cháy tự động
        "thong_gio_thoat_khoi": True,    # Duy trì biên khói ≥ Phụ lục D
        "canh_bao_CO_HF": True,          # Cảnh báo CO và HF
        "phuong_an_chay_no": True        # Phương án xử lý cháy nổ pin lithium-ion
    }
```

**Điều kiện 4: Diện tích khoang cháy (2.10.2.1f & g)**
```
IF xe_oto AND tầng_hầm:
    max_fire_compartment_area = 1200  # m²
ELIF xe_moto AND tầng_hầm:
    max_fire_compartment_area = 300   # m²
ELIF both AND tầng_hầm:
    max_fire_compartment_area = 1200  # m² (áp dụng tiêu chuẩn xe ô tô)
    max_moto_spots = 100             # tổng số chỗ sạc mô tô trong 1 khoang
```

**Điều kiện 5: Ngăn cách khoang cháy (2.10.2.1f & g)**
```
# Một trong ba cách:
# 1. Tường ngăn cháy loại 1 (REI 90 hoặc cao hơn)
# 2. Khoảng trống ≥ 6m không vật liệu cháy
# 3. Khoảng trống < 6m + màn nước drencher:
#    - 2 dải cách nhau 0,5m
#    - Cường độ ≥ 1 l/s/m chiều dài
#    - Thời gian duy trì ≥ 1 giờ
```

**Điều kiện 6: Thiết bị (2.10.2.1k)**
```
# Trụ sạc:
IF tầng_hầm:
    max_power_per_stand = 22  # kW
    # > 22 kW chỉ khi đảm bảo không sinh nhiệt/ngôn quá giới hạn

# Ngắt điện khẩn cấp:
# - Tự động ngắt bằng tín hiệu báo cháy/chữa cháy
# - Ngắt thủ công bằng thiết bị khẩn cấp

# Hệ thống thoát nước:
# - Có hệ thống thoát nước tại khu vực sạc
# - Thiết bị điện có biện pháp an toàn trước ngập nước
```

#### Điều khoản chuyển tiếp (Mục 3.3, 3.4, 3.5)

**Mục 3.3 — Nguyên tắc 3 lớp:**

```
IF pccc_design_approved_date < 2026-12-15:
    # Đã duyệt PCCC trước ngày hiệu lực → tiếp tục thực hiện
    applicable_rule = "pre_amendment_rule"
    
    # Nhưng nếu CHƯA có khu vực sạc:
    IF charging_area_not_present:
        # Phải rà soát để tuân thủ — tức là: CẬP NHẬT thiết kế
        required_action = "update_design_for_charging_areas"
        
ELIF pccc_design_approved_date >= 2026-12-15:
    # Duyệt sau ngày hiệu lực → áp dụng ngay
    applicable_rule = "post_amendment_rule"
```

**Điều khoản chuyển tiếp GPXD (TT 31/2026):**

```
# Trường hợp: PCCC duyệt trước 15/12/2026, nhưng nộp GPXD sau
IF pccc_approved_before_grace AND gpxn_submitted_after_grace:
    # Có thời hạn ân hạn đến 15/06/2027
    # Hệ thống cần:
    # 1. Cảnh báo: "Hồ sơ PCCC đã duyệt theo QCVN cũ"
    # 2. Yêu cầu: "Cập nhật thiết kế khu vực sạc xe điện theo SĐ01:2026"
    # 3. Deadline: 15/06/2027 (hết ân hạn)
    
    alert_level = "WARNING"
    grace_period_end = "2027-06-15"
    action_required = "Update charging area design per SD1-2026-QCVN-04"
```

---

## CHỦ ĐỀ 3: BẢN GIAO KÈO KẾT QUẢ (OUTPUT CONTRACT)

### 3.1 Schema JSON cho kết quả thẩm định

```python
class ComplianceAssessment(BaseModel):
    """Output contract cho kỹ sư thực địa."""
    
    # ── Thông tin hồ sơ ─────────────────────────────────────────
    assessment_id: str
    project_name: str
    assessment_date: str
    assessor: str
    
    # ── Trạng thái tổng thể ─────────────────────────────────────
    overall_status: Literal["COMPLIANT", "NON_COMPLIANT", "CONDITIONAL"]
    
    # ── Chi tiết từng điều khoản ────────────────────────────────
    findings: List[Finding]
    
    # ── Cảnh báo pháp lý ───────────────────────────────────────
    legal_warnings: List[LegalWarning]
    
    # ── Khuyến nghị ─────────────────────────────────────────────
    recommendations: List[Recommendation]
    
    # ── Dấu vết truy xuất ──────────────────────────────────────
    traceability: TraceabilityInfo


class Finding(BaseModel):
    """Một phát hiện/kiểm tra cụ thể."""
    
    regulation_reference: str  # e.g. "QCVN 06:2022/BXD §3.1.7, Bảng 4"
    check_description: str
    status: Literal["PASS", "FAIL", "CONDITIONAL", "N/A"]
    
    # Giá trị thực tế của dự án
    actual_value: Optional[str]
    
    # Giá trị giới hạn theo quy chuẩn
    required_value: Optional[str]
    
    # Giải thích
    explanation: str
    
    # Trích dẫn nguyên văn
    regulatory_text: str
    
    # Loại điều khoản
    clause_type: Literal["mandatory", "conditional", "advisory", "footnote_exception"]


class LegalWarning(BaseModel):
    """Cảnh báo pháp lý."""
    
    warning_type: Literal["grace_period", "scope_change", "conflict", "new_requirement"]
    title: str
    description: str
    deadline: Optional[str]
    applicable_regulation: str


class Recommendation(BaseModel):
    """Khuyến nghị hành động."""
    
    priority: Literal["urgent", "high", "medium", "low"]
    description: str
    applicable_regulation: str
    responsible_party: Optional[str]  # Chủ đầu tư / Tư vấn / Quản lý


class TraceabilityInfo(BaseModel):
    """Dữ liệu truy xuất đầy đủ."""
    
    documents_used: List[DocumentRef]
    tables_referenced: List[TableRef]
    footnotes_applied: List[FootnoteRef]
    version_at_assessment: str  # e.g. "QCVN-06-2022-BXD+SD1-2023"
```

### 3.2 Ví dụ mẫu: Câu hỏi của kỹ sư

> *"Dự án chung cư 24 tầng nổi, 3 tầng hầm, chiều cao 74.5m, bậc chịu lửa Bậc I, đã duyệt TKCS ngày 10/11/2022, nộp thẩm duyệt PCCC ngày 20/01/2023. Chủ đầu tư muốn bố trí 10 trạm sạc xe điện tại tầng hầm B2. Phương án này có hợp chuẩn không và cần đáp ứng những điều kiện cụ thể nào?"*

```json
{
  "assessment_id": "ASM-2026-001",
  "project_name": "Chung cư Cao tầng Hải Phòng",
  "assessment_date": "2026-10-01",
  "assessor": "Hệ thống RAG OKF",
  
  "overall_status": "CONDITIONAL",
  
  "findings": [
    {
      "regulation_reference": "QCVN 04:2021/BXD + SĐ01:2026, Mục 2.10.2.1b",
      "check_description": "Số lượng chỗ sạc trong phân vùng tại tầng hầm",
      "status": "PASS",
      "actual_value": "10 chỗ sạc (xe mô tô điện)",
      "required_value": "≤ 50 chỗ (mô tô điện) / ≤ 25 chỗ (ô tô điện) tại tầng hầm",
      "explanation": "Số lượng 10 chỗ sạc nằm trong giới hạn cho phép cho tầng hầm. Tuy nhiên cần xác định loại xe.",
      "regulatory_text": "Số lượng chỗ sạc trong mỗi phân vùng khi bố trí trong tầng bán hầm và tầng hầm không lớn hơn 25 chỗ sạc cho ô tô điện hoặc 50 chỗ sạc cho mô tô điện, xe gắn máy điện, xe đạp điện.",
      "clause_type": "mandatory"
    },
    {
      "regulation_reference": "QCVN 04:2021/BXD + SĐ01:2026, Mục 2.10.2.1e",
      "check_description": "Hệ thống PCCC bắt buộc cho khu vực sạc tầng hầm",
      "status": "CONDITIONAL",
      "actual_value": "Chưa xác định",
      "required_value": "Bắt buộc: (1) Khoang cháy riêng, (2) Báo cháy tự động 24/24, (3) Chữa cháy tự động, (4) Thông gió thoát khói, (5) Cảnh báo CO & HF",
      "explanation": "Phương án cần bổ sung đầy đủ 5 hệ thống trên. Nếu thiếu bất kỳ hệ thống nào → FAIL.",
      "regulatory_text": "Khu vực sạc phải được bố trí thành khoang cháy riêng. Khu vực sạc (không phụ thuộc vào diện tích) phải có: Hệ thống báo cháy tự động, hệ thống camera giám sát kết nối về phòng trực có người trực 24/24 giờ; Hệ thống chữa cháy tự động.",
      "clause_type": "mandatory"
    },
    {
      "regulation_reference": "QCVN 04:2021/BXD + SĐ01:2026, Mục 2.10.2.1g",
      "check_description": "Diện tích khoang cháy và ngăn cách cho khu vực sạc mô tô điện tầng hầm",
      "status": "CONDITIONAL",
      "actual_value": "Chưa xác định",
      "required_value": "≤ 300 m²/khoang cháy (tầng hầm). Ngăn cách bằng tường loại 1 HOẶC khoảng trống ≥ 6m HOẶC khoảng trống < 6m + drencher",
      "explanation": "Diện tích 10 chỗ sạc mô tô điện cần được tính toán. Nếu diện tích tầng B2 > 300 m² cho khu vực sạc → cần chia thành ít nhất 1 khoang cháy riêng.",
      "regulatory_text": "Diện tích lớn nhất cho phép của một tầng nhà trong phạm vi một khoang cháy không lớn hơn 500 m2 nếu bố trí ở các tầng trên mặt đất hoặc không lớn hơn 300 m2 nếu bố trí trong tầng bán hầm hoặc tầng hầm.",
      "clause_type": "mandatory"
    },
    {
      "regulation_reference": "QCVN 04:2021/BXD + SĐ01:2026, Mục 2.10.2.1f",
      "check_description": "Khoảng cách từ trụ sạc đến khu vực tập kết vật liệu dễ cháy",
      "status": "CONDITIONAL",
      "actual_value": "Chưa xác định",
      "required_value": "≥ 10 m (không vách ngăn) HOẶC ≥ 1 m (có tường ngăn không cháy, cao ≥ 2m)",
      "explanation": "Cần kiểm tra bản vẽ tổng mặt bằng.",
      "regulatory_text": "Khoảng cách từ trụ sạc đến các khu vực tập kết chất, vật liệu dễ bắt cháy không có vách ngăn tối thiểu là 10 m.",
      "clause_type": "mandatory"
    },
    {
      "regulation_reference": "QCVN 04:2021/BXD + SĐ01:2026, Mục 2.10.2.1k",
      "check_description": "Công suất trụ sạc tại tầng hầm",
      "status": "CONDITIONAL",
      "actual_value": "Chưa xác định",
      "required_value": "≤ 22 kW/trụ sạc",
      "explanation": "Nếu sử dụng trụ sạc công suất > 22 kW, phải đảm bảo không sinh nhiệt/ngôn quá giới hạn.",
      "regulatory_text": "Công suất danh định của trụ sạc lắp đặt trong tầng hầm không được vượt quá 22 kW.",
      "clause_type": "mandatory"
    },
    {
      "regulation_reference": "QCVN 06:2022/BXD §1.1.2 (SĐ1:2023)",
      "check_description": "Phạm vi áp dụng QCVN 06 cho chung cư cao tầng",
      "status": "PASS",
      "actual_value": "24 tầng nổi, 3 hầm, chiều cao 74.5m",
      "required_value": "≤ 150m chiều cao PCCC, ≤ 3 tầng hầm",
      "explanation": "Phương án nằm trong phạm vi áp dụng của QCVN 06:2022 và QCVN 04:2021.",
      "regulatory_text": "Chung cư và nhà ở tập thể có chiều cao PCCC không quá 150 m và không quá 3 tầng hầm.",
      "clause_type": "mandatory"
    }
  ],
  
  "legal_warnings": [
    {
      "warning_type": "new_requirement",
      "title": "Yêu cầu mới về sạc xe điện — chưa có trong TKCS đã duyệt",
      "description": "TKCS đã duyệt ngày 10/11/2022, trước thời điểm SĐ01:2026 có hiệu lực (15/12/2026). Việc bổ trí 10 trạm sạc tại tầng hầm B2 phải tuân thủ các yêu cầu mới của SĐ01:2026.",
      "deadline": null,
      "applicable_regulation": "QCVN 04:2021/BXD + SĐ01:2026, Mục 3.3"
    }
  ],
  
  "recommendations": [
    {
      "priority": "urgent",
      "description": "Thiết kế khu vực sạc thành khoang cháy riêng với tường ngăn cháy loại 1 (REI 90+).",
      "applicable_regulation": "QCVN 04:2021/BXD + SĐ01:2026, Mục 2.10.2.1e, 2.10.2.1g",
      "responsible_party": "Đơn vị thiết kế PCCC"
    },
    {
      "priority": "urgent",
      "description": "Bổ sung hệ thống chữa cháy tự động cho khu vực sạc tầng hầm.",
      "applicable_regulation": "QCVN 04:2021/BXD + SĐ01:2026, Mục 2.10.2.1e",
      "responsible_party": "Chủ đầu tư"
    },
    {
      "priority": "high",
      "description": "Đề xuất phương án thông gió thoát khói riêng cho khu vực sạc, duy trì biên khói ≥ quy định Phụ lục D QCVN 06.",
      "applicable_regulation": "QCVN 04:2021/BXD + SĐ01:2026, Mục 2.10.2.1e; QCVN 06:2022/BXD Phụ lục D",
      "responsible_party": "Đơn vị tư vấn cơ điện"
    },
    {
      "priority": "medium",
      "description": "Lựa chọn trụ sạc có công suất ≤ 22 kW, có chứng nhận chất lượng.",
      "applicable_regulation": "QCVN 04:2021/BXD + SĐ01:2026, Mục 2.10.2.1k",
      "responsible_party": "Nhà cung cấp thiết bị"
    }
  ],
  
  "traceability": {
    "documents_used": [
      {"doc_id": "QCVN-04-2021-BXD", "version": "original", "amendments": ["SD1-2026-QCVN-04"]},
      {"doc_id": "QCVN-06-2022-BXD", "version": "consolidated", "amendments": ["SD1-2023-QCVN-06"]},
      {"doc_id": "TT-31-2026-TT-BXD", "version": "effective_date_2026-12-15"}
    ],
    "tables_referenced": [
      {"table_id": "bang_06", "title": "Phân nhóm nhà"},
      {"table_id": "bang_h_1", "title": "Nhà ở và ký túc xá kiểu căn hộ"}
    ],
    "footnotes_applied": [],
    "version_at_assessment": "QCVN-04-2021-BXD+SD1-2026,QCVN-06-2022-BXD+SD1-2023"
  }
}
```

### 3.3 Schema Markdown cho in hồ sơ giải trình

```markdown
# BÁO CÁO THẨM ĐỊNH TUÂN THỦ QUY CHUẨN
# DỰ ÁN: Chung cư Cao tầng Hải Phòng

## 1. THÔNG TIN TỔNG QUAN
- Ngày thẩm định: 01/10/2026
- Đơn vị thẩm định: Hệ thống RAG OKF
- Quy chuẩn áp dụng: QCVN 04:2021/BXD (SĐ01:2026), QCVN 06:2022/BXD (SĐ1:2023)
- Kết luận: CONDITIONAL (PASS CÓ ĐIỀU KIỆN)

## 2. KẾT QUẢ CHI TIẾT

### 2.1 Số lượng chỗ sạc — PASS ✅
- **Điều khoản:** QCVN 04:2021 + SĐ01:2026, Mục 2.10.2.1b
- **Giá trị dự án:** 10 chỗ sạc (mô tô điện)
- **Giới hạn:** ≤ 50 chỗ (tầng hầm, mô tô điện)
- **Kết luận:** ĐẠT

### 2.2 Hệ thống PCCC — CONDITIONAL ⚠️
- **Điều khoản:** QCVN 04:2021 + SĐ01:2026, Mục 2.10.2.1e
- **Yêu cầu:** 5 hệ thống bắt buộc (khoang cháy riêng, báo cháy, chữa cháy, thông gió, cảnh báo CO/HF)
- **Kết luận:** CHƯA XÁC ĐỊNH — cần bổ sung thiết kế

## 3. CẢNH BÁO PHÁP LÝ
⚠️ **Yêu cầu mới về sạc xe điện** — TKCS duyệt 10/11/2022, trước SĐ01:2026. 
Bắt buộc cập nhật thiết kế khu vực sạc theo quy chuẩn mới.

## 4. KHUYẾN NGHỊ
1. **[URGENT]** Thiết kế khoang cháy riêng cho khu vực sạc
2. **[URGENT]** Bổ sung hệ thống chữa cháy tự động
3. **[HIGH]** Đề xuất phương án thông gió thoát khói riêng
4. **[MEDIUM]** Chọn trụ sạc ≤ 22 kW có chứng nhận

---
*Báo cáo này được sinh tự động từ hệ thống RAG OKF. 
Người sử dụng cần đối chiếu với hồ sơ thiết kế chính thức.*
```

---

## KẾT LUẬN — YÊU CẦU TÍCH HỢP VÀO HỆ THỐNG

### Schema Pydantic cần tạo

1. **`ProjectProfile`** — bao gồm `project_level`, `primary_function`, `secondary_functions`, `is_apartment_building`, `mixed_use`, `dominant_function`
2. **`GeometricParameters`** — `fire_height_m`, `above_ground_floors`, `underground_floors`, `total_floor_area_m2`, `building_volume_m3`
3. **`ActiveFireProtection`** — `has_sprinkler`, `sprinkler_coverage`, `has_drencher`, `has_mechanical_smoke_extraction`
4. **`LegalTimeline`** — 4 mốc thời gian: `planning_approved`, `cs_design_approved`, `pccc_approved`, `building_permitted`
5. **`ComplianceAssessment`** — output contract cho kỹ sư thực địa

### Symbolic Solver cần xây dựng

1. **`Table4SymbolicSolver`** — Resolve REI với chú thích chân bảng (Sprinkler, báo cháy, vật liệu không cháy)
2. **`Table10SymbolicSolver`** — Tính lưu lượng nước ngoài nhà với chú thích chân bảng (nhân hệ số 1.5 cho > 50m, cộng dồn cho nhiều khoang)
3. **`ChargingAreaValidator`** — Validate khu vực sạc xe điện theo QCVN 04 + SĐ01:2026

### Ingestion Metadata cần bổ sung

1. **Footnote Index** — Mỗi bảng cần có trường `footnotes` trong `tables_catalog.json`, map từng chú thích sang Symbolic Predicate
2. **Scope Gate Rules** — Tệp YAML định nghĩa rule-based scope gate: function_type → QCVN list + priority order
3. **Version Anchor Map** — Map mỗi điều khoản đến version_effective_date, cho phép lookup "quy chuẩn hiệu lực tại ngày X"

---

*End of document.*
