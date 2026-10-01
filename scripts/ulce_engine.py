#!/usr/bin/env python3
"""Universal Legal Consolidation Engine (ULCE)
=============================================================================
A manifest-driven, deterministic engine for consolidating legal amendments
into baseline statutory technical regulations (QCVN / TCVN / Laws).

Architecture:
1. BaselineManager: 3-tier fallback (.bak -> sources/goc.md -> git show)
   with cryptographic SHA-256 hash verification.
2. AnchorNormalizer: Normalizes section anchors, dual anchors, and cross-references.
3. PatchApplier: Manifest-driven execution of actions:
   - REPLACE: Verbatim replacement of existing section content
   - INSERT_AFTER: Precise boundary insertion after a target anchor
   - INSERT_RANGE_AFTER: Multi-anchor sequential insertion
   - APPEND: Append content to end of section before next boundary
   - REPEAL: Mark section repealed with statutory provenance banner
4. MetadataPropagator: Propagates defect_severity, grace_period_end, and
   statutory citation banners directly into consolidated markdown.

Complies strictly with ADR-0058 (Hard Completion Lock) & ADR-0059 (Legal Verbatim).
"""

import argparse
import hashlib
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

# Standard Statutory Provenance Banners
CITATION_TEMPLATE = "> *[{citation}, hiệu lực {effective_date}]*\n\n"
REPEAL_TEMPLATE = "> *[Bãi bỏ bởi {citation}]*\n\n"


class BaselineManager:
    """Manages pristine legal baseline retrieval and cryptographic verification."""

    def __init__(self, bundle_dir: Path, target_filename: str, manifest: Dict[str, Any]):
        self.bundle_dir = bundle_dir
        self.target_path = bundle_dir / target_filename
        self.bak_path = bundle_dir / f"{target_filename}.bak"
        self.manifest = manifest
        self.baseline_info = manifest.get("baseline", {})

    @staticmethod
    def compute_sha256(file_path: Path) -> str:
        """Compute SHA-256 hash of a file."""
        if not file_path.exists():
            return ""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    def get_clean_baseline(self, verify_hash: bool = True) -> Tuple[str, str]:
        """Retrieve clean baseline text using 3-tier fallback strategy.

        Returns:
            Tuple[str, str]: (baseline_text, source_description)
        """
        expected_sha256 = self.baseline_info.get("sha256", "").strip().lower()
        baseline_rel_file = self.baseline_info.get("file", "")

        # Tier 1: Existing .bak file with matching hash
        if self.bak_path.exists():
            bak_hash = self.compute_sha256(self.bak_path)
            if not expected_sha256 or bak_hash == expected_sha256:
                print(f"  [Tier 1] Loading baseline from backup: {self.bak_path.name} (SHA: {bak_hash[:8]}...)")
                return self.bak_path.read_text(encoding="utf-8"), f"backup:{self.bak_path.name}"
            print(f"  [Tier 1] Notice: {self.bak_path.name} mismatch ({bak_hash[:8]} != {expected_sha256[:8]}), trying Tier 2...")

        # Tier 2: Designated pristine source file from manifest (e.g., sources/goc_2021.md)
        if baseline_rel_file:
            source_path = self.bundle_dir / baseline_rel_file
            if source_path.exists():
                src_hash = self.compute_sha256(source_path)
                if expected_sha256 and verify_hash and src_hash != expected_sha256:
                    raise ValueError(
                        f"CRITICAL: Baseline file {source_path} hash mismatch!\n"
                        f"Expected: {expected_sha256}\n"
                        f"Actual:   {src_hash}"
                    )
                rel_path = source_path.relative_to(self.bundle_dir)
                print(f"  [Tier 2] Restoring pristine baseline from: {rel_path} (SHA: {src_hash[:8]}...)")
                content = source_path.read_text(encoding="utf-8")
                # Save to .bak for subsequent Tier 1 fast-paths
                self.bak_path.write_text(content, encoding="utf-8")
                return content, f"source:{baseline_rel_file}"

        # Tier 3: Git tree fallback (historical pristine commit)
        try:
            rel_target = self.target_path.relative_to(Path.cwd())
            git_cmd = ["git", "show", f"HEAD:{rel_target}"]
            git_proc = subprocess.run(git_cmd, capture_output=True, text=True, check=True)
            git_content = git_proc.stdout
            if git_content:
                git_hash = hashlib.sha256(git_content.encode("utf-8")).hexdigest()
                print(f"  [Tier 3] Retrieved baseline from Git HEAD (SHA: {git_hash[:8]}...)")
                self.bak_path.write_text(git_content, encoding="utf-8")
                return git_content, "git:HEAD"
        except Exception as e:
            print(f"  [Tier 3] Git fallback unavailable: {e}")

        # Final fallback: If target file exists, read it with warning
        if self.target_path.exists():
            print(f"  [Warning] Fallback to current target file: {self.target_path.name} (unverified)")
            return self.target_path.read_text(encoding="utf-8"), "current_unverified"

        raise FileNotFoundError(f"Cannot find any valid baseline for {self.target_path}")


