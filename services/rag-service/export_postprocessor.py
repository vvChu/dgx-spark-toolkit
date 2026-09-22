#!/usr/bin/env python3
"""Thin CLI wrapper for DataExporter.reprocess_exports."""
import argparse
from ingestion.exporter import DataExporter


def main():
    parser = argparse.ArgumentParser(description="RAG Export Post-Processor")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--apply", action="store_true", help="Apply fixes to exports")
    group.add_argument("--revert", action="store_true", help="Revert to backup copies")
    group.add_argument("--dry-run", action="store_true", help="Show what would change")
    parser.add_argument("--export-dir", default=None, help="Directory containing json/ and markdown/ exports")

    args = parser.parse_args()
    action = "apply" if args.apply else ("revert" if args.revert else "dry-run")

    exporter = DataExporter(args.export_dir)
    stats = exporter.reprocess_exports(action=action)
    print(f"Action '{action}' completed: {stats}")


if __name__ == "__main__":
    main()
