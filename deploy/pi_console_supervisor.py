"""Fawkes Pi kiosk companion; application authentication and code stay intact.

Started inside its own dbus-run-session by the user service. Its browser,
keyring and handoff socket live in the private per-user runtime directory.
"""
import fcntl
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

from browser_pipe import ORIGIN, PipeBrowser, SetupError
from pi_shutdown_state import LocalShutdown, SaveError, THREAD
from pi_shutdown_browser import BrowserShutdown

ROOT = Path(__file__).resolve().parent
RUNTIME = Path("/run/user") / str(os.getuid())
STATE = RUNTIME / "fawkes-pi-console"
STATUS = STATE / "status.json"
ACCEPTED_BINDING = ROOT / "accepted-console.json"
credential_lock = threading.Lock()
credential = ""
credential_received = 0.0
last_status = None
credential_ready = threading.Event()


def status(state, message, *, browser_observation=None):
    global last_status
    value = {"state": state, "message": message, "time": int(time.time())}
    if browser_observation is not None:
        value['browser_observation'] = browser_observation
    temporary = STATUS.with_suffix(".new")
    temporary.write_text(json.dumps(value), encoding="utf-8")
    temporary.replace(STATUS)
    if last_status != state:
        print(state + ": " + message, flush=True)
        last_status = state


def ready_status(browser):
    # Observed browser identity, not merely the expected installed identity.
    # Old-preview compatibility can report READY, but is never accepted rollout proof.
    observation = browser.evaluate("""({origin: location.origin, path: location.pathname,
      context: document.querySelector('meta[name="fawkes-console-context"]')?.content || '',
      projection: document.querySelector('#dev-console')?.dataset.projectionState || ''})""")
    if (not isinstance(observation, dict) or set(observation) != {'origin','path','context','projection'}
            or any(not isinstance(v, str) or len(v) > 256 for v in observation.values())):
        raise SetupError('Browser readiness identity is unavailable.')
    status('READY', 'Summary opened; Matrix starts after two idle minutes.',
           browser_observation=observation)


def receive_credentials():
    global credential, credential_received
    path = STATE / "credential.sock"
    path.unlink(missing_ok=True)
    with socket.socket(socket.AF_UNIX) as server:
        server.bind(str(path))
        path.chmod(0o600)
        server.listen(2)
        credential_ready.set()
        while True:
            connection, _ = server.accept()
            with connection:
                try:
                    connection.settimeout(4)
                    peer = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
                    if struct.unpack("3i", peer)[1] != os.getuid():
                        continue
                    data = b""
                    while b"\n" not in data and len(data) < 65537:
                        part = connection.recv(4096)
                        if not part:
                            break
                        data += part
                    if len(data) > 65536 or not data.endswith(b"\n"):
                        continue
                    value = json.loads(data)
                    if not isinstance(value, dict):
                        continue
                    candidate = value.get("credential")
                    if not isinstance(candidate, str) or not candidate:
                        continue
                    with credential_lock:
                        credential = candidate
                        credential_received = time.monotonic()
                    connection.sendall(b"OK\n")
                except (ValueError, OSError):
                    pass


def get_credential():
    with credential_lock:
        # A stale bridge must not keep triggering failed sign-ins indefinitely.
        return credential if time.monotonic() - credential_received < 65 else ""


def preview_ready():
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(ORIGIN + "/", timeout=3) as response:
            page = response.read(32768).decode("utf-8", "replace")
            return (response.geturl() == ORIGIN + "/" and
                    'id="credential"' in page and
                    ("UNREVIEWED VISUALIZATION SUCCESSOR" in page or
                     "FAWKES MANAGED DEVELOPMENT CONSOLE" in page))
    except (OSError, ValueError):
        return False


def private_keyring(env, session):
    # This is a new private Secret Service, not the desktop's login keyring.
    # Its random password, encryption key and browser data are discarded when
    # the companion stops. No Pi login password is requested or stored.
    (session / "data/keyrings").mkdir(parents=True, mode=0o700)
    (session / "keyring").mkdir(mode=0o700)
    env.update(XDG_DATA_HOME=str(session / "data"),
               GNOME_KEYRING_CONTROL=str(session / "keyring"))
    secret = secrets.token_urlsafe(48).encode()
    result = subprocess.run(
        ["gnome-keyring-daemon", "--daemonize", "--unlock", "--components=secrets",
         "--control-directory=" + str(session / "keyring")],
        input=secret, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        timeout=15, env=env)
    secret = None
    if result.returncode:
        raise SetupError("The private browser keyring could not start.")
    # The freshly unlocked login collection is the default only on this bus.
    subprocess.run(
        ["gdbus", "call", "--session", "--dest", "org.freedesktop.secrets",
         "--object-path", "/org/freedesktop/secrets", "--method",
         "org.freedesktop.Secret.Service.SetAlias", "default",
         "/org/freedesktop/secrets/collection/login"],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        timeout=10, env=env)
    result = subprocess.run(
        ["gdbus", "call", "--session", "--dest", "org.freedesktop.secrets",
         "--object-path", "/org/freedesktop/secrets/aliases/default", "--method",
         "org.freedesktop.DBus.Properties.Get", "org.freedesktop.Secret.Collection", "Locked"],
        capture_output=True, timeout=10, env=env)
    if result.returncode or b"false" not in result.stdout:
        raise SetupError("The private browser keyring did not unlock.")


