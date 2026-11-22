#!/usr/bin/env python3
"""Build and run the production Preferences panel in a private iOS Simulator app."""
from __future__ import annotations

import argparse
import json
import os
import platform
import plistlib
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

UI_DIR = Path(__file__).resolve().parent
ROOT = UI_DIR.parents[1]
PREFERENCES = ROOT / "Preferences" / "SQCCMPreferences.m"
HOST = UI_DIR / "SQCCMTestPreferencesHost.m"
TESTS = UI_DIR / "SQCCMTestPanelRunner.m"
BUNDLE_ID = "com.minis.saoqiangccmedia.tests"
EXECUTABLE = "SQCCMTestApp"
DEPLOYMENT = "15.0"
FRAMEWORKS = ("Foundation", "UIKit", "Photos", "PhotosUI", "AVFoundation", "UniformTypeIdentifiers", "ImageIO", "CoreFoundation", "CoreMedia", "QuartzCore", "CoreGraphics")
EXPECTED_CASES = 8


def emit(message: str) -> None:
    print(message, flush=True)


def checked(args: list[object], *, timeout: int = 120, cwd: Path | None = None) -> str:
    command = [str(arg) for arg in args]
    try:
        result = subprocess.run(command, cwd=cwd, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or ""
        if isinstance(output, bytes):
            output = output.decode(errors="replace")
        raise TimeoutError(f"command timed out after {timeout}s: {' '.join(command)}\n{output}") from exc
    if result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(command)}\n{result.stdout}")
    return result.stdout.strip()


def streamed(args: list[object], log_path: Path, *, timeout: int = 300) -> str:
    command = [str(arg) for arg in args]
    emit("$ " + " ".join(command))
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, bufsize=1, errors="replace")
    assert process.stdout is not None
    lines: queue.Queue[str | None] = queue.Queue()

    def reader() -> None:
        try:
            for line in process.stdout:
                lines.put(line)
        finally:
            lines.put(None)

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    captured: list[str] = []
    finished = False
    started = time.monotonic()
    with log_path.open("w", encoding="utf-8") as log:
        while not finished or process.poll() is None:
            if time.monotonic() - started > timeout:
                process.kill()
                process.wait()
                raise TimeoutError(f"command timed out after {timeout}s: {' '.join(command)}")
            try:
                line = lines.get(timeout=0.2)
            except queue.Empty:
                continue
            if line is None:
                finished = True
                continue
            captured.append(line)
            log.write(line)
            log.flush()
            sys.stdout.write(line)
            sys.stdout.flush()
    thread.join(timeout=1)
    if process.returncode:
        raise RuntimeError(f"command failed ({process.returncode}): {' '.join(command)}")
    return "".join(captured).strip()


def parse_version(value: str) -> tuple[int, ...]:
    match = re.match(r"^(\d+(?:\.\d+)*)", value)
    if not match:
        return ()
    return tuple(int(part) for part in match.group(1).split("."))


def choose_simulator(sdk_version: str, runtimes: dict, devices: dict) -> tuple[str, str, str]:
    sdk = parse_version(sdk_version)
    installed = [runtime for runtime in runtimes.get("runtimes", [])
                 if runtime.get("isAvailable") and runtime.get("identifier", "").startswith("com.apple.CoreSimulator.SimRuntime.iOS-")]
    installed = [runtime for runtime in installed if parse_version(runtime.get("version", "")) <= sdk]
    installed.sort(key=lambda runtime: parse_version(runtime.get("version", "")), reverse=True)
    for runtime in installed:
        candidates = [device for device in devices.get("devices", {}).get(runtime["identifier"], [])
                      if device.get("isAvailable") and "iphone" in device.get("name", "").lower()]
        if candidates:
            candidates.sort(key=lambda device: device.get("name", ""))
            device_type = candidates[0].get("deviceTypeIdentifier")
            if device_type:
                return runtime["identifier"], device_type, runtime["version"]
    raise RuntimeError("no available iPhone simulator device/runtime compatible with the selected simulator SDK")