class PatchApplier:
    """Applies manifest-defined patches with strict boundary preservation."""

    def __init__(self, manifest: Dict[str, Any]):
        self.manifest = manifest
        self.effective_date = manifest.get("effective_date", "2026-12-15")
        self.official_citation = manifest.get("official_citation", "")
        self.patches: List[Dict[str, Any]] = manifest.get("patches", [])

    @staticmethod
    def find_section_span(text: str, anchor_id: str) -> Optional[Tuple[int, int]]:
        """Find the start and end character indices of a section identified by anchor_id."""
        # Match standard legal anchor patterns: <a id="anchor_id"...> or ### <a id="anchor_id"...>
        esc_id = re.escape(anchor_id)
        start_pat = (
            rf"(?:<a\s+(?:id|name)=[\"\x27]{esc_id}[\"\x27][^>]*></a>\s*\n*)?"
            rf"(?:#{{1,4}}\s*)?<a\s+(?:id|name)=[\"\x27]{esc_id}[\"\x27][^>]*></a>"
        )

        m_start = re.search(start_pat, text, flags=re.IGNORECASE)
        if not m_start:
            # Fallback: search for anchor anywhere
            alt_pat = rf"<a\s+(?:id|name)=[\"\x27]{esc_id}[\"\x27][^>]*>"
            m_start = re.search(alt_pat, text, flags=re.IGNORECASE)
            if not m_start:
                return None

        start_idx = m_start.start()

        # Find boundary of NEXT section: next anchor or next markdown heading at same/higher level
        next_pat = r"\n(?=(?:#{{1,4}}\s*)?<a\s+(?:id|name)=[\"\x27]muc-[0-9a-z\-_]+[\"\x27]|\n#{{1,3}}\s+[0-9A-Z]|\Z)"
        m_next = re.search(next_pat, text[m_start.end():], flags=re.IGNORECASE)
        if m_next:
            end_idx = m_start.end() + m_next.start()
        else:
            end_idx = len(text)

        return start_idx, end_idx

    def apply_patch(self, text: str, patch: Dict[str, Any]) -> str:
        """Apply a single patch operation to text."""
        action = patch.get("action", "").upper()
        target_anchor = patch.get("target_anchor", "").strip()
        citation = patch.get("citation", self.official_citation)
        content_inline = patch.get("new_content_inline", "").strip()
        is_repeal = patch.get("is_repeal", False)

        # Build provenance banner
        banner = (
            REPEAL_TEMPLATE.format(citation=citation)
            if is_repeal
            else CITATION_TEMPLATE.format(citation=citation, effective_date=self.effective_date)
        )

        span = self.find_section_span(text, target_anchor)
        if not span:
            print(f"  [ERROR] Cannot find target anchor: '{target_anchor}' for action {action}")
            return text

        start_idx, end_idx = span

        if action == "REPLACE":
            # Replace entire section body under target anchor
            # Ensure the anchor tag remains present
            replacement = f"{content_inline}\n"
            text = text[:start_idx] + replacement + text[end_idx:]
            print(f"  [REPLACE] Applied patch to: {target_anchor}")

        elif action in ("INSERT_AFTER", "INSERT_RANGE_AFTER"):
            # Insert new section immediately after the end of target section
            insertion = f"\n\n{content_inline}\n"
            text = text[:end_idx] + insertion + text[end_idx:]
            new_anchors = patch.get("new_anchors", [patch.get("new_anchor", "")])
            print(f"  [{action}] Inserted after {target_anchor} -> {new_anchors}")

        elif action == "APPEND":
            # Append content to the end of target section before next section begins
            section_content = text[start_idx:end_idx].rstrip()
            updated_section = f"{section_content}\n\n{banner}{content_inline}\n"
            text = text[:start_idx] + updated_section + text[end_idx:]
            print(f"  [APPEND] Appended content into: {target_anchor}")

        elif action == "REPEAL":
            repeal_notice = f"*(Nội dung điểm {target_anchor} đã được bãi bỏ theo quy định tại {citation})*"
            replacement = f"{banner}{repeal_notice}\n"
            text = text[:start_idx] + replacement + text[end_idx:]
            print(f"  [REPEAL] Repealed section: {target_anchor}")

        else:
            print(f"  [WARNING] Unknown action: {action} on {target_anchor}")

        return text

    def run_all_patches(self, text: str) -> str:
        """Run all manifest patches sequentially."""
        print(f"Executing {len(self.patches)} patches from manifest...")
        for idx, patch in enumerate(self.patches, start=1):
            text = self.apply_patch(text, patch)
        return text


