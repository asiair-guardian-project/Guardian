"""Read-only commissioning evidence index; never approves commissioning."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from guardian_v1_commissioning_reconcile import reconcile, CHECKS

FINGERPRINT = "911dd714f44fbede7c72ce442d20b6345aec3061216a460f562e9dc0f546701f"
KEYWORDS = {
 "ASIAIR_MONITORING": ("asiair", "observation"),
 "OBSERVATORY_SAFETY": ("roof", "observatory", "alpaca"),
 "ASIAIR_SAFETY_POWER": ("asiair", "power"),
 "MOUNT_SAFETY_POWER": ("mount", "power"),
 "GUARDIAN_SURVIVAL": ("survival", "host", "protected"),
 "SIMULTANEOUS_PATHS": ("simultaneous", "integrated", "overnight"),
 "PROTECTION_LOGIC": ("abort", "recovery", "interlock", "protection", "commissioning"),
 "ACCESSORIES_SAFETY_POWER": ("accessor", "pegasus", "power"),
}
def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def compile_review(root, fingerprint):
    physical = reconcile(root, fingerprint)
    reports=[]
    for path in sorted(root.glob("acceptance_*.json")):
        try:
            data=json.loads(path.read_text())
        except (ValueError, OSError):
            continue
        if data.get("schema") != "guardian-acceptance-run-v1":
            continue
        if data.get("configuration_fingerprint_sha256") != fingerprint:
            continue
        counts=data.get("test_counts") or {}
        names=[f'{t.get("classname","")}.{t.get("name","")}' for t in data.get("tests",[]) if t.get("outcome")=="PASSED"]
        reports.append({"file":str(path),"sha256":digest(path),"counts":counts,"passed_test_names":names,
                        "source_junit_xml":data.get("source_junit_xml"),"source_sha256":data.get("source_sha256")})
    checks={}
    for check in CHECKS:
        hints=KEYWORDS[check]
        matches=[]
        for r in reports:
            selected=[n for n in r["passed_test_names"] if any(k in n.lower() for k in hints)]
            if selected:
                matches.append({"report":r["file"],"test_names":selected})
        checks[check]={"physical_assessment":physical["checks"][check]["assessment"],
                       "related_automated_test_leads":matches,
                       "formal_evidence_accepted":False,
                       "commissioning_result":"NOT_TESTED",
                       "review_required":True}
    return {"schema":"guardian-commissioning-review-dossier-v1",
            "generated_utc":datetime.now(timezone.utc).isoformat(),
            "fingerprint":fingerprint,"phase_b":{"outcome_file":physical["source"],
            "outcome_sha256":physical["source_sha256"],
            "consumed_file":physical["authorization_source"],
            "consumed_sha256":physical["authorization_sha256"],
            "verified_status":physical["physical_test_status"],
            "physical_roof_event":physical["physical_roof_event"]},
            "acceptance_reports":reports,"checks":checks,
            "operator_notes":["Phase B verifies physical power execution, not actual roof closure detection.",
              "Mount physically installed during Phase B: AM5 loaner; outlet 3 alias: Wave 150i.",
              "Monitoring LaunchAgent restored after Phase B; PID observed 44912.",
              "Earlier physical Phase A record exists; inspect separately if needed."],
            "commissioning_status":"NOT_AUTHORIZED",
            "production_audit_modified":False}
def render_md(d):
    lines=["# Guardian 1.0 — Commissioning evidence review dossier","",
      f'Generated UTC: {d["generated_utc"]}',f'Configuration fingerprint: `{d["fingerprint"]}`',
      "**Status: NOT AUTHORIZED — evidence index only, not an approval.**","",
      "## Phase B physical evidence",
      f'- Outcome: `{d["phase_b"]["verified_status"]}`; roof event: `{d["phase_b"]["physical_roof_event"]}`',
      f'- Journal: `{d["phase_b"]["outcome_file"]}`',
      f'- Journal SHA-256: `{d["phase_b"]["outcome_sha256"]}`',
      f'- Authorization consumption: `{d["phase_b"]["consumed_file"]}`',
      f'- Authorization SHA-256: `{d["phase_b"]["consumed_sha256"]}`',"",
      "## Automated evidence inventory",
      f'Found {len(d["acceptance_reports"])} matching acceptance reports (may include repeated test runs).',"",
      "| Check | Physical evidence | Matching test leads | Formal status |",
      "|---|---|---:|---|"]
    for key,v in d["checks"].items():
        n=sum(len(x["test_names"]) for x in v["related_automated_test_leads"])
        lines.append(f'| {key} | {v["physical_assessment"]} | {n} | REVIEW REQUIRED |')
    lines+=["","## Source report inventory"]
    for r in d["acceptance_reports"]:
        lines.append(f'- `{r["file"]}` — counts `{r["counts"]}`, SHA-256 `{r["sha256"]}`')
    lines+=["","## Outstanding acceptance decisions",
      "- Review actual test assertions and observational records against each check's acceptance criteria; name matches are leads, not proof.",
      "- Decide whether a real roof-closure-to-abort observation is required for OBSERVATORY_SAFETY.",
      "- Verify ASIAIR monitoring with prior live evidence and Guardian survival after emergency power loss.",
      "- Reconcile installed AM5 loaner with the Wave 150i outlet alias; review configuration fingerprint implications.",
      "- Only an explicitly approved commissioning workflow may mark checks VERIFIED or enable hardware execution.","",
      "## Operator notes"]
    lines += [f"- {note}" for note in d["operator_notes"]]
    lines += ["","This document does not modify Guardian's production audit, recovery file, ARM state, or power outlets.",""]
    return "\n".join(lines)
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--reports-dir",type=Path,default=Path("commissioning_reports"))
    ap.add_argument("--fingerprint",default=FINGERPRINT)
    args=ap.parse_args()
    data=compile_review(args.reports_dir,args.fingerprint)
    dest=args.reports_dir/"commissioning_review"
    dest.mkdir(exist_ok=True)
    json_path=dest/"evidence_dossier_20261029.json"
    md_path=dest/"evidence_dossier_20261029.md"
    if json_path.exists() or md_path.exists():
        raise FileExistsError("Dossier already exists; will not overwrite audit evidence")
    json_path.write_text(json.dumps(data,indent=2,sort_keys=True)+"\n")
    md_path.write_text(render_md(data))
    print(f"DOSSIER_JSON={json_path.resolve()}")
    print(f"DOSSIER_MARKDOWN={md_path.resolve()}")
    print(f"ACCEPTANCE_REPORTS={len(data['acceptance_reports'])}")
    print("COMMISSIONING_STATUS=NOT_AUTHORIZED; PRODUCTION_AUDIT=UNCHANGED; HARDWARE_COMMANDS=0")
if __name__=="__main__":
    main()
