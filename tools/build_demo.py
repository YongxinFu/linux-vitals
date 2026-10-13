#!/usr/bin/env python3
"""Render the demo dashboard and the sample-fleet data from a linux-vitals checkout.

Usage: tools/build_demo.py /path/to/linux-vitals

Every host result is one of the collection's own golden fixtures
(tests/golden/*.json -- real scan output, pinned by tests/test_golden_findings.py),
renamed onto a sample fleet. The dashboard is then produced by the real
vitals_report role: a baseline run, then a postcheck run with the same
maintenance id, so the page shows a genuine before/after comparison.

Writes:
  assets/demo-dashboard.html  -- the rendered dashboard (iframed by the site)
  assets/fleet.js             -- the postcheck results, for the interactive sections
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

SITE = Path(__file__).resolve().parents[1]
MAINTENANCE_ID = "CHG-2026-1012"

# host -> (ip, baseline fixture or None for a host added during the window,
#          postcheck fixture, tweaks applied to both runs)
FLEET = {
    "web-01": ("10.0.3.11", "ubuntu_degraded", "ubuntu_healthy", {}),
    "web-02": ("10.0.3.12", "ubuntu_healthy", "ubuntu_healthy", {}),
    "web-03": ("10.0.3.13", "ubuntu_healthy", "journal_denied", {}),
    "db-01": ("10.0.4.21", "rocky_degraded", "rocky_healthy", {}),
    "db-02": ("10.0.4.22", "rocky_healthy", "rocky_critical", {}),
    "api-01": ("10.0.5.31", "rocky_healthy", "rocky_healthy", {
        "os": "Amazon 2023", "running_kernel": "6.1.112-122.189.amzn2023.x86_64",
        "latest_installed_kernel": "6.1.112-122.189.amzn2023.x86_64",
        "bootloader_default_kernel": "6.1.112-122.189.amzn2023.x86_64",
        "bootloader_default_entry": "/boot/vmlinuz-6.1.112-122.189.amzn2023.x86_64",
        "selinux_status": "Permissive", "platform_type": "Cloud Instance",
        "virtualization_type": "kvm",
    }),
    "ws-07": ("10.0.6.47", "fedora_healthy", "fedora_healthy", {}),
    "build-04": ("10.0.6.44", "fedora_degraded", "fedora_degraded", {}),
    "app-03": ("10.0.7.53", "opensuse_healthy", "opensuse_healthy", {}),
    "app-04": ("10.0.7.54", "opensuse_degraded", "opensuse_critical", {}),
    "cache-01": ("10.0.3.41", None, "ubuntu_healthy", {
        "os": "Debian 12", "running_kernel": "6.1.0-26-amd64",
        "latest_installed_kernel": "6.1.0-26-amd64",
        "bootloader_default_kernel": "6.1.0-26-amd64",
    }),
}

# web-01 also had a failed unit that vitals_heal restarted during the postcheck.
HEALED = {"web-01": ["nginx.service"]}


def result(collection: Path, fixture: str, host: str, ip: str, tweaks: dict) -> dict:
    data = json.loads((collection / "tests" / "golden" / f"{fixture}.json").read_text())
    data = copy.deepcopy(data)
    data.update(tweaks)
    data["hostname"] = host
    data["ip_address"] = ip
    data["comparison"] = {"baseline_available": False}
    data.setdefault("unknown_count", 0)
    return data


def main(collection: Path) -> None:
    baseline, postcheck = {}, {}
    for host, (ip, before, after, tweaks) in FLEET.items():
        if before:
            baseline[host] = result(collection, before, host, ip, tweaks)
        postcheck[host] = result(collection, after, host, ip, tweaks)
        healed = HEALED.get(host, [])
        postcheck[host]["services_healed"] = healed
        postcheck[host]["healing_results"] = [{"service": s, "result": "Fixed"} for s in healed]

    work = Path(tempfile.mkdtemp(prefix="lv-demo-"))
    try:
        (work / "inventory.ini").write_text(
            "[linux_servers]\n"
            + "".join(f"{h} ansible_connection=local\n" for h in FLEET)
            + "\n[baseline_hosts]\n"
            + "".join(f"{h}\n" for h in baseline)
        )
        (work / "fleet.yml").write_text(yaml.safe_dump({"demo_baseline": baseline, "demo_postcheck": postcheck}))
        common = {
            "gather_facts": False,
            "vars_files": ["fleet.yml"],
            "vars": {
                "ansible_python_interpreter": sys.executable,
                "linux_vitals_maintenance_id": MAINTENANCE_ID,
                "linux_vitals_archive_html_reports": False,
                "linux_vitals_archive_json_reports": False,
                "linux_vitals_report_title": "LinuxVitals Health Check Dashboard",
            },
        }
        plays = [
            {**common, "name": "Baseline", "hosts": "baseline_hosts",
             "vars": {**common["vars"], "linux_vitals_phase": "baseline"},
             "tasks": [
                 {"ansible.builtin.set_fact": {
                     "linux_vitals_result": "{{ demo_baseline[inventory_hostname] }}",
                     "linux_vitals_auto_fixed_count": 0}},
                 {"ansible.builtin.include_role": {"name": "sameeralam3127.linux_vitals.vitals_report"}},
             ]},
            {**common, "name": "Postcheck", "hosts": "linux_servers",
             "vars": {**common["vars"], "linux_vitals_phase": "postcheck"},
             "tasks": [
                 {"ansible.builtin.set_fact": {
                     "linux_vitals_result": "{{ demo_postcheck[inventory_hostname] }}",
                     "linux_vitals_auto_fixed_count": "{{ demo_postcheck[inventory_hostname].services_healed | length }}"}},
                 {"ansible.builtin.include_role": {"name": "sameeralam3127.linux_vitals.vitals_report"}},
             ]},
        ]
        (work / "demo.yml").write_text(yaml.safe_dump(plays, sort_keys=False))

        coll_root = work / "collections" / "ansible_collections" / "sameeralam3127"
        coll_root.mkdir(parents=True)
        (coll_root / "linux_vitals").symlink_to(collection.resolve(), target_is_directory=True)
        env = dict(os.environ,
                   ANSIBLE_COLLECTIONS_PATH=f"{work / 'collections'}{os.pathsep}{Path.home() / '.ansible' / 'collections'}",
                   ANSIBLE_LOCAL_TEMP=str(work / "tmp"), ANSIBLE_HOME=str(work / ".ansible"),
                   ANSIBLE_NOCOLOR="1", ANSIBLE_STDOUT_CALLBACK="default")
        subprocess.run(["ansible-playbook", "-i", "inventory.ini", "demo.yml", "--skip-tags", "notifications"], cwd=work, env=env,
                       check=True, stdin=subprocess.DEVNULL)

        shutil.copy(work / "reports" / "linux_vitals_report.html", SITE / "assets" / "demo-dashboard.html")
        report = json.loads((work / "reports" / "linux_vitals_report.json").read_text())
    finally:
        shutil.rmtree(work, ignore_errors=True)

    # The output paths name a throwaway temp dir; they mean nothing on the site.
    report["report"] = {"title": report["report"]["title"]}
    # The playground re-derives both runs' statuses under the visitor's own
    # threshold, so it needs the baseline findings as well as the postcheck's.
    report["baseline_findings"] = {h: r["findings"] for h, r in baseline.items()}
    galaxy = yaml.safe_load((collection / "galaxy.yml").read_text())
    (SITE / "assets" / "fleet.js").write_text(
        "// Generated by tools/build_demo.py -- do not edit by hand.\n"
        f"// The demo dashboard's postcheck report (collection {galaxy['version']}), built from the\n"
        "// collection's golden scan fixtures, plus each baseline host's findings.\n"
        f"window.LV_FLEET = {json.dumps(report, indent=1)};\n"
    )
    print("wrote assets/demo-dashboard.html and assets/fleet.js")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(Path(sys.argv[1]))