ORIGIN_JS = json.dumps(ORIGIN)
def accepted_context():
    """Exact deployed identity, installed only after canonical acceptance.

    This is a presentation binding, never an approval or session credential.
    Missing/malformed binding does not admit the new console.
    """
    try:
        value = json.loads(ACCEPTED_BINDING.read_text(encoding="utf-8"))
        identity = value["candidate_snapshot_id"]
        if (set(value) != {"candidate_snapshot_id"} or not isinstance(identity, str)
                or len(identity) != 83 or not identity.startswith("candidate-snapshot-")
                or any(c not in "0123456789abcdef" for c in identity[19:])):
            return ""
        return "ACCEPTED:" + identity
    except (OSError, ValueError, TypeError, KeyError):
        return ""

LOGIN_READY = """location.origin === %s && document.readyState === 'complete' &&
  !!document.querySelector('form#login input#credential') &&
  (document.body.innerText.includes('UNREVIEWED VISUALIZATION SUCCESSOR') ||
   document.body.innerText.includes('FAWKES MANAGED DEVELOPMENT CONSOLE'))""" % ORIGIN_JS
CONSOLE_READY = """location.origin === %s && location.pathname === '/dev-console' &&
  document.readyState === 'complete' &&
  (((document.querySelector('#preview-context')?.textContent || '').includes('UNREVIEWED') &&
    (document.querySelector('#connection-state')?.textContent || '').trim().toUpperCase() === 'CONNECTED') ||
   (%s !== '' && document.querySelector('meta[name="fawkes-console-context"]')?.content === %s &&
    document.querySelector('#dev-console')?.dataset.projectionState === 'live' &&
    !!document.querySelector('[data-page-target="0"]')))
""" % (ORIGIN_JS, json.dumps(accepted_context()), json.dumps(accepted_context()))
SUMMARY_CONTROL = """(() => {
  const controls = document.querySelectorAll('#dev-console button[data-page-target="0"]');
  const pages = document.querySelectorAll('#dev-console .console-page[data-page="0"]');
  if (controls.length !== 1 || pages.length !== 1) return null;
  const control = controls[0];
  if (control.disabled || control.getAttribute('aria-disabled') === 'true') return null;
  return control;
})()"""
SUMMARY = """(() => {
  if (!(%s)) return false;
  const summary = %s;
  if (!summary) return false;
  summary.click();
  const page = document.querySelector('#dev-console .console-page[data-page="0"]');
  if (document.querySelector('#dev-console')?.dataset.page !== '0' ||
      summary.getAttribute('aria-current') !== 'page' || page.hidden) return false;
  // Installed Goodix mapping is mouseEmulation=yes (retained Pi input evidence).
  // This opts only this Pi console into drag scrolling, not the desktop browser.
  window.__fawkesMatrixConfig = {idleMs:120000, emulatedPointerScroll:true,
    summarySelector: '#dev-console button[data-page-target="0"]'};
  return true;
})()""" % (CONSOLE_READY, SUMMARY_CONTROL)

# A document refresh can remain authenticated/CONSOLE_READY but lose injected
# JS globals. Restore only missing controls; do not select Summary or move focus
# during healthy polling. Native orientation/calibration and the bridge stay put.
CONTROLS_READY = """Boolean(window.__fawkesMatrix &&
  window.__fawkesMatrixConfig?.emulatedPointerScroll === true)"""
RESTORE_CONTROLS = """(() => {
  if (!(%s)) return false;
  const summary = %s;
  if (!summary) return false;
  window.__fawkesMatrixConfig={idleMs:120000,emulatedPointerScroll:true,
    summarySelector:'#dev-console button[data-page-target="0"]'};
  return true;
})()""" % (CONSOLE_READY, SUMMARY_CONTROL)


def ensure_console_controls(browser, matrix):
    if browser.evaluate(CONTROLS_READY):
        return
    if not browser.evaluate(RESTORE_CONTROLS):
        raise SetupError('Console controls are not available after refresh.')
    browser.evaluate(matrix)


