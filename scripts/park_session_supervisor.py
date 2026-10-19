#!/usr/bin/env python3
"""Keep private browser hosting alive while switching fresh native park sessions."""

import argparse
import json
import os
import re
import shutil
import signal
import socket
import socketserver
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from prepare_existing_defense import prepare
from scenario_package import ROOT, build_native_map, ensure_park, session_environment


PARK_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_. -]{0,119}\.park$")


class ParkSessionSupervisor:
    def __init__(self, library: Path, runtime: Path, initial: str = "", start_browser=True):
        self.library = library.resolve(strict=True)
        self.runtime = runtime.resolve()
        if not self.library.is_dir() or not self.runtime.is_relative_to((ROOT / "run-data").resolve()):
            raise ValueError("park library must exist and runtime must be inside run-data")
        self.initial = initial
        self.lock = threading.RLock()
        self.phase = "preparing" if initial else "idle"
        self.current = ""
        self.generation = ""
        self.pending = ""
        self.error = ""
        self.session = None
        self.transition_thread = None
        self.plan = None
        self.browser = None
        self.start_browser = start_browser
        self.socket_path = self.runtime / "control.sock"
        self.runtime.mkdir(parents=True, exist_ok=True)
        if initial and initial not in self.catalog():
            raise ValueError("initial park is not in the private library")
        selection = self.runtime / "active-park.json"
        if initial and selection.is_file():
            try:
                saved = json.loads(selection.read_text()).get("park")
                if saved in self.catalog():
                    self.initial = saved
            except (ValueError, OSError, TypeError):
                pass

    def persist_current(self):
        path = self.runtime / "active-park.json"
        temporary = path.with_suffix(".json.tmp")
        try:
            temporary.write_text(json.dumps({"park": self.current}) + "\n")
            os.replace(temporary, path)
        except OSError as error:
            print("supervisor: could not record active park: " + str(error), flush=True)
            temporary.unlink(missing_ok=True)

    def catalog(self):
        parks = {}
        for candidate in self.library.iterdir():
            if not PARK_NAME.fullmatch(candidate.name) or candidate.is_symlink() or not candidate.is_file():
                continue
            if candidate.resolve().parent != self.library:
                continue
            parks[candidate.name] = candidate
        return dict(sorted(parks.items(), key=lambda item: item[0].lower()))

    def state(self):
        with self.lock:
            return {"phase": self.phase, "current": self.current, "generation": self.generation,
                    "pending": self.pending, "error": self.error[:240],
                    "parks": list(self.catalog())}

    def ready_session_exited(self):
        with self.lock:
            return self.phase == "ready" and self.session is not None and self.session.poll() is not None

    def source_for(self, name):
        source = self.catalog().get(name)
        if source is None:
            raise ValueError("park_not_in_private_library")
        saved = self.runtime / "saved" / name
        return saved if saved.is_file() else source

    def prepare(self, name):
        generation = uuid.uuid4().hex
        directory = self.runtime / "sessions" / generation
        plan = prepare(str(self.source_for(name)), directory)
        ensure_park(plan)
        build_native_map(plan)
        self.preflight_native_map(generation, plan)
        return generation, plan

    def preflight_native_map(self, generation, plan):
        # Run the actual three-participant synchronization in a private network
        # namespace. OpenBW rebuilds its regions after the park collision mask
        # arrives, so loading the .scm in isolation cannot validate navigation.
        preflight = dict(plan)
        directory = self.runtime / "sessions" / generation / "preflight"
        preflight["spawn_journal"] = str(directory / "spawn-queue.json")
        preflight["server_data"] = str(directory / "server")
        preflight["client_data"] = str(directory / "client")
        environment = session_environment(preflight, {
            "BRIDGE_RUNTIME_DIR": str(ROOT / "run-data/ps" / generation[:16] / "check"),
            "BRIDGE_SERVER_DATA_DIR": preflight["server_data"],
            "BRIDGE_CLIENT_DATA_DIR": preflight["client_data"],
            "BRIDGE_PARK_SUPERVISOR_SOCKET": "", "BRIDGE_PARK_GENERATION": "",
            "BRIDGE_SERVE_WASM": "0", "BRIDGE_LAUNCH_CLIENT": "0",
        })
        log_path = directory / "session.log"
        directory.mkdir(parents=True, exist_ok=True)
        with log_path.open("ab", buffering=0) as log:
            process = subprocess.Popen(["unshare", "-Urn", str(ROOT / "scripts/run-isolated-world-preflight.sh"),
                                        plan["park"]], cwd=ROOT, env=environment,
                                       stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            self.await_ready(process, log_path, timeout=150)
        finally:
            self.stop(process)

    def start_wasm(self):
        if not self.start_browser:
            return
        bundle = Path(os.environ.get("WASM_DEPLOY_DIR", str(ROOT / "run-data/wasm-deploy"))) / "current"
        if not (bundle / "manifest.json").is_file():
            raise RuntimeError("private WASM bundle is missing")
        command = [str(ROOT / "build/wasm-server"), "--bundle", str(bundle),
                   "--listen", os.environ.get("WASM_LISTEN_ADDRESS", "127.0.0.1:8091"),
                   "--native", "127.0.0.1:" + os.environ.get("OPENRCT2_PORT", "11753"),
                   "--rct2-data-path", str(Path(os.environ.get("RCT2_DATA_DIR", str(Path.home() / "games/rct2"))).resolve()),
                   "--supervisor-socket", str(self.socket_path)]
        log = (self.runtime / "wasm-server.log").open("ab", buffering=0)
        self.browser = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                        start_new_session=True)
        log.close()

    def launch(self, generation, plan):
        environment = session_environment(plan, {
            # OpenBW's Unix socket names must fit the platform's short sun_path.
            "BRIDGE_RUNTIME_DIR": str(ROOT / "run-data/ps" / generation[:16]),
            "BRIDGE_SERVER_DATA_DIR": plan["server_data"],
            "BRIDGE_CLIENT_DATA_DIR": plan["client_data"],
            "BRIDGE_PARK_SUPERVISOR_SOCKET": str(self.socket_path),
            "BRIDGE_PARK_GENERATION": generation,
            "BRIDGE_SERVE_WASM": "0", "BRIDGE_LAUNCH_CLIENT": "0",
        })
        log_path = self.runtime / "sessions" / generation / "session.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log = log_path.open("ab", buffering=0)
        process = subprocess.Popen([str(ROOT / "scripts/run-world-session.sh"), plan["park"]],
                                   cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        log.close()
        return process, log_path

    def await_ready(self, process, log_path, timeout=150):
        deadline = time.monotonic() + timeout
        marker = b"WORLD_SCENARIO_STATUS scenario="
        while time.monotonic() < deadline:
            if process.poll() is not None:
                lines = log_path.read_text(errors="replace").splitlines()[-20:]
                errors = [line for line in lines if "Error:" in line or "WORLD_ERROR" in line]
                raise RuntimeError("native session exited before readiness: "
                                   + (errors[-1] if errors else "see " + str(log_path)))
            if log_path.exists() and marker in log_path.read_bytes():
                return
            time.sleep(.3)
        raise RuntimeError("new game session did not synchronize both OpenBW participants")

    @staticmethod
    def stop(process):
        if process is None or process.poll() is not None:
            return
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=12)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)

    def start_initial(self):
        if not self.initial:
            return
        process = None
        try:
            generation, plan = self.prepare(self.initial)
            with self.lock:
                self.phase = "starting"
            process, log_path = self.launch(generation, plan)
            self.session = process
            self.await_ready(process, log_path)
            with self.lock:
                self.session, self.plan = process, plan
                self.generation, self.current, self.phase = generation, self.initial, "ready"
                self.persist_current()
        except BaseException as error:
            self.stop(process)
            with self.lock:
                self.phase, self.error = "failed", str(error)
            raise

    def request(self, park, decision, generation, save_name=""):
        with self.lock:
            if self.phase != "ready":
                raise ValueError("park_transition_busy")
            if generation != self.generation:
                raise ValueError("stale_park_generation")
            if park not in self.catalog():
                raise ValueError("park_not_in_private_library")
            if decision not in ("save", "discard"):
                raise ValueError("select_save_or_discard")
            if decision == "save" and (not re.fullmatch(r"starcoaster-switch-[0-9a-f]{16}\.park", save_name)):
                raise ValueError("invalid_save_name")
            self.phase, self.pending, self.error = "preparing", park, ""
        self.transition_thread = threading.Thread(target=self.transition,
                                                  args=(park, decision, save_name))
        self.transition_thread.start()
        return self.state()

    def archive_save(self, name, save_name):
        source = Path(self.plan["server_data"]) / "save" / save_name
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and (not source.is_file() or source.stat().st_size < 4):
            time.sleep(.2)
        if not source.is_file():
            raise RuntimeError("authoritative_park_save_missing")
        with source.open("rb") as stream:
            signature = stream.read(4)
        if signature != b"PARK":
            raise RuntimeError("authoritative_park_save_missing")
        destination = self.runtime / "saved" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(".park.tmp")
        shutil.copy2(source, temporary)
        os.replace(temporary, destination)

    def transition(self, park, decision, save_name):
        old_name, old_process, old_plan = self.current, self.session, self.plan
        try:
            generation, plan = self.prepare(park)
            if decision == "save":
                self.archive_save(old_name, save_name)
            with self.lock:
                self.phase = "switching"
            self.stop(old_process)
            with self.lock:
                self.phase = "starting"
            process, log_path = self.launch(generation, plan)
            try:
                self.await_ready(process, log_path)
            except Exception:
                self.stop(process)
                raise
            with self.lock:
                self.session, self.plan = process, plan
                self.generation, self.current = generation, park
                self.pending, self.phase = "", "ready"
                self.persist_current()
        except Exception as error:
            with self.lock:
                self.phase, self.error = "failed", str(error)
            if old_process.poll() is None:
                with self.lock:
                    self.phase, self.pending = "ready", ""
                return
            try:
                generation, plan = self.prepare(old_name)
                with self.lock:
                    self.phase = "starting"
                process, log_path = self.launch(generation, plan)
                self.await_ready(process, log_path)
                with self.lock:
                    self.session, self.plan = process, plan
                    self.generation, self.current = generation, old_name
                    self.pending, self.phase = "", "ready"
                    self.error = "new park failed; restored prior park: " + self.error
                    self.persist_current()
            except Exception as recovery:
                with self.lock:
                    self.error += "; recovery failed: " + str(recovery)

    def close(self):
        if self.transition_thread is not None and self.transition_thread.is_alive():
            self.transition_thread.join()
        self.stop(self.session)
        self.stop(self.browser)


class ThreadedUnixServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/state":
            self.send_error(404)
            return
        self.answer(200, self.server.supervisor.state())

    def do_POST(self):
        if self.path != "/load":
            self.send_error(404)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size < 1 or size > 4096:
                raise ValueError("invalid_request_size")
            request = json.loads(self.rfile.read(size))
            result = self.server.supervisor.request(request.get("park"), request.get("decision"),
                                                    request.get("generation"), request.get("save_name", ""))
            self.answer(202, result)
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            self.answer(400, {"error": str(error)})

    def answer(self, status, value):
        data = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        print("supervisor: " + format % args, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parks", type=Path, required=True, help="private directory containing eligible .park files")
    parser.add_argument("--initial", default="", help="optional development park filename within --parks")
    parser.add_argument("--runtime", type=Path, default=ROOT / "run-data/park-supervisor")
    args = parser.parse_args()
    supervisor = ParkSessionSupervisor(args.parks, args.runtime, args.initial)
    if supervisor.socket_path.exists():
        supervisor.socket_path.unlink()
    server = ThreadedUnixServer(str(supervisor.socket_path), Handler)
    server.supervisor = supervisor
    os.chmod(supervisor.socket_path, 0o600)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    def terminate(_signal, _frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, terminate)
    try:
        supervisor.start_wasm()
        supervisor.start_initial()
        while supervisor.browser is None or supervisor.browser.poll() is None:
            # A transition intentionally stops the old session before the new
            # one is ready. Only a stopped session in the ready phase is fatal.
            if supervisor.ready_session_exited():
                raise RuntimeError("native game session exited")
            time.sleep(.5)
        raise RuntimeError("private browser server exited")
    except KeyboardInterrupt:
        pass
    finally:
        supervisor.close()
        server.shutdown()
        server.server_close()
        supervisor.socket_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
