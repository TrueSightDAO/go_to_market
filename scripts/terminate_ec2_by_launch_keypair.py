#!/usr/bin/env python3
"""
Find EC2 instances in every AWS region whose launch-time key pair name matches
a given value, optionally terminate them.

Uses the DescribeInstances filter ``key-name`` (the key pair assigned at launch).

Dependencies::

    pip install boto3

Authentication uses the normal boto3 chain (env vars ``AWS_ACCESS_KEY_ID`` /
``AWS_SECRET_ACCESS_KEY``, ``AWS_PROFILE``, ``~/.aws/credentials``, SSO, or an
instance role).

Examples::

    # List matches only (default; no termination)
    python3 scripts/terminate_ec2_by_launch_keypair.py

    # Explicit dry run against AWS (permission check, no termination)
    python3 scripts/terminate_ec2_by_launch_keypair.py --aws-dry-run

    # Actually terminate (irreversible)
    python3 scripts/terminate_ec2_by_launch_keypair.py --execute

    # Custom key name and profile
    python3 scripts/terminate_ec2_by_launch_keypair.py --key-name my-key --profile prod --execute
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError
except ImportError as exc:  # pragma: no cover
    print("Install boto3: pip install boto3", file=sys.stderr)
    raise SystemExit(1) from exc

DEFAULT_KEY_NAME = "buatbelisdfgmsobilbaim"

# For second-pass sweeps: exclude ``terminated`` (and optional ``shutting-down``) from DescribeInstances.
ACTIVE_INSTANCE_STATES = ("pending", "running", "stopping", "stopped", "shutting-down")


def apply_aws_dotenv() -> None:
    """
    Load AWS credentials from local ``.env`` files when not already in the environment.

    Precedence (later files override earlier for the same key):

    1. Sibling repo ``Cypher-Defense/.env`` (preferred for incident response keys).
    2. ``market_research/.env`` (legacy / local convenience).

    Maps ``AWS_KEY`` / ``AWSKEY`` / ``AWS_SECRET`` onto boto3's standard names.
    """
    try:
        from dotenv import dotenv_values
    except ImportError:
        return

    market_root = Path(__file__).resolve().parent.parent
    apps_root = market_root.parent
    paths = [
        apps_root / "Cypher-Defense" / ".env",
        market_root / ".env",
    ]
    merged: dict[str, Any] = {}
    for env_path in paths:
        if not env_path.is_file():
            continue
        vals = {k: v for k, v in dotenv_values(env_path).items() if v not in (None, "")}
        merged.update(vals)

    if not os.environ.get("AWS_ACCESS_KEY_ID"):
        for k in ("AWS_ACCESS_KEY_ID", "AWSKEY", "AWS_KEY"):
            if merged.get(k):
                os.environ["AWS_ACCESS_KEY_ID"] = str(merged[k]).strip()
                break
    if not os.environ.get("AWS_SECRET_ACCESS_KEY") and merged.get("AWS_SECRET"):
        os.environ["AWS_SECRET_ACCESS_KEY"] = str(merged["AWS_SECRET"]).strip()


def ec2_regions(session: boto3.Session) -> list[str]:
    client = session.client("ec2", region_name="us-east-1")
    return sorted(r["RegionName"] for r in client.describe_regions()["Regions"])


def describe_matches(
    session: boto3.Session,
    region: str,
    key_name: str,
    *,
    active_states_only: bool = False,
) -> tuple[list[dict[str, Any]], str | None]:
    """
    Return (rows, error_message). error_message set if the region call failed.

    If ``active_states_only`` is True, only return instances whose lifecycle state
    is not ``terminated`` (typical follow-up sweep after a bulk terminate).
    """
    ec2 = session.client("ec2", region_name=region)
    paginator = ec2.get_paginator("describe_instances")
    flt: list[dict[str, Any]] = [{"Name": "key-name", "Values": [key_name]}]
    if active_states_only:
        flt.append({"Name": "instance-state-name", "Values": list(ACTIVE_INSTANCE_STATES)})
    rows: list[dict[str, Any]] = []
    try:
        for page in paginator.paginate(Filters=flt):
            for res in page.get("Reservations", []):
                for inst in res.get("Instances", []):
                    name = ""
                    for t in inst.get("Tags") or []:
                        if t.get("Key") == "Name":
                            name = t.get("Value") or ""
                            break
                    placement = inst.get("Placement") or {}
                    rows.append(
                        {
                            "Region": region,
                            "AvailabilityZone": placement.get("AvailabilityZone") or "",
                            "InstanceId": inst["InstanceId"],
                            "State": inst["State"]["Name"],
                            "KeyName": inst.get("KeyName") or "",
                            "Name": name,
                            "LaunchTime": inst.get("LaunchTime").isoformat()
                            if inst.get("LaunchTime")
                            else "",
                        }
                    )
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        return [], f"{region}: {code} {e}"
    except BotoCoreError as e:
        return [], f"{region}: {e}"
    return rows, None


def terminate_batch(
    session: boto3.Session,
    region: str,
    instance_ids: list[str],
    *,
    aws_dry_run: bool,
) -> dict[str, Any]:
    ec2 = session.client("ec2", region_name=region)
    kwargs: dict[str, Any] = {"InstanceIds": instance_ids}
    if aws_dry_run:
        kwargs["DryRun"] = True
    return ec2.terminate_instances(**kwargs)


def main() -> int:
    p = argparse.ArgumentParser(
        description="List or terminate EC2 instances by launch key pair name across all regions."
    )
    p.add_argument(
        "--key-name",
        default=DEFAULT_KEY_NAME,
        help=f"EC2 launch key pair name to match (default: {DEFAULT_KEY_NAME!r})",
    )
    p.add_argument(
        "--profile",
        default="",
        help="Optional AWS named profile (boto3 Session profile_name).",
    )
    p.add_argument(
        "--regions",
        default="",
        help="Comma-separated regions to scan instead of every enabled region.",
    )
    p.add_argument(
        "--execute",
        action="store_true",
        help="Terminate matching instances. Without this, only prints matches.",
    )
    p.add_argument(
        "--aws-dry-run",
        action="store_true",
        help="If combined with --execute, pass DryRun=true to TerminateInstances (permission check only).",
    )
    p.add_argument("--json", action="store_true", help="Print machine-readable JSON summary.")
    p.add_argument(
        "--active-states-only",
        action="store_true",
        help="Only match instances in pending/running/stopping/stopped/shutting-down (excludes terminated).",
    )
    args = p.parse_args()

    if args.aws_dry_run and not args.execute:
        print("--aws-dry-run only applies with --execute", file=sys.stderr)
        return 2

    apply_aws_dotenv()

    session_kw: dict[str, Any] = {}
    if args.profile.strip():
        session_kw["profile_name"] = args.profile.strip()
    session = boto3.Session(**session_kw)

    if args.regions.strip():
        regions = [r.strip() for r in args.regions.split(",") if r.strip()]
    else:
        regions = ec2_regions(session)

    all_rows: list[dict[str, Any]] = []
    region_errors: list[str] = []

    for region in regions:
        rows, err = describe_matches(
            session, region, args.key_name, active_states_only=args.active_states_only
        )
        if err:
            region_errors.append(err)
            continue
        all_rows.extend(rows)

    by_region: dict[str, list[str]] = {}
    for r in all_rows:
        by_region.setdefault(r["Region"], []).append(r["InstanceId"])

    summary: dict[str, Any] = {
        "key_name": args.key_name,
        "matched_count": len(all_rows),
        "instances": all_rows,
        "region_errors": region_errors,
        "execute": args.execute,
        "aws_dry_run": args.aws_dry_run,
        "active_states_only": args.active_states_only,
    }

    if not args.json:
        if region_errors:
            print("Warnings (describe_instances):", file=sys.stderr)
            for e in region_errors:
                print(f"  {e}", file=sys.stderr)
        if not all_rows:
            print(f"No instances found with key-name={args.key_name!r} in scanned regions.")
            return 0
        print(f"Found {len(all_rows)} instance(s) with key-name={args.key_name!r}:\n")
        for r in all_rows:
            nm = f" name={r['Name']!r}" if r.get("Name") else ""
            az = r.get("AvailabilityZone") or "?"
            print(
                f"  {r['Region']}  az={az}  {r['InstanceId']}  state={r['State']}{nm}  launch={r.get('LaunchTime','')}"
            )

    if not args.execute:
        if not args.json:
            print(
                "\nDry listing only. Re-run with --execute to terminate these instances "
                "(add --aws-dry-run first to verify IAM without terminating)."
            )
        else:
            print(json.dumps(summary, indent=2))
        return 0

    id_to_az: dict[str, str] = {
        r["InstanceId"]: (r.get("AvailabilityZone") or "") for r in all_rows
    }

    # Terminate per region
    term_results: list[dict[str, Any]] = []
    for region, ids in sorted(by_region.items()):
        if not ids:
            continue
        try:
            resp = terminate_batch(session, region, ids, aws_dry_run=args.aws_dry_run)
            term_results.append({"region": region, "response": resp})
            if not args.json:
                label = "DryRun terminate" if args.aws_dry_run else "Terminate"
                print(f"\n{label} {region}: {ids}")
                for ti in resp.get("TerminatingInstances", []):
                    iid = ti.get("InstanceId")
                    az = id_to_az.get(iid or "", "") or "unknown"
                    prev = ti.get("PreviousState", {}).get("Name")
                    cur = ti.get("CurrentState", {}).get("Name")
                    print(
                        f"  availability_zone={az}  instance_id={iid}  state {prev} -> {cur}"
                    )
        except ClientError as e:
            term_results.append({"region": region, "error": str(e), "instance_ids": ids})
            print(f"ERROR {region}: {e}", file=sys.stderr)

    summary["terminate"] = term_results
    if args.json:
        print(json.dumps(summary, indent=2))

    return 0 if not any("error" in tr for tr in term_results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
