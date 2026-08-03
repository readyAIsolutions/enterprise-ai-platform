#!/usr/bin/env python3
"""CI failure reporter — writes failed-test names from junit.xml into a
GITHUB_STEP_SUMMARY file so failing tests are visible in PR annotations
(even when raw job logs are behind auth)."""
import os
import sys
import xml.etree.ElementTree as ET


def main() -> int:
    summary = sys.argv[1] if len(sys.argv) > 1 else None
    junit = "junit.xml"
    out = []
    if os.path.exists(junit):
        try:
            root = ET.parse(junit).getroot()
            for tc in root.iter("testcase"):
                for fail in tc.iter("failure"):
                    out.append(
                        f"- {tc.get('classname')}::{tc.get('name')} : "
                        f"{((fail.get('message') or '')[:200])}"
                    )
        except Exception as e:  # noqa: BLE001
            out.append(f"(junit parse error: {e})")
    text = "\n".join(out)
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write("```\n" + text + "\n```\n")
    print(f"failed tests reported: {len(out)}")
    for line in out:
        print(line)
    return 1  # re-fail the step (it only runs when the test step already failed)


if __name__ == "__main__":
    raise SystemExit(main())
