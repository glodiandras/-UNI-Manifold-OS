"""scripts/crawl_all.sh: the unattended runner around ``download.py --crawl``.

The script is a shell around the CLIs, so these tests check what the shell
itself decides - how many rounds it runs, what it retries, when it gives up,
and that its lock, background mode and --stop behave. The interpreter it calls
is replaced (MSP_PYTHON) by a stub that records every command and answers from
a plan. Nothing is downloaded and no network is used.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from conftest import real_project_root  # noqa: F401 - fixture used by name

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")

URL = "https://zanza.tv/irodalom"

# Stands in for "$PY scripts/<name>.py ...". Only the detach helper of
# --background (python -c ...) is handed to the real interpreter.
STUB = r'''
import json
import os
import sys
import time

state = os.environ["STUB_STATE"]
args = sys.argv[1:]
if args[:1] == ["-c"]:
    os.execv(sys.executable, [sys.executable] + args)

with open(os.path.join(state, "plan.json"), encoding="utf-8") as handle:
    plan = json.load(handle)
with open(os.path.join(state, "calls.jsonl"), "a", encoding="utf-8") as handle:
    handle.write(json.dumps(args) + "\n")

script = os.path.basename(args[0]) if args else ""
if script == "download.py" and "--check" in args:
    print("yt-dlp        : yes (stub)")
    print("JS runtime    : node")
    print()
    print("log_dir      : " + os.path.join(state, "logs"))
elif script == "transcribe.py" and "--list-backends" in args:
    print("subtitles        available")
    print("faster_whisper   " + ("available" if plan.get("asr", True) else "unavailable - not installed"))
elif script == "download.py" and "--crawl" in args:
    counter = os.path.join(state, "rounds")
    done = int(open(counter).read()) if os.path.exists(counter) else 0
    with open(counter, "w") as handle:
        handle.write(str(done + 1))
    step = plan["rounds"][min(done, len(plan["rounds"]) - 1)]
    time.sleep(step.get("sleep", 0))
    print(step.get("out", ""))
    sys.exit(step.get("code", 0))
elif script == "transcribe.py":
    sys.exit(plan.get("transcribe", 0))
elif script == "validate.py":
    sys.exit(plan.get("validate", 0))
else:
    sys.exit(99)
'''


class Project:
    """A throwaway checkout holding a copy of the script, plus the stub's state."""

    def __init__(self, tmp_path: Path, source: Path) -> None:
        self.root = tmp_path / "project"
        (self.root / "scripts").mkdir(parents=True)
        self.script = self.root / "scripts" / "crawl_all.sh"
        shutil.copy2(source, self.script)
        self.status_script = self.root / "scripts" / "crawl_status.sh"
        shutil.copy2(source.parent / "crawl_status.sh", self.status_script)
        self.state = tmp_path / "state"
        self.state.mkdir()
        self.tmp = tmp_path
        (tmp_path / "stub.py").write_text(STUB, encoding="utf-8")
        # A wrapper, not a shebang: the interpreter's path may contain spaces.
        self.python = tmp_path / "python"
        self.python.write_text(
            f'#!/bin/sh\nexec "{sys.executable}" "{tmp_path / "stub.py"}" "$@"\n', encoding="utf-8")
        self.python.chmod(0o755)
        self.lock = self.state / "logs" / "crawl_all.lock"

    def plan(self, **plan) -> None:
        (self.state / "plan.json").write_text(json.dumps(plan), encoding="utf-8")

    def env(self) -> dict[str, str]:
        env = {key: value for key, value in os.environ.items() if key != "CRAWL_ALL_LOG"}
        env.update(MSP_PYTHON=str(self.python), STUB_STATE=str(self.state), TMPDIR=str(self.tmp))
        return env

    def run(self, *args: str, timeout: float = 30) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(self.script), *args], cwd=self.tmp, env=self.env(),
                              capture_output=True, text=True, timeout=timeout)

    def status(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(self.status_script), *args], cwd=self.tmp, env=self.env(),
                              capture_output=True, text=True, timeout=30)

    def commands(self) -> list[str]:
        path = self.state / "calls.jsonl"
        if not path.exists():
            return []
        calls = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        return [" ".join([os.path.basename(call[0]), *call[1:]]) for call in calls]

    def rounds(self) -> int:
        return sum(1 for command in self.commands() if "--crawl" in command.split())

    def logs(self) -> str:
        return "".join(path.read_text(encoding="utf-8")
                       for path in sorted((self.state / "logs").glob("crawl_all-*.log")))


@pytest.fixture
def project(tmp_path, real_project_root):  # noqa: F811
    project = Project(tmp_path, real_project_root / "scripts" / "crawl_all.sh")
    yield project
    # A background run that a failing test left behind must not outlive it.
    try:
        os.killpg(int((project.lock / "pid").read_text()), signal.SIGKILL)
    except (OSError, ValueError):
        pass


def wait_for(condition, timeout: float = 20.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.1)
    return False


