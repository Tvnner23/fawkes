"""Fixed authenticated control surface for the local Fawkes systemd stack."""

import subprocess


UNITS = {
    "stack": "fawkes.target",
    "app_server": "fawkes-app.service",
    "discord_bridge": "fawkes-discord.service",
}
ACTIONS = {"start", "stop", "restart"}


def control_component(component, action):
    if component not in UNITS or action not in ACTIONS:
        raise ValueError("unsupported Fawkes component control action")
    completed = subprocess.run(
        ["/usr/bin/sudo", "-n", "/usr/bin/systemctl", action, UNITS[component]],
        capture_output=True, text=True, timeout=60, check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"component control failed with exit code {completed.returncode}")
    return {"component": component, "unit": UNITS[component], "action": action,
            "status": "requested", "creates_development_authority": False}


def component_states():
    result = {}
    for component, unit in UNITS.items():
        completed = subprocess.run(
            ["/usr/bin/systemctl", "show", unit, "--property=ActiveState,SubState,NRestarts",
             "--value"], capture_output=True, text=True, timeout=10, check=False)
        values = completed.stdout.splitlines()
        active = values[0] if completed.returncode == 0 and values else "inactive"
        normalized = {"active": "READY", "activating": "STARTING", "deactivating": "STOPPED",
                      "failed": "FAILED", "inactive": "STOPPED"}.get(active, "BLOCKED")
        result[component] = {"unit": unit,
            "state": normalized, "systemd_active_state": active,
            "substate": values[1] if len(values) > 1 else "unknown",
            "restart_count": values[2] if len(values) > 2 else "0"}
    return result
