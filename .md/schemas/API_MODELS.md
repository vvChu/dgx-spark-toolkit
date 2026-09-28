# 📋 OpenAPI Schemas & Data Contracts

- **API Title**: `BIM RAG Engine API (Refactored)`
- **Version**: `2.0.0`
- **Total Schemas**: `17`

---

### `ChatRequest`

- **Type**: `object`

| Property | Type | Required | Description |
|---|---|:---:|---|
| `context_limit` | `any` | ❌ | - |
| `history` | `any` | ❌ | - |
| `language` | `any` | ❌ | - |
| `model` | `any` | ❌ | - |
| `query` | `string` | ✅ | - |
| `session_id` | `any` | ❌ | - |
| `use_agentic` | `any` | ❌ | - |

---

### `ChatResponse`

- **Type**: `object`
- **Description**: Response from /chat endpoint.

| Property | Type | Required | Description |
|---|---|:---:|---|
| `answer` | `string` | ✅ | - |
| `cached` | `boolean` | ❌ | - |
| `context` | `array` | ❌ | - |
| `session_id` | `any` | ❌ | - |
| `thought` | `any` | ❌ | - |
| `trace` | `any` | ❌ | - |
| `usage` | `any` | ❌ | - |

---

### `ComplianceCheckRequest`

- **Type**: `object`

| Property | Type | Required | Description |
|---|---|:---:|---|
| `focus_area` | `any` | ❌ | - |
| `project_profile` | `string` | ✅ | - |

---

### `ConflictAnalysisRequest`

- **Type**: `object`

| Property | Type | Required | Description |
|---|---|:---:|---|
| `depth` | `integer` | ❌ | - |
| `doc_id` | `string` | ✅ | - |
| `query` | `string` | ✅ | - |

---

### `DiagramGenerationRequest`

- **Type**: `object`
- **Description**: Request for generating visual SOP/QCVN workflow diagrams via Imagen 4 Fast.

| Property | Type | Required | Description |
|---|---|:---:|---|
| `sop_title` | `string` | ✅ | - |
| `style` | `any` | ❌ | - |
| `workflow_steps` | `array` | ✅ | - |

---

### `DiagramGenerationResponse`

- **Type**: `object`
- **Description**: Response containing generated diagram metadata and image prompt.

| Property | Type | Required | Description |
|---|---|:---:|---|
| `daily_quota_limit` | `integer` | ❌ | - |
| `image_prompt` | `string` | ✅ | - |
| `model` | `string` | ❌ | - |
| `sop_title` | `string` | ✅ | - |
| `status` | `string` | ✅ | - |

---

### `EvaluationRequest`

- **Type**: `object`

| Property | Type | Required | Description |
|---|---|:---:|---|
| `answer` | `string` | ✅ | - |
| `context` | `array` | ✅ | - |
| `query` | `string` | ✅ | - |

---

### `EvaluationResponse`

- **Type**: `object`

| Property | Type | Required | Description |
|---|---|:---:|---|
| `faithfulness` | `number` | ✅ | - |
| `faithfulness_reason` | `string` | ✅ | - |
| `relevancy` | `number` | ✅ | - |
| `relevancy_reason` | `string` | ✅ | - |
| `suggestions` | `any` | ❌ | - |

---

### `FeedbackRequest`

- **Type**: `object`

| Property | Type | Required | Description |
|---|---|:---:|---|
| `answer` | `string` | ✅ | - |
| `comment` | `any` | ❌ | - |
| `is_positive` | `boolean` | ✅ | - |
| `query` | `string` | ✅ | - |

---

### `HTTPValidationError`

- **Type**: `object`

| Property | Type | Required | Description |
|---|---|:---:|---|
| `detail` | `array` | ❌ | - |

---

### `SearchRequest`

- **Type**: `object`

| Property | Type | Required | Description |
|---|---|:---:|---|
| `authority` | `any` | ❌ | - |
| `doc_number` | `any` | ❌ | - |
| `doc_type` | `any` | ❌ | - |
| `limit` | `integer` | ❌ | - |
| `query` | `string` | ✅ | - |
| `session_id` | `any` | ❌ | - |
| `use_cache` | `any` | ❌ | - |
| `use_hyde` | `any` | ❌ | - |
| `use_reranker` | `boolean` | ❌ | - |
| `year` | `any` | ❌ | - |

---

### `SearchResponse`

- **Type**: `object`
- **Description**: Response from /search and /retrieve endpoints.

| Property | Type | Required | Description |
|---|---|:---:|---|
| `cached` | `boolean` | ❌ | - |
| `query` | `string` | ❌ | - |
| `results` | `array` | ❌ | - |
| `rewritten_query` | `any` | ❌ | - |
| `trace` | `any` | ❌ | - |

---

### `SearchResultItem`

- **Type**: `object`
- **Description**: A single document chunk returned from search.

| Property | Type | Required | Description |
|---|---|:---:|---|
| `authority` | `any` | ❌ | - |
| `bbox` | `any` | ❌ | - |
| `doc_id` | `any` | ❌ | - |
| `doc_number` | `string` | ❌ | - |
| `doc_type` | `any` | ❌ | - |
| `page` | `integer` | ❌ | - |
| `score` | `number` | ❌ | - |
| `text` | `string` | ✅ | - |
| `year` | `any` | ❌ | - |

---

### `StatsResponse`

- **Type**: `object`
- **Description**: Response from /stats endpoint.

| Property | Type | Required | Description |
|---|---|:---:|---|
| `milvus_entities` | `integer` | ❌ | - |
| `neo4j_docs` | `integer` | ❌ | - |
| `neo4j_rels` | `integer` | ❌ | - |
| `total_target` | `integer` | ❌ | - |

---

### `SyncStatusRequest`

- **Type**: `object`

| Property | Type | Required | Description |
|---|---|:---:|---|
| `doc_id` | `string` | ✅ | - |
| `new_status` | `string` | ✅ | - |

---

### `SyncStatusResponse`

- **Type**: `object`
- **Description**: Response from /admin/sync-status endpoint.

| Property | Type | Required | Description |
|---|---|:---:|---|
| `doc_id` | `string` | ✅ | - |
| `new_status` | `string` | ✅ | - |
| `status` | `string` | ✅ | - |
| `updates` | `object` | ❌ | - |

---

### `ValidationError`

- **Type**: `object`

| Property | Type | Required | Description |
|---|---|:---:|---|
| `ctx` | `object` | ❌ | - |
| `input` | `any` | ❌ | - |
| `loc` | `array` | ✅ | - |
| `msg` | `string` | ✅ | - |
| `type` | `string` | ✅ | - |

---

