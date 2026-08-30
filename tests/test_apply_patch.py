"""ghostc apply-patch: ghost PR diff -> real PR diff, fail closed on ambiguity."""
from __future__ import annotations

import subprocess

import pytest
from click.testing import CliRunner

from ghostc.cli import main
from ghostc.patch import Rejection, reverse_patch
from tests.conftest import load_jsonl

pytestmark = pytest.mark.usefixtures("real_repo")


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return str(p)


GHOST_DIFF = """\
diff --git a/src/integrations/internalServices.js b/src/integrations/internalServices.js
--- a/src/integrations/internalServices.js
+++ b/src/integrations/internalServices.js
@@ -20,3 +20,4 @@ const SERVICES = {
 function resolve(serviceKey) {
   const svc = SERVICES[serviceKey];
+  console.log(`base ${process.env.SERVICE_A_URL} for serviceA at service-a.internal`);
   return svc.url;
"""


def test_round_trip_translation(tmp_path, compiled, privacy_yaml):
    res = reverse_patch(_write(tmp_path, "g.diff", GHOST_DIFF), str(compiled.mapping),
                        config_path=str(privacy_yaml),
                        audit_path=str(tmp_path / "a.jsonl"))
    assert "process.env.BOOKING_CORE_URL" in res.real_diff
    assert "bookingCore" in res.real_diff
    assert "booking-core.internal" in res.real_diff
    assert "service-a" not in res.real_diff and "SERVICE_A" not in res.real_diff
    assert "svc_booking_core" in res.entities_resolved


def test_translates_renamed_path_in_the_headers(tmp_path, compiled, privacy_yaml):
    diff = (
        "diff --git a/src/integrations/vendorAClient.js b/src/integrations/vendorAClient.js\n"
        "--- a/src/integrations/vendorAClient.js\n"
        "+++ b/src/integrations/vendorAClient.js\n"
        "@@ -1,1 +1,2 @@\n"
        " const VENDOR_A_BASE_URL = process.env.VENDOR_A_BASE_URL;\n"
        "+const extra = 1;\n"
    )
    res = reverse_patch(_write(tmp_path, "g.diff", diff), str(compiled.mapping),
                        config_path=str(privacy_yaml), audit_path=str(tmp_path / "a.jsonl"))
    assert "skyRouteClient.js" in res.real_diff          # identifier/path casing round-trips
    assert "vendorAClient.js" not in res.real_diff
    assert "VENDOR_A" not in res.real_diff               # env-var token reversed (casing may differ)
    assert "vendor_skyroute" in res.entities_resolved


def test_rejects_unmapped_alias(tmp_path, compiled, privacy_yaml):
    diff = GHOST_DIFF.replace("serviceA at service-a.internal", "serviceZ at service-z.internal")
    with pytest.raises(Rejection, match="unmapped ghost-alias-shaped token"):
        reverse_patch(_write(tmp_path, "g.diff", diff), str(compiled.mapping),
                      config_path=str(privacy_yaml), audit_path=str(tmp_path / "a.jsonl"))


def test_rejects_real_value_present_in_the_ghost_diff(tmp_path, compiled, privacy_yaml):
    diff = GHOST_DIFF.replace("base ${process.env.SERVICE_A_URL}",
                              "base for Northwind Airlines")
    with pytest.raises(Rejection, match="unexpected real entity"):
        reverse_patch(_write(tmp_path, "g.diff", diff), str(compiled.mapping),
                      config_path=str(privacy_yaml), audit_path=str(tmp_path / "a.jsonl"))


def test_rejects_mapping_version_mismatch(tmp_path, compiled, privacy_yaml):
    with pytest.raises(Rejection, match="mapping-version mismatch"):
        reverse_patch(_write(tmp_path, "g.diff", GHOST_DIFF), str(compiled.mapping),
                      config_path=str(privacy_yaml), mapping_version=999,
                      audit_path=str(tmp_path / "a.jsonl"))


def test_rejection_audit_carries_no_cleartext(tmp_path, compiled, privacy_yaml, seed_entities):
    diff = GHOST_DIFF.replace("base ${process.env.SERVICE_A_URL}", "base for Northwind Airlines")
    audit = tmp_path / "a.jsonl"
    with pytest.raises(Rejection):
        reverse_patch(_write(tmp_path, "g.diff", diff), str(compiled.mapping),
                      config_path=str(privacy_yaml), audit_path=str(audit))
    events = [r["event"] for r in load_jsonl(audit)]
    assert events == ["patch.rejected"]
    raw = audit.read_text()
    for e in seed_entities:
        assert e["real"] not in raw


def test_apply_lands_on_a_branch_in_the_real_repo(tmp_path, compiled, privacy_yaml, real_repo):
    real = tmp_path / "real"
    subprocess.run(["git", "init", "-q", str(real)], check=True)
    for src in real_repo.rglob("*"):
        if src.is_file() and ".git" not in src.parts:
            dst = real / src.relative_to(real_repo)
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(src.read_bytes())
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    subprocess.run(["git", "-C", str(real), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(real), "commit", "-qm", "base"], check=True,
                   env={**__import__("os").environ, **env})

    # a real ghost edit -> ghost diff
    f = compiled.ghost / "src" / "integrations" / "internalServices.js"
    f.write_text(f.read_text().replace(
        "function resolve(serviceKey) {",
        "function resolve(serviceKey) {\n  console.log(process.env.SERVICE_A_URL);"))
    ghost_diff = subprocess.run(["git", "-C", str(compiled.ghost), "diff"],
                                capture_output=True, text=True, check=True).stdout

    res = reverse_patch(_write(tmp_path, "g.diff", ghost_diff), str(compiled.mapping),
                        config_path=str(privacy_yaml), real_repo=str(real),
                        do_apply=True, branch="test/rev", audit_path=str(tmp_path / "a.jsonl"))
    assert res.applied and res.branch == "test/rev"
    applied = (real / "src" / "integrations" / "internalServices.js").read_text()
    assert "process.env.BOOKING_CORE_URL" in applied
    events = [r["event"] for r in load_jsonl(tmp_path / "a.jsonl")]
    assert "patch.applied" in events and "patch.parsed" in events


def test_cli_apply_patch_is_not_a_stub(tmp_path, compiled, privacy_yaml):
    res = CliRunner().invoke(main, [
        "apply-patch", "--ghost-diff", _write(tmp_path, "g.diff", GHOST_DIFF),
        "--mapping", str(compiled.mapping), "--config", str(privacy_yaml),
        "--out", str(tmp_path / "real.diff"), "--audit", str(tmp_path / "a.jsonl"),
    ])
    assert res.exit_code == 0, res.output
    assert "entities resolved" in res.output
    assert "BOOKING_CORE_URL" in (tmp_path / "real.diff").read_text()