def summary(*, downloaded: int, skipped: int, failed: int) -> str:
    return (f"Downloaded: {downloaded}\nSkipped: {skipped}\nFailed: {failed}\n"
            f"Total: {downloaded + skipped + failed}")


# --- rounds -----------------------------------------------------------------

def test_one_clean_round_then_transcripts_and_the_check(project):
    project.plan(rounds=[{"code": 0, "out": summary(downloaded=3, skipped=0, failed=0)}])
    result = project.run(URL)
    assert result.returncode == 0, result.stdout + result.stderr
    assert project.commands() == [
        "download.py --check",
        "transcribe.py --list-backends",
        f"download.py --crawl --max-items 500 {URL}",
        "transcribe.py --pending",
        "validate.py --repair-archive",
    ]
    assert "OK - every video found is staged" in result.stdout
    assert "Downloaded: 3" in project.logs()
    assert not project.lock.exists()


def test_failed_videos_get_another_round(project):
    project.plan(rounds=[
        {"code": 1, "out": summary(downloaded=3, skipped=0, failed=2)},
        {"code": 0, "out": summary(downloaded=2, skipped=3, failed=0)},
    ])
    result = project.run("--pause", "0", URL)
    assert result.returncode == 0, result.stdout + result.stderr
    assert project.rounds() == 2
    assert "some videos failed - next round in 0s" in result.stdout


def test_gives_up_when_the_rounds_run_out(project):
    failing = (summary(downloaded=0, skipped=4, failed=1)
               + "\n\nFailed items:\n  https://zanza.tv/irodalom/x/y\n    not publicly accessible")
    project.plan(rounds=[{"code": 1, "out": failing}])
    result = project.run("--pause", "0", "--retries", "2", URL)
    assert result.returncode == 1
    assert project.rounds() == 3
    # what did get staged is still transcribed and checked
    assert project.commands()[-2:] == ["transcribe.py --pending", "validate.py --repair-archive"]
    report = result.stdout.split("==== Summary ====")[1]
    assert "https://zanza.tv/irodalom/x/y" in report
    assert "NOT COMPLETE - 1 video(s) failed in every round" in report


def test_unreadable_pages_get_another_round(project):
    project.plan(rounds=[
        {"code": 0, "out": f"Crawl found 5 video page(s) under {URL} (9 pages read, 1 unreadable)"},
        {"code": 0, "out": f"Crawl found 6 video page(s) under {URL} (3 pages read)"},
    ])
    result = project.run("--pause", "0", URL)
    assert result.returncode == 0, result.stdout + result.stderr
    assert project.rounds() == 2


def test_pages_that_stay_unreadable_are_not_reported_as_complete(project):
    project.plan(rounds=[
        {"code": 0, "out": f"Crawl found 5 video page(s) under {URL} (9 pages read, 1 unreadable)"},
    ])
    result = project.run("--pause", "0", "--retries", "1", URL)
    assert result.returncode == 1
    assert project.rounds() == 2
    assert "NOT COMPLETE - some pages could not be read" in result.stdout
    assert "OK - " not in result.stdout


def test_an_error_that_waiting_cannot_fix_is_not_retried(project):
    project.plan(rounds=[{"code": 65, "out": f"ERROR: No video page found under {URL}"}])
    result = project.run("--pause", "0", URL)
    assert result.returncode == 65
    assert project.rounds() == 1
    assert not any(command.startswith(("transcribe.py --pending", "validate.py"))
                   for command in project.commands())
    assert "STOPPED - download.py ended with exit code 65" in result.stdout


def test_failed_transcripts_make_the_run_fail(project):
    project.plan(rounds=[{"code": 0}], transcribe=1)
    result = project.run(URL)
    assert result.returncode == 1
    assert "Some transcripts failed" in result.stdout


# --- pre-flight and options -------------------------------------------------

def test_refuses_to_start_without_speech_to_text(project):
    project.plan(asr=False, rounds=[{"code": 0}])
    result = project.run(URL)
    assert result.returncode == 69
    assert "no speech-to-text backend" in result.stderr
    assert project.rounds() == 0


def test_dry_run_only_plans(project):
    project.plan(asr=False, rounds=[{"code": 1}])
    result = project.run("--dry-run", "--max-items", "7", URL)
    assert result.returncode == 1
    assert project.commands() == [
        "download.py --check",
        f"download.py --crawl --max-items 7 --dry-run {URL}",
    ]
    assert "Dry run: nothing was downloaded." in result.stdout


@pytest.mark.parametrize("args", [(), ("--retries", "two", URL), ("--nope", URL)])
def test_usage_errors(project, args):
    project.plan(rounds=[{"code": 0}])
    result = project.run(*args)
    assert result.returncode == 64
    assert project.commands() == []


# --- lock, background, stop -------------------------------------------------

def test_a_second_run_is_refused_while_one_is_in_progress(project):
    holder = subprocess.Popen(["bash", "-c", "sleep 30; :", "crawl_all.sh"])
    try:
        project.lock.mkdir(parents=True)
        (project.lock / "pid").write_text(str(holder.pid))
        project.plan(rounds=[{"code": 0}])
        result = project.run(URL)
        assert result.returncode == 75
        assert f"in progress (PID {holder.pid})" in result.stderr
        assert project.rounds() == 0
    finally:
        holder.kill()
        holder.wait()


