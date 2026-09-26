#!/usr/bin/env python3
"""
Negative tests for the Day 3 Terraform test suite.

Copies the configuration 16 times, injects one specific defect into each, and
asserts the matching check fires.

This exists because 21 of the 23 checks are static policy checks, and a static
check that silently matches nothing is indistinguishable from one that passes.
That is not hypothetical: while writing the Day 2 suite, a module-name
comparison error made nine checks vacuously pass, and nothing but injected
defects revealed it.

Run with:  python tests/negative_test.py
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent

GREEN, RED, YELLOW, BOLD, RESET = (
    "\033[32m", "\033[31m", "\033[33m", "\033[1m", "\033[0m",
)
if os.environ.get("NO_COLOR") or not sys.stdout.isatty():
    GREEN = RED = YELLOW = BOLD = RESET = ""

CASES: list[tuple[str, object, str]] = []


def case(name: str, expect: str):
    def wrap(fn):
        CASES.append((name, fn, expect))
        return fn
    return wrap


def _root_vars(root: Path) -> Path:
    return root / "variables.tf"


@case("variable missing its description", "has no description")
def _(root: Path) -> None:
    p = _root_vars(root)
    p.write_text(p.read_text(encoding="utf-8").replace(
        'variable "project_name" {\n  description = "Short project identifier used in resource names and tags. Lowercase, no separators."\n',
        'variable "project_name" {\n', 1), encoding="utf-8")


@case("variable missing its type", "has no type")
def _(root: Path) -> None:
    p = _root_vars(root)
    p.write_text(p.read_text(encoding="utf-8").replace(
        'variable "project_name" {\n  description = "Short project identifier used in resource names and tags. Lowercase, no separators."\n  type        = string\n',
        'variable "project_name" {\n  description = "Short project identifier used in resource names and tags. Lowercase, no separators."\n', 1),
        encoding="utf-8")


@case("output missing its description", "has no description")
def _(root: Path) -> None:
    p = root / "outputs.tf"
    p.write_text(p.read_text(encoding="utf-8").replace(
        'output "cluster_api_endpoint" {\n  description = "K3s API server endpoint, reachable from the control node."\n',
        'output "cluster_api_endpoint" {\n', 1), encoding="utf-8")


@case("module outputs.tf deleted", "is missing")
def _(root: Path) -> None:
    (root / "modules" / "network-bridge" / "outputs.tf").unlink()


@case("provider version constraint removed", "has no version constraint")
def _(root: Path) -> None:
    p = root / "versions.tf"
    p.write_text(p.read_text(encoding="utf-8").replace(
        '      source  = "hashicorp/random"\n      version = "~> 3.6"\n',
        '      source  = "hashicorp/random"\n', 1), encoding="utf-8")


@case("module required_version removed", "no required_version")
def _(root: Path) -> None:
    p = root / "modules" / "k3s-server" / "versions.tf"
    p.write_text(p.read_text(encoding="utf-8").replace(
        'required_version = ">= 1.9.0, < 2.0.0"\n', "", 1), encoding="utf-8")


@case("backend switched to local", "backend is 'local'")
def _(root: Path) -> None:
    p = root / "providers.tf"
    p.write_text(p.read_text(encoding="utf-8").replace(
        'backend "s3" {}', 'backend "local" {}', 1), encoding="utf-8")


@case("commented-out local backend fallback", "state split")
def _(root: Path) -> None:
    p = root / "providers.tf"
    p.write_text(p.read_text(encoding="utf-8") + '\n# backend "local" {\n# }\n',
                 encoding="utf-8")


@case("secret variable not marked sensitive", "is not sensitive")
def _(root: Path) -> None:
    p = root / "modules" / "k3s-server" / "variables.tf"
    p.write_text(p.read_text(encoding="utf-8").replace(
        "  sensitive   = true\n", "", 1), encoding="utf-8")


@case("hardcoded secret in a .tf file", "hardcoded credential")
def _(root: Path) -> None:
    # Inject into locals.tf, which is where common_tags lives, and insert a new
    # line rather than rewriting an existing one. Matching on
    # '  ManagedBy   = "terraform"' broke the moment terraform fmt re-aligned
    # the '=' signs.
    p = root / "locals.tf"
    text = p.read_text(encoding="utf-8")
    text = re.sub(r'(common_tags = \{\n)',
                  r'\1    ApiKey = "abcd1234efgh5678"\n', text, count=1)
    p.write_text(text, encoding="utf-8")


@case("module source pointing at a missing directory", "not found")
def _(root: Path) -> None:
    p = root / "main.tf"
    p.write_text(p.read_text(encoding="utf-8").replace(
        'source = "./modules/network-bridge"', 'source = "./modules/ghost-module"', 1),
        encoding="utf-8")


@case("state no longer gitignored", "no rule line")
def _(root: Path) -> None:
    p = root / ".gitignore"
    lines = [ln for ln in p.read_text(encoding="utf-8").splitlines()
             if ln.strip() != "*.tfstate"]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")


@case("provisioner on a managed resource", "use terraform_data")
def _(root: Path) -> None:
    # Must target a resource that actually carries a provisioner. Renaming
    # local_file.inventory does nothing, because that resource has none, so the
    # check correctly stayed silent and the case looked like a miss.
    p = root / "modules" / "k3s-server" / "main.tf"
    p.write_text(p.read_text(encoding="utf-8").replace(
        'resource "terraform_data" "bootstrap" {',
        'resource "null_resource" "bootstrap" {', 1), encoding="utf-8")


@case("for_each given a list", "for_each")
def _(root: Path) -> None:
    # Caught by terraform validate, not by a static check. See the note in
    # run_tests.py on why no regex check exists for this.
    p = root / "modules" / "k3s-server" / "main.tf"
    p.write_text(p.read_text(encoding="utf-8").replace(
        "for_each = toset(var.node_names)", "for_each = var.node_names", 1),
        encoding="utf-8")


@case("local-exec without an interpreter", "without an interpreter")
def _(root: Path) -> None:
    p = root / "modules" / "k3s-server" / "main.tf"
    p.write_text(p.read_text(encoding="utf-8").replace(
        '    interpreter = ["/bin/bash", "-c"]\n', "", 1), encoding="utf-8")


@case("unescaped bash expansion in a heredoc", "unescaped bash expansion")
def _(root: Path) -> None:
    p = root / "modules" / "network-bridge" / "main.tf"
    p.write_text(p.read_text(encoding="utf-8").replace(
        '"$ADDRESS/$${CIDR#*/}"', '"$ADDRESS/${CIDR#*/}"', 1), encoding="utf-8")


@case("unescaped bash expansion in a template", "unescaped bash expansion")
def _(root: Path) -> None:
    p = root / "modules" / "k3s-server" / "templates" / "bootstrap.sh.tftpl"
    p.write_text(p.read_text(encoding="utf-8").replace(
        'sh -s - "$${flags[@]}"', 'sh -s - "${flags[@]}"', 1), encoding="utf-8")


@case("security variable loses its validation", "no validation block")
def _(root: Path) -> None:
    # Scoped to the variable's own block, then the validation block removed from
    # within it. The previous whole-file regex was fragile in two ways: it
    # assumed a fixed indentation, and a non-matching substitution left the file
    # untouched, which reads as an undetected defect rather than a broken case.
    p = _root_vars(root)
    text = p.read_text(encoding="utf-8")
    start = text.index('variable "allow_insecure_images"')
    end = text.index("\n}\n", start) + 3
    block = text[start:end]
    cleaned = re.sub(r'\n[ ]*validation \{.*?\n[ ]*\}\n', '\n', block, flags=re.S)
    if cleaned == block:
        raise AssertionError(
            "mutation did not change anything; the fixture drifted from the check"
        )
    p.write_text(text[:start] + cleaned + text[end:], encoding="utf-8")


@case("lab tfvars enables insecure images", "allow_insecure_images = true")
def _(root: Path) -> None:
    # Regex-based because 'terraform fmt' re-aligns the '=' in tfvars files, so
    # an exact multi-space match breaks as soon as the suite is run after fmt.
    p = root / "environments" / "lab" / "terraform.tfvars"
    text = re.sub(r'allow_insecure_images\s*=\s*false',
                  'allow_insecure_images = true', p.read_text(encoding="utf-8"), count=1)
    p.write_text(text, encoding="utf-8")


@case("local_file without file_permission", "no file_permission")
def _(root: Path) -> None:
    p = root / "main.tf"
    p.write_text(p.read_text(encoding="utf-8").replace(
        '  file_permission = "0644"\n', "", 1), encoding="utf-8")


@case("broken HCL syntax", "")
def _(root: Path) -> None:
    # expect is empty on purpose: any failure satisfies this case, because
    # detecting broken HCL is terraform's job and the exact diagnostic text is
    # terraform's to change.
    p = root / "locals.tf"
    p.write_text(p.read_text(encoding="utf-8") + "\nthis is not valid hcl {{{\n",
                 encoding="utf-8")


def run_suite(root: Path) -> tuple[int, str]:
    env = dict(os.environ)
    env["TF_LAB_ROOT"] = str(root)
    env["NO_COLOR"] = "1"
    proc = subprocess.run(
        [sys.executable, str(root / "tests" / "run_tests.py")],
        capture_output=True, text=True, env=env, cwd=str(root),
    )
    return proc.returncode, proc.stdout + proc.stderr


def main() -> int:
    print(f"\n{BOLD}Day 3 test suite - negative tests{RESET}")
    print(f"  {len(CASES)} injected defects, each must be caught\n")

    with tempfile.TemporaryDirectory() as tmp:
        clean = Path(tmp) / "clean"
        shutil.copytree(
            PROJECT, clean,
            ignore=shutil.ignore_patterns(".git", ".terraform", "artifacts",
                                          "__pycache__", "*.tfstate*"),
        )
        code, out = run_suite(clean)
        if code != 0:
            print(f"{RED}Baseline FAILED{RESET} - the clean configuration does not pass.")
            print(out[-2500:])
            return 1
        print(f"  {GREEN}ok{RESET}    baseline: clean configuration passes\n")

    undetected: list[str] = []
    wrong: list[str] = []

    for name, mutate, expect in CASES:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "cfg"
            shutil.copytree(
                PROJECT, root,
                ignore=shutil.ignore_patterns(".git", ".terraform", "artifacts",
                                              "__pycache__", "*.tfstate*"),
            )
            mutate(root)
            code, out = run_suite(root)

            if code == 0:
                undetected.append(f"{name}: not detected")
                status, colour, msg = "MISS", RED, "not detected"
            elif expect and expect not in out:
                wrong.append(f"{name}: failed, but not via {expect!r}")
                status, colour, msg = "WRONG", YELLOW, f"not via '{expect}'"
            else:
                status, colour, msg = "ok", GREEN, "detected"
            print(f"  {name:<48} {colour}{status}{RESET}  {colour}{msg}{RESET}")

    total = len(CASES)
    print(f"\n  detected : {GREEN}{total - len(undetected) - len(wrong)}/{total}{RESET}")

    if undetected or wrong:
        if undetected:
            print(f"\n{RED}Not detected{RESET}")
            for u in undetected:
                print(f"  - {u}")
        if wrong:
            print(f"\n{YELLOW}Detected by the wrong check{RESET}")
            for w in wrong:
                print(f"  - {w}")
        print()
        return 1

    print(f"\n{GREEN}All {total} injected defects were caught by the expected check.{RESET}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
