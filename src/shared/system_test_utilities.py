import json
import os
import pathlib
import pytest
import re
import subprocess
import sys
import threading
import time


class GrpcServerProcess:
    def __init__(self, config_file_path):
        server_exe = self._get_grpc_server_exe()
        self._proc = subprocess.Popen([str(server_exe), config_file_path], stdout=subprocess.PIPE)

        # Read/parse output until we find the port number or the process exits; discard the rest.
        try:
            self.server_port = None
            while self.server_port is None and self._proc.poll() is None:
                line = self._proc.stdout.readline()
                match = re.search(rb"Server listening on port (\d+)", line)
                if match:
                    self.server_port = int(match.group(1))

            if self._proc.poll() is not None:
                raise RuntimeError(f"Server exited with return code {self._proc.returncode}")

            self._stdout_thread = threading.Thread(target=self._discard_output, args=(self._proc.stdout,), daemon=True)
            self._stdout_thread.start()
        except Exception:
            self._proc.kill()
            raise

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._proc.kill()

    def _get_grpc_server_exe(self):
        if os.name != "nt":
            pytest.skip("Only supported on Windows")
        import winreg
        try:
            reg = winreg.ConnectRegistry(None, winreg.HKEY_LOCAL_MACHINE)
            read64key = winreg.KEY_READ | winreg.KEY_WOW64_64KEY
            with winreg.OpenKey(reg, r"SOFTWARE\National Instruments\Common\Installer", access=read64key) as key:
                shared_dir, _ = winreg.QueryValueEx(key, "NISHAREDDIR64")
        except OSError:
            pytest.skip("NI gRPC Device Server not installed")
        server_exe = pathlib.Path(shared_dir) / "NI gRPC Device Server" / "ni_grpc_device_server.exe"
        if not server_exe.exists():
            pytest.skip("NI gRPC Device Server not installed")
        return server_exe

    def _discard_output(self, stdout):
        while True:
            data = stdout.read(8196)
            if not data:
                return


def impl_test_multi_threading_lock_unlock(session):
    t1_lock_engaged = threading.Event()
    release_t1_lock = threading.Event()

    def lock_wait_unlock():
        session.lock()
        t1_lock_engaged.set()
        assert session.instrument_manufacturer != ''
        release_t1_lock.wait()
        session.unlock()

    def lock_unlock():
        session.lock()
        assert session.instrument_model != ''
        session.unlock()

    # test that lock, unlock functions work properly
    t1 = threading.Thread(target=lock_wait_unlock)
    t2 = threading.Thread(target=lock_unlock)

    t1.start()
    t2.start()

    t1_lock_engaged.wait()
    time.sleep(2.0)
    # t1 is blocked by the release event, t2 should be blocked by t1's lock
    assert t2.is_alive()
    release_t1_lock.set()
    t2.join()

    assert not t1.is_alive()
    assert not t2.is_alive()

def impl_test_multi_threading_ivi_synchronized_wrapper_releases_lock(ivi_method_to_call):
    # test that the 2nd thread doesn't hang
    t1 = threading.Thread(target=ivi_method_to_call)
    t2 = threading.Thread(target=ivi_method_to_call)

    t1.start()
    t1.join()
    assert not t1.is_alive()

    t2.start()
    t2.join()
    assert not t2.is_alive()


def exchange_certificates(
    server_host: str,
    server_user: str | None = None,
    client_host: str | None = None,
    client_user: str | None = None,
    verbosity: int = 2,
):
    script_path = (
        r"C:/NITests/nitlsconfigtest/exchange_certificates.py"
        if sys.platform == "win32" else
        r"/opt/NITests/nitlsconfigtest/exchange_certificates.py"
    )
    if not pathlib.Path(script_path).is_file():
        raise FileNotFoundError(f"Certificate exchange script not found: {script_path}")

    server_host_arg = f"--server-host={server_host}"
    server_user_arg = f"--server-user={server_user}" if server_user else "--local-server"
    client_host_arg = f"--client-host={client_host}" if client_host else None
    client_user_arg = f"--client-user={client_user}" if client_user else None

    verbosity = max(0, min(verbosity, 4))
    verbosity_arg = {
        0: "-qq",
        1: "-q",
        3: "-v",
        4: "-vv",
    }.get(verbosity)

    command = [sys.executable, str(pathlib.Path(script_path)), server_host_arg, server_user_arg]
    command.extend(arg for arg in (client_host_arg, client_user_arg, verbosity_arg) if arg is not None)
    subprocess.run(command, check=True)


def configure_tls_modes(
    service: str,
    server_host: str,
    server_user: str | None = None,
    client_host: str | None = None,
    client_user: str | None = None,
    server_cert_mode: str | None = None,
    server_client_mode: str | None = None,
    client_cert_mode: str | None = None,
    client_server_mode: str | None = None,
):
    script_path = (
        r"C:/NITests/nitlsconfigtest/configure_tls_modes.py"
        if sys.platform == "win32" else
        r"/opt/NITests/nitlsconfigtest/configure_tls_modes.py"
    )
    if not pathlib.Path(script_path).is_file():
        raise FileNotFoundError(f"Configure TLS modes script not found: {script_path}")

    service_arg = f"--service={service}"
    server_host_arg = f"--server-host={server_host}"
    server_user_arg = f"--server-user={server_user}" if server_user else "--local-server"
    client_host_arg = f"--client-host={client_host}" if client_host else None
    client_user_arg = f"--client-user={client_user}" if client_user else None
    server_cert_mode_arg = f"--server-certificate-mode={server_cert_mode}" if server_cert_mode else None
    server_client_mode_arg = f"--server-client-mode={server_client_mode}" if server_client_mode else None
    client_cert_mode_arg = f"--client-certificate-mode={client_cert_mode}" if client_cert_mode else None
    client_server_mode_arg = f"--client-server-mode={client_server_mode}" if client_server_mode else None

    command = [sys.executable, str(pathlib.Path(script_path)), service_arg, server_host_arg, server_user_arg]
    command.extend(
        arg
        for arg in (
            client_host_arg,
            client_user_arg,
            server_cert_mode_arg,
            server_client_mode_arg,
            client_cert_mode_arg,
            client_server_mode_arg,
        )
        if arg is not None
    )
    subprocess.run(command, check=True)


def write_grpc_device_server_config(use_tls_config: bool = True):
    config_path = (
        r"C:/Program Files/National Instruments/Shared/NI gRPC Device Server/server_config.json" 
        if sys.platform == "win32" else
        r"/etc/ni_grpc_device_server/server_config.json"
    )
    if not os.path.isfile(config_path):
        raise FileNotFoundError(f"NI gRPC Device Server config file not found: {config_path}")

    config = {
        "address": "[::]",
        "port": 31763,
    }
    if use_tls_config:
        config["security"] = "ni-tls-config"
        config["feature_toggles"] = {"ni-tls-config": True}

    with open(config_path, "w", encoding="utf-8") as config_file:
        json.dump(config, config_file, indent=4)
        config_file.write("\n")