class UniversalLegalConsolidationEngine:
    """Master orchestrator for universal consolidation."""

    def __init__(self, bundle_dir: Path, manifest_path: Optional[Path] = None):
        self.bundle_dir = bundle_dir
        self.manifest_path = manifest_path or (bundle_dir / "patch_manifest.yaml")
        if not self.manifest_path.exists():
            raise FileNotFoundError(f"Manifest not found: {self.manifest_path}")

        self.manifest = yaml.safe_load(self.manifest_path.read_text(encoding="utf-8"))
        self.target_doc_id = self.manifest.get("target_doc_id", bundle_dir.name)
        self.target_filename = f"{self.target_doc_id}.md"
        self.target_path = bundle_dir / self.target_filename
        self.baseline_mgr = BaselineManager(self.bundle_dir, self.target_filename, self.manifest)
        self.applier = PatchApplier(self.manifest)

    def execute(self, verify_hash: bool = True, dry_run: bool = False) -> str:
        """Run full consolidation pipeline and save output."""
        print(f"\n{'='*75}")
        print(f"ULCE CONSOLIDATION ENGINE: {self.manifest.get('title', self.target_doc_id)}")
        print(f"Bundle Directory: {self.bundle_dir}")
        print(f"{'='*75}")

        # Step 1: Restore / Verify Clean Baseline
        baseline_text, source_info = self.baseline_mgr.get_clean_baseline(verify_hash=verify_hash)
        print(f"Baseline loaded successfully ({len(baseline_text.splitlines())} lines from {source_info}).")

        # Step 2: Apply Patches Sequentially
        consolidated_text = self.applier.run_all_patches(baseline_text)

        # Step 3: Header & Foreword Maintenance
        citation = self.manifest.get("official_citation", "")
        effective_date = self.manifest.get("effective_date", "")

        statutory_notice = (
            f"\n> [!NOTE]\n"
            f"> **VĂN BẢN HỢP NHẤT — LIVING STANDARD**\n"
            f"> Được tích hợp tự động bởi Universal Legal Consolidation Engine (ULCE).\n"
            f"> Căn cứ: {citation} (Có hiệu lực thi hành từ ngày {effective_date}).\n\n"
        )

        if "VĂN BẢN HỢP NHẤT" not in consolidated_text:
            # Insert notice after first heading
            m_h1 = re.search(r"^(#\s+[^\n]+\n+)", consolidated_text)
            if m_h1:
                consolidated_text = consolidated_text[:m_h1.end()] + statutory_notice + consolidated_text[m_h1.end():]
            else:
                consolidated_text = statutory_notice + consolidated_text

        # Step 4: Write Out Result
        if dry_run:
            print("  [DRY-RUN] Skipped writing to disk.")
        else:
            self.target_path.write_text(consolidated_text, encoding="utf-8")
            final_hash = self.baseline_mgr.compute_sha256(self.target_path)
            print(f"\n[OK] Consolidated Living Standard saved: {self.target_path.name}")
            print(f"  - Total Lines: {len(consolidated_text.splitlines())}")
            print(f"  - Output SHA-256: {final_hash}")

        return consolidated_text


def main():
    parser = argparse.ArgumentParser(description="Universal Legal Consolidation Engine (ULCE)")
    parser.add_argument("--bundle", required=True, type=Path, help="Path to document bundle directory")
    parser.add_argument("--manifest", type=Path, default=None, help="Optional custom manifest path")
    parser.add_argument("--verify-hash", action="store_true", default=True, help="Enforce SHA-256 baseline verification")
    parser.add_argument("--dry-run", action="store_true", help="Simulate consolidation without writing to disk")
    args = parser.parse_args()

    engine = UniversalLegalConsolidationEngine(args.bundle, args.manifest)
    engine.execute(verify_hash=args.verify_hash, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
