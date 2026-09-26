#!/usr/bin/env python3
"""
Test suite for the Day 3 Terraform + K3s configuration.

Two layers:

  1. Real Terraform validation. `terraform fmt -check` and
     `terraform init -backend=false` + `terraform validate` are run against the
     actual configuration. This is genuine semantic validation of the module
     tree, and it is what caught five real defects while this was being written:
     an undeclared variable, a missing template, a list passed to for_each,
     bash array expansion being parsed as a Terraform expression, and a
     provisioner timeout that Terraform 1.16 rejects on terraform_data.

  2. Static checks for the things validate does not look at: whether every
     variable is documented, whether providers are pinned, whether state is
     ignored, whether anything sensitive is marked sensitive.

Run with:  python tests/run_tests.py
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(
    os.environ.get("TF_LAB_ROOT", Path(__file__).resolve().parent.parent)
).resolve()

GREEN, RED, YELLOW, CYAN, BOLD, RESET = (
    "\033[32m", "\033[33m", "\033[33m", "\033[36m", "\033[1m", "\033[0m",
)
if os.environ.get("NO_COLOR") or not sys.stdout.isatty():
    GREEN = RED = YELLOW = CYAN = BOLD = RESET = ""


class Results:
    def __init__(self) -> None:
        self.current = ""
        self.current_failed = False
        self.tests = 0
        self.assertions = 0
        self.failures: list[str] = []
        self.skipped: list[str] = []

    def it(self, name: str) -> None:
        self.flush()
        self.tests += 1
        self.current = name
        self.current_failed = False
        print(f"  {name:<66}", end="", flush=True)

    def ok(self) -> None:
        self.assertions += 1

    def no(self, detail: str) -> None:
        self.assertions += 1
        self.current_failed = True
        self.failures.append(f"{self.current}: {detail}")

    def skip(self, detail: str) -> None:
        self.flush()
        self.skipped.append(detail)
        print(f"{YELLOW}skip{RESET}  {detail}")

    def flush(self) -> None:
        if not self.current:
            return
        print(f"{RED}FAIL{RESET}" if self.current_failed else f"{GREEN}ok{RESET}")
        self.current = ""

    def truthy(self, cond, what: str) -> None:
        self.ok() if cond else self.no(what)

    def contains(self, haystack, needle, what: str) -> None:
        self.ok() if needle in haystack else self.no(f"{what}: {needle!r} not found")

    def absent(self, haystack, needle, what: str) -> None:
        self.ok() if needle not in haystack else self.no(f"{what}: {needle!r} present")

    def report(self) -> int:
        self.flush()
        failed = len(self.failures)
        print(f"\n{BOLD}Results{RESET}")
        print(f"  tests      : {self.tests}")
        print(f"  assertions : {GREEN}{self.assertions - failed}{RESET} passed, "
              f"{RED}{failed}{RESET} failed")
        if self.skipped:
            print(f"  skipped    : {YELLOW}{len(self.skipped)}{RESET}")
            for s in self.skipped:
                print(f"               - {s}")
        if self.failures:
            print(f"\n{BOLD}Failures{RESET}")
            for f in self.failures:
                print(f"  - {f}")
            print()
            return 1
        print(f"\n{GREEN}All {self.tests} checks passed.{RESET}\n")
        return 0


R = Results()


# ------------------------------------------------------------------ utilities

def tf_files() -> list[Path]:
    return sorted(p for p in ROOT.rglob("*.tf") if ".terraform" not in p.parts)


def module_dirs() -> list[Path]:
    mods = ROOT / "modules"
    return sorted(d for d in mods.iterdir() if d.is_dir()) if mods.is_dir() else []


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def blocks(text: str, kind: str) -> list[str]:
    """Return the bodies of top-level `kind "name" { ... }` blocks."""
    out = []
    for m in re.finditer(rf'^{kind}\s+"([^"]+)"\s*\{{', text, re.M):
        start = m.end()
        depth, i = 1, start
        while i < len(text) and depth:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        out.append(text[start:i - 1])
    return out


def has_attribute(block: str, name: str) -> bool:
    """
    True when `name = ...` is actually assigned in the block.

    A substring test for the bare word is satisfied by a comment that explains
    what the attribute is for. That is not hypothetical: the comment above
    variable.allow_insecure_images contains the word "validation", so a
    substring check reported the validation block as present after the negative
    test had deleted it. Every attribute check goes through here.

    Matches both the block form on its own line and the inline map form:
        description = "..."
        local = { source = "hashicorp/local", version = "~> 2.5" }
    """
    return re.search(rf'(?:^|[{{,])\s*{re.escape(name)}\s*=', block, re.M) is not None


def terraform_exe() -> str | None:
    return shutil.which("terraform") or shutil.which("terraform.exe")


def run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, cwd=str(cwd))


# ================================================== layer 1: real terraform

def check_terraform_fmt() -> None:
    R.it("terraform fmt -check -recursive")
    exe = terraform_exe()
    if not exe:
        R.skip("terraform not installed")
        return
    proc = run([exe, "fmt", "-check", "-recursive", "-no-color"], ROOT)
    R.truthy(proc.returncode == 0,
             f"run 'terraform fmt -recursive'. Unformatted:\n{proc.stdout}{proc.stderr}")


def check_terraform_validate() -> None:
    R.it("terraform init -backend=false succeeds")
    exe = terraform_exe()
    if not exe:
        R.skip("terraform not installed")
        return

    # validate needs the providers present, and a real backend would need
    # credentials this machine does not have. -backend=false gives a full
    # provider install without touching remote state.
    with tempfile.TemporaryDirectory() as tmp:
        # A scratch copy, so the repository never accumulates a .terraform
        # directory or a lock file as a side effect of being tested.
        work = Path(tmp) / "cfg"
        shutil.copytree(
            ROOT, work,
            ignore=shutil.ignore_patterns(".git", ".terraform", "artifacts",
                                          "scripts", "__pycache__"),
        )
        init = run([exe, "init", "-backend=false", "-input=false", "-no-color"], work)
        if init.returncode != 0:
            R.no(f"init failed:\n{(init.stderr or init.stdout)[-600:]}")
            return
        R.ok()

        R.it("terraform validate passes")
        val = run([exe, "validate", "-no-color"], work)
        R.truthy(val.returncode == 0,
                 f"validate failed:\n{(val.stderr or val.stdout)[-1200:]}")


# ============================================ layer 2: static policy checks

def check_every_variable_documented() -> None:
    R.it("every variable declares a type and a description")
    targets = [ROOT / "variables.tf"] + [d / "variables.tf" for d in module_dirs()]
    for path in targets:
        if not path.is_file():
            R.no(f"{path.relative_to(ROOT)} is missing")
            continue
        body = read(path)
        names = re.findall(r'^variable\s+"([^"]+)"\s*\{', body, re.M)
        R.truthy(bool(names), f"{path.relative_to(ROOT)} declares no variables")
        blocks_ = blocks(body, "variable")
        for name, blk in zip(names, blocks_):
            rel = path.relative_to(ROOT)
            R.truthy(has_attribute(blk, "description"),
                     f"{rel}: variable {name} has no description")
            R.truthy(has_attribute(blk, "type"),
                     f"{rel}: variable {name} has no type")


def check_every_output_documented() -> None:
    R.it("every output declares a description")
    targets = [ROOT / "outputs.tf"] + [d / "outputs.tf" for d in module_dirs()]
    for path in targets:
        if not path.is_file():
            R.no(f"{path.relative_to(ROOT)} is missing")
            continue
        body = read(path)
        names = re.findall(r'^output\s+"([^"]+)"\s*\{', body, re.M)
        R.truthy(bool(names), f"{path.relative_to(ROOT)} declares no outputs")
        for name, blk in zip(names, blocks(body, "output")):
            R.truthy(has_attribute(blk, "description"),
                     f"{path.relative_to(ROOT)}: output {name} has no description")


def check_providers_pinned() -> None:
    R.it("every required provider is version pinned")
    targets = [ROOT / "versions.tf"] + [d / "versions.tf" for d in module_dirs()]
    for path in targets:
        if not path.is_file():
            R.no(f"{path.relative_to(ROOT)} is missing")
            continue
        body = read(path)
        providers = re.findall(r'^\s*(\w+)\s*=\s*\{[^}]*?source\s*=\s*"[^"]+"', body, re.M)
        R.truthy(bool(providers), f"{path.relative_to(ROOT)} pins no providers")
        for m in re.finditer(r'(\w+)\s*=\s*\{([^}]*)\}', body, re.S):
            name, inner = m.group(1), m.group(2)
            if "source" not in inner:
                continue
            R.truthy(has_attribute(inner, "version"),
                     f"{path.relative_to(ROOT)}: provider {name} has no version constraint")
            v = re.search(r'version\s*=\s*"([^"]+)"', inner)
            if v:
                R.truthy(v.group(1) != "latest" and "~>" in v.group(1)
                         or v.group(1)[0].isdigit(),
                         f"{path.relative_to(ROOT)}: provider {name} is not pinned "
                         f"to a range ({v.group(1)})")


def check_required_version_declared() -> None:
    R.it("every module declares required_version")
    targets = [ROOT / "versions.tf"] + [d / "versions.tf" for d in module_dirs()]
    for path in targets:
        if not path.is_file():
            R.no(f"{path.relative_to(ROOT)} is missing")
            continue
        R.truthy("required_version" in read(path),
                 f"{path.relative_to(ROOT)} has no required_version")


def check_backend_is_remote() -> None:
    R.it("a remote state backend is configured, not local")
    text = read(ROOT / "providers.tf") if (ROOT / "providers.tf").is_file() else ""
    found = re.search(r'backend\s+"([^"]+)"', text)
    R.truthy(found is not None, "no backend block found")
    if found:
        R.truthy(found.group(1) != "local",
                 "backend is 'local'; two engineers will disagree about what exists")
    R.truthy('backend "s3" {}' in text.replace("\n", " "),
             "s3 backend should use partial configuration, with values in -backend-config")


def check_sensitive_marked() -> None:
    R.it("secret-bearing variables are marked sensitive")
    for path in [ROOT / "variables.tf"] + [d / "variables.tf" for d in module_dirs()]:
        if not path.is_file():
            continue
        for name, blk in zip(
            re.findall(r'^variable\s+"([^"]+)"\s*\{', read(path), re.M),
            blocks(read(path), "variable"),
        ):
            if re.search(r"token|password|secret|private_key", name, re.I):
                R.truthy(re.search(r'sensitive\s*=\s*true', blk) is not None,
                         f"{path.relative_to(ROOT)}: {name} looks secret but is not sensitive")
            else:
                R.ok()


def check_no_hardcoded_secrets() -> None:
    R.it("no .tf file contains a hardcoded secret")
    # The separator is optional so ApiKey, api_key and api-key all match.
    # Requiring the underscore missed the camelCase spelling, which is what a
    # copy-pasted vendor example tends to use.
    pattern = re.compile(
        r'(?i)\b(password|secret|token|private[_-]?key|api[_-]?key)\s*=\s*"([^"]{8,})"'
    )
    for path in tf_files():
        offenders = []
        for m in pattern.finditer(read(path)):
            value = m.group(2)
            if "${" in value:
                continue  # a reference, not a literal
            offenders.append(f"{m.group(1)} = {value[:14]}")
        R.truthy(not offenders,
                 f"{path.relative_to(ROOT)}: hardcoded credential(s): {offenders[:3]}")


def check_module_sources_exist() -> None:
    R.it("every local module source exists")
    for path in tf_files():
        for m in re.finditer(r'source\s*=\s*"(\./[^"]+)"', read(path)):
            target = (path.parent / m.group(1)).resolve()
            R.truthy(target.is_dir(), f"{path.relative_to(ROOT)}: module {m.group(1)} not found")


def check_gitignore_covers_state() -> None:
    R.it(".gitignore excludes state, .terraform and rendered artefacts")
    gi = ROOT / ".gitignore"
    if not gi.is_file():
        R.no(".gitignore is missing")
        return
    # Rule lines only, not substrings. Searching for "*.tfstate" anywhere in the
    # file is satisfied by "*.tfstate.*", which does not match a file named
    # terraform.tfstate, so a real state file would still be committable.
    #
    # Trailing slashes are stripped: "artifacts/" and "artifacts" are the same
    # rule, and requiring the bare form flagged a correct .gitignore.
    rules = {
        line.strip().rstrip("/")
        for line in read(gi).splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    for required in (".terraform", "*.tfstate", "*.tfplan", "artifacts"):
        R.truthy(required in rules,
                 f".gitignore has no rule line for {required!r}")


def check_rendered_scripts_gitignored() -> None:
    R.it("directories holding rendered scripts are gitignored")
    # Rule lines, not substrings. "scripts" appears in the explanatory comments
    # of this very .gitignore, so a substring search would pass on the comments
    # alone while the directory stayed trackable.
    gi = ROOT / ".gitignore"
    rules = {
        line.strip().rstrip("/")
        for line in (read(gi) if gi.is_file() else "").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    R.truthy(any(r in ("scripts", "**/scripts") for r in rules),
             ".gitignore has no rule line excluding the rendered script directories")


def check_terraform_data_used_for_provisioners() -> None:
    R.it("provisioners are attached to terraform_data, not to managed resources")
    # A provisioner on a real provider resource forces a taint on any change to
    # its arguments, which is why terraform_data exists.
    for path in tf_files():
        text = read(path)
        for m in re.finditer(r'^resource\s+"([^"]+)"\s+"([^"]+)"\s*\{', text, re.M):
            kind = m.group(1)
            start = m.end()
            depth, i = 1, start
            while i < len(text) and depth:
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                i += 1
            body = text[start:i - 1]
            if "provisioner" in body:
                R.truthy(kind == "terraform_data",
                         f"{path.relative_to(ROOT)}: {kind}.{m.group(2)} has a "
                         f"provisioner; use terraform_data to avoid resource taint")
            else:
                R.ok()


def check_no_local_fallback_backend() -> None:
    R.it("no commented-out local backend fallback")
    # Matches a commented-out backend *declaration*, not prose about backends.
    # A naive "comment mentioning backend and local" rule flags the line
    # "# The local backend is NOT a fallback", which is the opposite of the
    # thing being checked for.
    pattern = re.compile(r'^\s*#\s*(terraform\s*\{[^}]*)?backend\s+"local"', re.M)
    for path in tf_files():
        offenders = [
            f"{path.relative_to(ROOT)}:{n}"
            for n, line in enumerate(read(path).splitlines(), 1)
            if pattern.match(line)
        ]
        R.truthy(not offenders,
                 f"commented-out local backend invites a state split: {offenders}")


def check_interpreter_declared() -> None:
    R.it("local-exec provisioners declare a bash interpreter")
    for path in tf_files():
        text = read(path)
        for m in re.finditer(r'provisioner\s+"local-exec"\s*\{', text):
            start = m.end()
            depth, i = 1, start
            while i < len(text) and depth:
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                i += 1
            body = text[start:i - 1]
            R.truthy("interpreter" in body,
                     f"{path.relative_to(ROOT)}: local-exec without an interpreter "
                     f"defaults to /bin/sh")


def check_heredoc_escapes_bash_expansion() -> None:
    R.it("bash parameter expansion inside heredocs is escaped for Terraform")
    # "${flags[@]}" in a heredoc is read as a Terraform expression and fails
    # with "invalid character" on '['. It must be written "$${flags[@]}".
    for path in tf_files():
        text = read(path)
        offenders = []
        for m in re.finditer(r'<<-?EOT\b(.*?)\n\s*EOT', text, re.S):
            block = m.group(1)
            # Single-character negative lookbehind, not a two-character one.
            # For "$${CIDR#*/}" the candidate match starts at the second '$',
            # whose two preceding characters are '/' and '$', not '$$', so a
            # (?<!\$\$) guard lets it through and every correctly escaped
            # sequence is reported as unescaped.
            for bad in re.finditer(r'(?<!\$)\$\{[A-Za-z_][A-Za-z0-9_]*[#@%\[]', block):
                offenders.append(bad.group(0))
        R.truthy(not offenders,
                 f"{path.relative_to(ROOT)}: unescaped bash expansion in a heredoc: "
                 f"{offenders[:3]}. Terraform will try to evaluate it.")


def check_templates_have_no_unescaped_expansion() -> None:
    R.it("templates escape bash expansion for templatefile()")
    for tpl in sorted(ROOT.rglob("*.tftpl")):
        if ".terraform" in tpl.parts:
            continue
        text = read(tpl)
        offenders = [
            m.group(0)
            for m in re.finditer(r'(?<!\$)\$\{[A-Za-z_][A-Za-z0-9_]*[#@%\[]', text)
        ]
        R.truthy(not offenders,
                 f"{tpl.relative_to(ROOT)}: unescaped bash expansion: {offenders[:3]}")


def check_security_variables_have_validation() -> None:
    R.it("security-relevant variables carry validation blocks")
    text = read(ROOT / "variables.tf") if (ROOT / "variables.tf").is_file() else ""
    for name in ("allow_insecure_images", "k3s_version", "control_plane_nodes"):
        m = re.search(rf'variable\s+"{name}"\s*\{{(.*?)\n\}}', text, re.S)
        if not m:
            R.no(f"variable {name} not found")
            continue
        body = m.group(1)
        # Match the block, not the word. A substring test for "validation" is
        # satisfied by a comment explaining what validation is for, which is
        # exactly what the explanatory comment above this variable contains.
        R.truthy(re.search(r'^[ \t]*validation\s*\{', body, re.M) is not None,
                 f"{name} has no validation block")


def check_environments_exist() -> None:
    R.it("lab environment has a tfvars and a backend config")
    lab = ROOT / "environments" / "lab"
    R.truthy((lab / "terraform.tfvars").is_file(), "environments/lab/terraform.tfvars missing")
    R.truthy((lab / "backend.hcl").is_file(), "environments/lab/backend.hcl missing")
    if (lab / "terraform.tfvars").is_file():
        text = read(lab / "terraform.tfvars")
        R.truthy("allow_insecure_images" in text,
                 "lab tfvars does not pin allow_insecure_images explicitly")
        v = re.search(r'allow_insecure_images\s*=\s*(\S+)', text)
        if v:
            R.truthy(v.group(1) == "false",
                     f"lab tfvars sets allow_insecure_images = {v.group(1)}")


def check_no_env_example_commits_real_values() -> None:
    R.it("production example does not contain a real-looking value")
    ex = ROOT / "environments" / "production" / "terraform.tfvars.example"
    if not ex.is_file():
        R.skip("no production tfvars example")
        return
    text = read(ex)
    R.truthy("CHANGE-ME" in text, "project_name in the example is not a placeholder")
    R.truthy("access_key" not in text.lower(), "example appears to contain a credential")


def check_scripts_are_executable_mode() -> None:
    R.it("rendered files request restrictive or explicit permissions")
    for path in tf_files():
        text = read(path)
        for m in re.finditer(r'resource\s+"local_file"\s+"([^"]+)"\s*\{(.*?)\n\}', text, re.S):
            name, body = m.group(1), m.group(2)
            if not has_attribute(body, "filename"):
                continue
            R.truthy(has_attribute(body, "file_permission"),
                     f"{path.relative_to(ROOT)}: local_file.{name} has no file_permission")


def main() -> int:
    print(f"\n{BOLD}Day 3 Terraform + K3s - test suite{RESET}\n")

    check_terraform_fmt()
    check_terraform_validate()
    check_every_variable_documented()
    check_every_output_documented()
    check_providers_pinned()
    check_required_version_declared()
    check_backend_is_remote()
    check_sensitive_marked()
    check_no_hardcoded_secrets()
    check_module_sources_exist()
    check_gitignore_covers_state()
    check_rendered_scripts_gitignored()
    check_terraform_data_used_for_provisioners()
    # No static for_each check on purpose. Whether an expression is a list or a
    # set depends on the variable's declared type, which a regex cannot see.
    # terraform validate determines it exactly, and its error is unambiguous, so
    # a regex check here would only add false confidence.
    check_no_local_fallback_backend()
    check_interpreter_declared()
    check_heredoc_escapes_bash_expansion()
    check_templates_have_no_unescaped_expansion()
    check_security_variables_have_validation()
    check_environments_exist()
    check_no_env_example_commits_real_values()
    check_scripts_are_executable_mode()

    return R.report()


if __name__ == "__main__":
    sys.exit(main())