def validate_result(result: object, run_token: str) -> dict:
    if not isinstance(result, dict):
        raise RuntimeError("simulator produced no valid JSON result")
    if result.get("runToken") != run_token:
        raise RuntimeError("simulator result token does not belong to this run")
    if result.get("status") != "PASS":
        raise RuntimeError(f"UIKit test status was not PASS: {result.get('status')!r}")
    checks = result.get("checks")
    if isinstance(checks, bool) or not isinstance(checks, int) or checks <= 0:
        raise RuntimeError("UIKit test result has zero or invalid checks")
    cases = result.get("completedCases")
    if isinstance(cases, bool) or not isinstance(cases, int) or cases < EXPECTED_CASES:
        raise RuntimeError(f"UIKit test result is incomplete: completedCases={cases!r}")
    failures = result.get("failures")
    if not isinstance(failures, list) or failures:
        raise RuntimeError(f"UIKit test failures are not empty: {failures!r}")
    expected_mode = "real-uikit-public-frameworks-test-only-preferences-substitute"
    if result.get("mode") != expected_mode:
        raise RuntimeError(f"unexpected test mode: {result.get('mode')!r}")
    return result


def write_plist(path: Path, value: dict) -> None:
    path.write_bytes(plistlib.dumps(value, fmt=plistlib.FMT_XML, sort_keys=False))


def compile_app(work: Path, report: Path, run_token: str) -> Path:
    app = work / f"{EXECUTABLE}.app"
    app.mkdir(parents=True)
    resources = app  # iOS flat bundle; bundleForClass must resolve original resources.
    info = {
        "CFBundleIdentifier": BUNDLE_ID,
        "CFBundleExecutable": EXECUTABLE,
        "CFBundleName": "SaoqiangCCMedia UIKit Tests",
        "CFBundleDisplayName": "Panel Tests",
        "CFBundlePackageType": "APPL",
        "CFBundleVersion": "1",
        "CFBundleShortVersionString": "1.0",
        "MinimumOSVersion": DEPLOYMENT,
        "LSRequiresIPhoneOS": True,
        "UILaunchScreen": {},
        "UIRequiredDeviceCapabilities": ["arm64"],
    }
    write_plist(app / "Info.plist", info)
    resource_names = ("Root.plist", "Icon.png", "ListIcon.png", "ListIcon@2x.png", "ListIcon@3x.png")
    for name in resource_names:
        source = UI_DIR / name
        if not source.is_file():
            raise RuntimeError(f"required original preference resource missing: {source}")
        shutil.copy2(source, resources / name)

    sdk = checked(["xcrun", "--sdk", "iphonesimulator", "--show-sdk-path"])
    sdk_version = checked(["xcrun", "--sdk", "iphonesimulator", "--show-sdk-version"])
    clang = checked(["xcrun", "--sdk", "iphonesimulator", "--find", "clang"])
    if platform.machine().lower() not in ("arm64", "aarch64"):
        raise RuntimeError("this runner requires an Apple Silicon host to execute the required arm64 simulator binary")
    target = f"arm64-apple-ios{DEPLOYMENT}-simulator"
    sources = (PREFERENCES, HOST, TESTS)
    objects: list[Path] = []
    for index, source in enumerate(sources):
        if not source.is_file():
            raise RuntimeError(f"required test source missing: {source}")
        obj = work / f"panel-{index}.o"
        command = [clang, "-fobjc-arc", "-fblocks", "-fmodules", "-target", target,
                   "-isysroot", sdk, f"-mios-simulator-version-min={DEPLOYMENT}",
                   "-Wall", "-Wextra", "-Wno-unused-parameter", "-Wno-deprecated-declarations",
                   "-DTHEOS_PACKAGE_SCHEME_ROOTHIDE=1",
                   f'-DSQCCM_TEST_RUN_TOKEN=@"{run_token}"',
                   "-I", UI_DIR / "include", "-I", ROOT / "Shared", "-c", source, "-o", obj]
        streamed(command, report / f"compile-{index}.log", timeout=300)
        objects.append(obj)
    binary = app / EXECUTABLE
    link = [clang, "-fobjc-arc", "-fblocks", "-target", target, "-isysroot", sdk,
            f"-mios-simulator-version-min={DEPLOYMENT}", *objects]
    for framework in FRAMEWORKS:
        link.extend(("-framework", framework))
    link.extend(("-o", binary))
    streamed(link, report / "link.log", timeout=300)
    codesign = shutil.which("codesign")
    if not codesign:
        raise RuntimeError("codesign is required to install the simulator app")
    streamed([codesign, "--force", "--sign", "-", "--timestamp=none", app], report / "codesign.log")
    return app


def tail_file(path: Path, offset: int) -> int:
    try:
        with path.open("rb") as file:
            file.seek(offset)
            content = file.read()
    except FileNotFoundError:
        return offset
    if content:
        text = content.decode(errors="replace")
        sys.stdout.write(text)
        sys.stdout.flush()
    return offset + len(content)


