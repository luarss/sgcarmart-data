"""
Upload archived pricelist PDFs (2021-2024) to Cloudflare R2.

Usage:
    uv run python scripts/archive_to_r2.py [--dry-run] [--delete] [--years 2021 2022 ...]
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

# Load from analysis/.env (project convention)
load_dotenv(Path(__file__).parent.parent / "analysis" / ".env")

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "pricelists"

DEFAULT_YEARS = [2021, 2022, 2023, 2024]


def get_r2_client():
    account_id = os.environ.get("R2_ACCOUNT_ID")
    access_key_id = os.environ.get("R2_ACCESS_KEY_ID")
    secret_access_key = os.environ.get("R2_SECRET_ACCESS_KEY")

    missing = [
        k
        for k, v in {
            "R2_ACCOUNT_ID": account_id,
            "R2_ACCESS_KEY_ID": access_key_id,
            "R2_SECRET_ACCESS_KEY": secret_access_key,
        }.items()
        if not v
    ]
    if missing:
        print(f"ERROR: Missing required environment variables: {', '.join(missing)}", file=sys.stderr)
        print("Set them in analysis/.env or export them in your shell.", file=sys.stderr)
        sys.exit(1)

    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        region_name="auto",
    )


def object_exists(client, bucket: str, key: str) -> int | None:
    """Return remote file size if object exists, else None."""
    try:
        resp = client.head_object(Bucket=bucket, Key=key)
        return resp["ContentLength"]
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchKey"):
            return None
        raise


def collect_pdfs(years: list[int]) -> list[Path]:
    pdfs = []
    for year in years:
        pdfs.extend(DATA_DIR.glob(f"*/{year}/*.pdf"))
    return sorted(pdfs)


def archive(
    years: list[int],
    bucket: str,
    dry_run: bool,
    delete_after: bool,
    skip_existing: bool,
) -> None:
    client = None if dry_run else get_r2_client()

    pdfs = collect_pdfs(years)
    if not pdfs:
        print(f"No PDFs found for years {years} under {DATA_DIR}")
        return

    print(f"Found {len(pdfs)} PDF(s) to process (years: {years})")
    if dry_run:
        print("[DRY RUN] No files will be uploaded or deleted.\n")

    uploaded = skipped = failed = deleted = 0

    for local_path in pdfs:
        # R2 key = relative path from project root (e.g. data/pricelists/toyota/2021/...)
        key = local_path.relative_to(PROJECT_ROOT).as_posix()
        local_size = local_path.stat().st_size

        if dry_run:
            print(f"  [dry-run] would upload: {key} ({local_size:,} bytes)")
            uploaded += 1
            continue

        # Skip if already exists and skip_existing is on
        if skip_existing:
            remote_size = object_exists(client, bucket, key)
            if remote_size is not None:
                if remote_size == local_size:
                    skipped += 1
                    continue
                else:
                    print(f"  [size mismatch] re-uploading: {key} (local={local_size}, remote={remote_size})")

        # Upload
        try:
            with local_path.open("rb") as fh:
                client.put_object(Bucket=bucket, Key=key, Body=fh, ContentLength=local_size)
        except Exception as e:
            print(f"  [FAIL] {key}: {e}", file=sys.stderr)
            failed += 1
            continue

        # Verify
        remote_size = object_exists(client, bucket, key)
        if remote_size != local_size:
            print(f"  [VERIFY FAIL] {key}: uploaded size {remote_size} != local size {local_size}", file=sys.stderr)
            failed += 1
            continue

        uploaded += 1

        if delete_after:
            local_path.unlink()
            deleted += 1

    # Summary
    print(f"\nDone: {uploaded} uploaded, {skipped} skipped, {failed} failed, {deleted} deleted locally.")
    if failed:
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Archive pricelist PDFs to Cloudflare R2")
    parser.add_argument(
        "--years",
        nargs="+",
        type=int,
        default=DEFAULT_YEARS,
        metavar="YEAR",
        help=f"Years to archive (default: {DEFAULT_YEARS})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview files without uploading",
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Delete local file after verified upload",
    )
    parser.add_argument(
        "--no-skip-existing",
        action="store_true",
        help="Re-upload files that already exist in R2",
    )
    args = parser.parse_args()

    bucket = os.environ.get("R2_BUCKET_NAME")
    if not bucket and not args.dry_run:
        # Load env now so we can check bucket name
        load_dotenv(Path(__file__).parent.parent / "analysis" / ".env")
        bucket = os.environ.get("R2_BUCKET_NAME")
    if not bucket and not args.dry_run:
        print("ERROR: R2_BUCKET_NAME is not set.", file=sys.stderr)
        sys.exit(1)

    archive(
        years=args.years,
        bucket=bucket or "dry-run-bucket",
        dry_run=args.dry_run,
        delete_after=args.delete,
        skip_existing=not args.no_skip_existing,
    )


if __name__ == "__main__":
    main()