def test_a_lock_left_by_a_dead_run_is_taken_over(project):
    dead = subprocess.Popen(["true"])
    dead.wait()
    project.lock.mkdir(parents=True)
    (project.lock / "pid").write_text(str(dead.pid))
    project.plan(rounds=[{"code": 0}])
    result = project.run(URL)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not project.lock.exists()


def test_stop_without_a_run(project):
    project.plan(rounds=[{"code": 0}])
    result = project.run("--stop")
    assert result.returncode == 0
    assert "No crawl_all.sh run is in progress." in result.stdout


def test_background_run_detaches_logs_and_stops(project):
    project.plan(rounds=[{"code": 0, "sleep": 30}])
    result = project.run("--background", URL)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Started in the background" in result.stdout
    assert wait_for(lambda: project.rounds() == 1), project.logs()
    assert wait_for(lambda: (project.lock / "pid").exists())

    stop = project.run("--stop")
    assert stop.returncode == 0
    assert "Stopped the run with PID" in stop.stdout
    assert wait_for(lambda: not project.lock.exists()), project.logs()
    assert "Stopped. Nothing is lost" in project.logs()
    # stopped mid-crawl: nothing after the crawl ran
    assert not any(command.startswith("validate.py") for command in project.commands())


def test_stop_ends_a_foreground_run_but_not_its_log(project):
    # Started like this, the run shares the process group of whoever started
    # it (here: pytest), so --stop must end the run alone - not that group.
    project.plan(rounds=[{"code": 0, "sleep": 30}])
    run = subprocess.Popen(["bash", str(project.script), URL], cwd=project.tmp, env=project.env(),
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        assert wait_for(lambda: project.rounds() == 1)
        stop = project.run("--stop")
        assert f"Stopped the run with PID {run.pid}" in stop.stdout
        output, _ = run.communicate(timeout=20)
        assert run.returncode == 143
        assert "Stopped. Nothing is lost" in output
        assert "Stopped. Nothing is lost" in project.logs()
        assert not project.lock.exists()
    finally:
        if run.poll() is None:
            run.kill()
            run.wait()


# --- crawl_status.sh --------------------------------------------------------

def test_status_shows_the_summary_of_a_finished_run(project):
    project.plan(rounds=[{"code": 0}])
    logs = project.state / "logs"
    logs.mkdir()
    (logs / "crawl_all-20260919-000000.log").write_text(
        "==== Round 1/3 - download.py --crawl  (00:00) ====\n"
        "==== Summary ====\n"
        f"pages   : {URL}\n\n"
        "OK - every video found is staged with its transcript, and the staging tree is valid.\n",
        encoding="utf-8")
    result = project.status()
    assert result.returncode == 0, result.stderr
    assert "fut:          nem" in result.stdout
    assert "OK - every video found is staged" in result.stdout


def test_status_of_a_run_in_progress(project):
    project.plan(rounds=[{"code": 0}])
    logs = project.state / "logs"
    logs.mkdir()
    (logs / "crawl_all-20260919-000000.log").write_text("\n".join([
        "==== Round 1/3 - download.py --crawl  (00:00) ====",
        f"Crawl found 5 video page(s) under {URL} (7 pages read)",
        "Crawl: 4 to stage, 1 already staged",
        f"[1/4] {URL}/a/egy",
        "Downloading: Egy",
        "OK: Egy -> Zanza/Irodalom/Egy",
        f"[2/4] {URL}/a/ketto",
        "ERROR: FAILED Kettő: Download failed: ERROR: unable to download video data: HTTP Error 403",
        f"[3/4] {URL}/a/harom",
        "Downloading: Három",
        "    transcribed 00:01:00 / 00:05:00  (20%)",
    ]) + "\n", encoding="utf-8")
    (logs / "pipeline-2026-09-19.log").write_text(
        "2026-09-19 00:00:00,000 INFO     msp Crawl: 4 to stage, 1 already staged\n"
        "2026-09-19 00:02:00,000 INFO     msp OK: Egy -> Zanza/Irodalom/Egy\n"
        "2026-09-19 00:04:00,000 ERROR    msp FAILED Kettő: Download failed\n",
        encoding="utf-8")
    holder = subprocess.Popen(["bash", "-c", "sleep 30; :", "crawl_all.sh"])
    try:
        project.lock.mkdir()
        (project.lock / "pid").write_text(str(holder.pid))
        out = project.status().stdout
    finally:
        holder.kill()
        holder.wait()
    assert f"igen (PID {holder.pid})" in out
    assert "talált:       5 videó, ebből 1 már korábban kész volt, 4 letöltendő" in out
    assert "kész:         1/4, sikertelen: 1" in out
    assert "most:         [3/4] Három (transcript: 20%)" in out
    assert "még 2 videó, átlag 2 perc 0 mp/videó" in out
    assert "    - Kettő: Download failed" in out