def sign_in_expression(token):
    return """(() => {
      if (!(%s)) return false;
      const field = document.querySelector('form#login input#credential[type=password]');
      if (!field) return false;
      field.value = %s;
      field.dispatchEvent(new Event('input', {bubbles:true}));
      field.dispatchEvent(new Event('change', {bubbles:true}));
      field.form.requestSubmit();
      return true;
    })()""" % (LOGIN_READY, json.dumps(token))


def local_shutdown_tick(browser, shutdown):
    shutdown.install()
    result = shutdown.poll()
    if result and result['state'] == 'requested':
        status('SHUTTING_DOWN', 'Pi shutdown requested; PC and Worker remain running.')
        while browser.process.poll() is None:
            time.sleep(.25)
        raise SystemExit(0)
    if result:
        status('SHUTDOWN_UNCONFIRMED', result['message'])


def responsive_wait(browser, expression, message, *, timeout, shutdown=None):
    if shutdown is None:
        return browser.wait_for(expression, message, timeout=timeout)
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        local_shutdown_tick(browser, shutdown)
        if browser.evaluate(expression):
            return
        time.sleep(.15)
    raise SetupError(message)


def guarded_navigation(browser, shutdown, action):
    # Readiness is not permission to interrupt a hold or discard an unsaved
    # page. Service the same local reader while waiting; never renew a hold.
    while not prepare_navigation(browser, shutdown):
        if browser.process.poll() is not None:
            raise SetupError('The browser ended before navigation could be saved.')
        time.sleep(.15)
    try:
        result=action()
    except BaseException:
        if shutdown is not None:
            shutdown.abort_navigation()
        raise
    if shutdown is not None:
        shutdown.finish_navigation()
    return result


def open_console(browser, token, matrix, shutdown=None):
    def navigate_root():
        browser.navigate("/")
        responsive_wait(browser, "(" + LOGIN_READY + ") || (" + CONSOLE_READY + ")",
                         "The preview page did not load.", timeout=25, shutdown=shutdown)
    guarded_navigation(browser, shutdown, navigate_root)
    if not browser.evaluate(CONSOLE_READY):
        # Normal app sign-in, using the existing credential supplied by the PC.
        def sign_in():
            if not browser.evaluate(sign_in_expression(token)):
                raise SetupError("The expected sign-in form is unavailable.")
            responsive_wait(browser, CONSOLE_READY, "Waiting for authenticated Fawkes data.", timeout=35, shutdown=shutdown)
        guarded_navigation(browser, shutdown, sign_in)
    if not guarded_navigation(browser, shutdown, lambda: shutdown.select_summary(SUMMARY) if shutdown is not None else browser.evaluate(SUMMARY)):
        raise SetupError("The Summary tab could not be identified.")
    # Config was set from the actual Summary control, not a fabricated route.
    browser.evaluate(matrix)


WAITING = """<!doctype html><html><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Fawkes Console</title><style>
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;
background:#040b08;color:#c9ffe0;font:22px system-ui;text-align:center;padding:48px}
main{max-width:500px}p{color:#7ca991;line-height:1.5}h1{font-size:38px;font-weight:500}
.mark{font-size:14px;letter-spacing:.5em;color:#53c98a}</style></head>
<body><main><div class='mark'>FAWKES</div><h1>Waiting for Fawkes</h1>
<p>The console will reconnect automatically when your PC preview is available.</p>
</main></body></html>"""


def prepare_navigation(browser, shutdown=None):
    if shutdown is None:
        return True
    local_shutdown_tick(browser, shutdown)
    try:
        if shutdown.navigation_token is not None:
            shutdown.abort_navigation()
        if not shutdown.begin_navigation():
            return False
        # Capture input entered during the preceding network wait immediately
        # before replacing the document, not only before starting that wait.
        shutdown.checkpoint()
    except (SetupError, SaveError, OSError, ValueError, TypeError):
        try:shutdown.abort_navigation()
        except (SetupError, SaveError, OSError, ValueError, TypeError):pass
        status('LOCAL_STATE_UNSAVED', 'Draft could not be saved; keep this page open.')
        return False
    return True


def show_waiting(browser, waiting_url, matrix, shutdown=None):
    if not prepare_navigation(browser, shutdown):
        return False
    try:
        browser.call("Page.navigate", {"url": waiting_url}, browser.session)
        browser.wait_for("document.readyState === 'complete' && location.protocol === 'file:'",
                         "The local waiting screen did not open.", timeout=15)
        browser.evaluate(matrix)
    except BaseException:
        if shutdown is not None:
            shutdown.abort_navigation()
        raise
    else:
        if shutdown is not None:
            shutdown.finish_navigation()
    return True