def execute(args: argparse.Namespace) -> int:
    if sys.platform != "darwin" or not shutil.which("xcrun"):
        emit("ERROR: iOS Simulator UIKit tests require macOS and Xcode; this is not a PASS.")
        return 77
    if not os.environ.get("DEVELOPER_DIR"):
        raise RuntimeError("DEVELOPER_DIR must be selected by the caller (expected Xcode 16.4)")
    report = Path(args.output).expanduser()
    if not report.is_absolute():
        report = ROOT / report
    report.mkdir(parents=True, exist_ok=True)
    run_token = uuid.uuid4().hex
    simulator_id = None
    console = None
    work = Path(tempfile.mkdtemp(prefix="sqccm-panel-ui-"))
    try:
        xcode = checked(["xcodebuild", "-version"])
        emit(f"Selected developer directory: {os.environ['DEVELOPER_DIR']}")
        emit(xcode)
        sdk_version = checked(["xcrun", "--sdk", "iphonesimulator", "--show-sdk-version"])
        runtimes = json.loads(checked(["xcrun", "simctl", "list", "runtimes", "--json"]))
        devices = json.loads(checked(["xcrun", "simctl", "list", "devices", "available", "--json"]))
        runtime_id, device_type, runtime_version = choose_simulator(sdk_version, runtimes, devices)
        emit(f"Using available iOS Simulator runtime {runtime_version}, device type {device_type}")
        app = compile_app(work, report, run_token)

        name = f"SQCCMPanel-{run_token[:10]}"
        simulator_id = checked(["xcrun", "simctl", "create", name, device_type, runtime_id], timeout=120).strip()
        streamed(["xcrun", "simctl", "boot", simulator_id], report / "simulator-boot.log", timeout=180)
        streamed(["xcrun", "simctl", "bootstatus", simulator_id, "-b"], report / "simulator-bootstatus.log", timeout=300)
        checked(["xcrun", "simctl", "install", simulator_id, app], timeout=180)
        console_path = report / "simulator-console.log"
        console_file = console_path.open("wb")
        console = subprocess.Popen(["xcrun", "simctl", "spawn", simulator_id, "log", "stream",
                                    "--style", "compact", "--level", "info",
                                    "--predicate", f'process == "{EXECUTABLE}"'],
                                   stdout=console_file, stderr=subprocess.STDOUT)
        checked(["xcrun", "simctl", "launch", simulator_id, BUNDLE_ID], timeout=60)
        container = Path(checked(["xcrun", "simctl", "get_app_container", simulator_id, BUNDLE_ID, "data"], timeout=60))
        result_path = container / "Documents" / "sqccm-uikit-result.json"
        deadline = time.monotonic() + args.timeout
        console_offset = 0
        last_progress = 0.0
        result = None
        while time.monotonic() < deadline:
            console_offset = tail_file(console_path, console_offset)
            if result_path.is_file():
                try:
                    result = json.loads(result_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    result = None
                if result is not None:
                    break
            if console and console.poll() is not None:
                raise RuntimeError(f"simulator unified log stream ended early (exit {console.returncode})")
            if time.monotonic() - last_progress >= 10:
                emit("Waiting for a complete UIKit result; simulator console is being captured.")
                last_progress = time.monotonic()
            time.sleep(0.4)
        console_offset = tail_file(console_path, console_offset)
        if result is None:
            raise TimeoutError(f"no UIKit JSON result before {args.timeout}s; see {console_path}")
        result = validate_result(result, run_token)
        (report / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        emit(f"PASS: {result['checks']} UIKit assertions across {result['completedCases']} cases; failures=[]")
        return 0
    finally:
        if console is not None:
            console.terminate()
            try:
                console.wait(timeout=8)
            except subprocess.TimeoutExpired:
                console.kill()
                console.wait()
        if simulator_id:
            try:
                checked(["xcrun", "simctl", "shutdown", simulator_id], timeout=60)
            except Exception as exc:
                emit(f"Cleanup note: simulator shutdown failed: {exc}")
            try:
                checked(["xcrun", "simctl", "delete", simulator_id], timeout=60)
                emit(f"Deleted runner-owned simulator {simulator_id}")
            except Exception as exc:
                emit(f"Cleanup error: failed deleting runner-owned simulator {simulator_id}: {exc}")
                raise
        shutil.rmtree(work, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="reports/uikit", help="report directory (relative to tests/ui by default)")
    parser.add_argument("--timeout", type=int, default=240, help="maximum seconds waiting for simulator results")
    args = parser.parse_args()
    if args.timeout < 1:
        parser.error("--timeout must be positive")
    try:
        return execute(args)
    except Exception as exc:
        emit(f"FAIL: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