def run():
    os.umask(0o077)
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    STATE.chmod(0o700)
    instance_lock = (STATE / "instance.lock").open("a")
    fcntl.flock(instance_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    # A crashed, stopped service can leave its temporary browser files behind.
    # The service owns these directories; its previous process group is gone.
    for old in STATE.glob("session-*"):
        if old.is_dir() and not old.is_symlink() and old.stat().st_uid == os.getuid():
            shutil.rmtree(old, ignore_errors=True)
    status("STARTING", "Preparing the Fawkes console.")
    for tool in ("chromium", "gnome-keyring-daemon", "gdbus"):
        if not shutil.which(tool):
            raise SetupError("Missing Pi component: " + tool)
    threading.Thread(target=receive_credentials, daemon=True).start()
    if not credential_ready.wait(5):
        raise SetupError("The private sign-in receiver could not start.")
    while not (RUNTIME / "wayland-0").is_socket():
        status("WAITING_DESKTOP", "Waiting for the Pi desktop.")
        time.sleep(3)
    session = Path(tempfile.mkdtemp(prefix="session-", dir=STATE))
    env = os.environ.copy()
    env.update(XDG_RUNTIME_DIR=str(RUNTIME), WAYLAND_DISPLAY="wayland-0")
    private_keyring(env, session)
    matrix = (ROOT / "matrix_idle.js").read_text(encoding="utf-8")
    hold = (ROOT / 'pi_console_idle_hold.js').read_text(encoding='utf-8')
    shutdown_owner = LocalShutdown(Path.home()/'.local/state/fawkes-pi-console-shutdown')
    waiting = session / "waiting.html"
    waiting.write_text(WAITING, encoding="utf-8")
    args = [shutil.which("chromium"), "--ozone-platform=wayland", "--disable-gpu",
            "--user-data-dir=" + str(session / "browser"), "--no-first-run",
            "--no-default-browser-check", "--password-store=gnome-libsecret",
            "--kiosk", "--remote-debugging-pipe", "about:blank"]
    with open(os.devnull, "wb") as quiet:
        browser = PipeBrowser(args, env, quiet)
        shutdown = None
        try:
            browser.attach()
            shutdown = BrowserShutdown(browser, shutdown_owner, THREAD, waiting.as_uri(), hold, matrix)
            shutdown.restore_hook()
            show_waiting(browser, waiting.as_uri(), matrix)
            shutdown.install()
            showing_console = False
            last_attempt = 0.0
            failures = 0
            next_health = 0.0
            while browser.process.poll() is None:
                local_shutdown_tick(browser, shutdown)
                if time.monotonic()<next_health:
                    time.sleep(.15);continue
                next_health=time.monotonic()+5
                # Save before any bridge-loss navigation. A failed save must
                # leave the current document/draft available, not erase it.
                try:shutdown.checkpoint()
                except (SetupError,SaveError,OSError,ValueError,TypeError):
                    status('LOCAL_STATE_UNSAVED','Draft could not be saved; keep this page open.')
                    time.sleep(.15);continue
                healthy = preview_ready()
                if not healthy:
                    failures += 1
                    if showing_console and failures >= 2:
                        if not show_waiting(browser, waiting.as_uri(), matrix, shutdown):
                            time.sleep(.15)
                            continue
                        shutdown.install()
                        showing_console = False
                    status("WAITING_PC", "Waiting for the PC preview; reconnecting automatically.")
                else:
                    failures = 0
                    if showing_console:
                        showing_console = bool(browser.evaluate(CONSOLE_READY))
                    token = get_credential()
                    if showing_console:
                        ensure_console_controls(browser, matrix)
                        ready_status(browser)
                    elif token and time.monotonic() - last_attempt >= 45:
                        last_attempt = time.monotonic()
                        status("SIGNING_IN", "Opening Fawkes Summary.")
                        try:
                            open_console(browser, token, matrix, shutdown)
                            shutdown.install()
                            showing_console = True
                            ready_status(browser)
                        except SetupError as error:
                            status("RETRYING", str(error))
                            show_waiting(browser, waiting.as_uri(), matrix, shutdown)
                            shutdown.install()
                        finally:
                            token = None
                    elif not token:
                        status("WAITING_BRIDGE", "Waiting for the PC sign-in connection.")
                time.sleep(.15)
        finally:
            if shutdown is not None:
                try:shutdown.checkpoint()
                except (SetupError,SaveError,OSError,ValueError,TypeError):pass
            browser.close()
            shutil.rmtree(session, ignore_errors=True)
    raise SetupError("The dedicated browser exited; restarting it.")


if __name__ == "__main__":
    try:
        if "--check-keyring" in sys.argv:
            os.umask(0o077)
            STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="check-", dir=STATE) as temporary:
                private_keyring(os.environ.copy(), Path(temporary))
            print("PRIVATE_KEYRING_OK", flush=True)
        else:
            run()
    except SetupError as error:
        status("RESTARTING", str(error))
        sys.exit(1)
    except Exception:
        # No raw browser responses, credentials or exception tracebacks in logs.
        status("RESTARTING", "The console encountered a local startup error.")
        sys.exit(1)
