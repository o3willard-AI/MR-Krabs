import ipaddress
import json
import os
import pwd
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(cmd, timeout=15):
    """Run a shell command using list-form and shlex.quote. Returns stdout."""
    quoted = []
    for part in cmd:
        quoted.append(shlex.quote(str(part)))
    cmd_str = " ".join(quoted)
    try:
        result = subprocess.run(
            cmd_str,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except subprocess.TimeoutExpired:
        return "", "Command timed out", 1
    except Exception as e:
        return "", str(e), 1


def _check_root():
    """Ensure the caller is root; return error dict if not."""
    if os.geteuid() != 0:
        return {"error": "This operation requires root privileges"}, 403
    return None


def _get_os_name():
    """Return a human-readable OS name."""
    if os.path.exists("/etc/os-release"):
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("PRETTY_NAME="):
                    return line.split("=", 1)[1].strip().strip('"')
    return "Ubuntu"


def _get_hostname():
    try:
        out, _, _ = _run(["hostname"])
        return out
    except Exception:
        return "kiosk"


# ---------------------------------------------------------------------------
# HTML pages
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/network")
def network_page():
    return render_template("network.html")


@app.route("/wifi")
def wifi_page():
    return render_template("wifi.html")


@app.route("/wired")
def wired_page():
    return render_template("wired.html")


@app.route("/users")
def users_page():
    return render_template("users.html")


@app.route("/users/add")
def users_add_page():
    return render_template("users_add.html")


@app.route("/user/<username>/permissions")
def user_permissions_page(username):
    return render_template("user_permissions.html", username=username)


@app.route("/kiosk")
def kiosk_page():
    service_name = "kiosk-mode.service"
    service_path = Path("/etc/systemd/system") / service_name
    try:
        _, _, rc = _run(["systemctl", "is-active", service_name])
        status = "enabled" if rc == 0 else "disabled"
    except Exception:
        status = "disabled"
    return render_template("kiosk.html", status=status)


@app.route("/system")
def system_page():
    """System information page"""
    cpu_info = _get_cpu_info()
    memory_info = _get_memory_info()
    disk_info = _get_disk_info()
    system_info = {
        "uptime": _get_system_info().get("uptime", "Unknown"),
        "load": _get_system_info().get("load", "N/A"),
        "python": sys.version.split()[0],
    }
    return render_template(
        "system_info.html",
        cpu_info=cpu_info,
        memory_info=memory_info,
        disk_info=disk_info,
        system_info=system_info,
    )


@app.route("/logs")
def logs_page():
    return render_template("logs.html")


# ---------------------------------------------------------------------------
# API: Dashboard
# ---------------------------------------------------------------------------


@app.route("/api/dashboard")
def api_dashboard():
    return jsonify({
        "os": _get_os_name(),
        "hostname": _get_hostname(),
        "kiosk": "enabled" if Path("/etc/systemd/system/kiosk-mode.service").exists() else "disabled",
    })


# ---------------------------------------------------------------------------
# API: Network
# ---------------------------------------------------------------------------


@app.route("/api/network/status")
def api_network_status():
    interfaces = []
    out, _, rc = _run(["nmcli", "-t", "-f", "GENERAL.STATE,GENERAL.DEVICE,GENERAL.CONNECTION", "device", "status"])
    if rc == 0 and out:
        for line in out.split("\n"):
            if not line.strip():
                continue
            parts = line.split(":")
            if len(parts) >= 3:
                state = parts[0]
                dev = parts[1]
                conn = parts[2] if parts[2] else "auto-" + dev
                interfaces.append({
                    "name": dev,
                    "state": state,
                    "connection": conn,
                })
    return jsonify({"interfaces": interfaces})


# ---------------------------------------------------------------------------
# API: WiFi
# ---------------------------------------------------------------------------


@app.route("/api/wifi/status")
def api_wifi_status():
    connected_ssid = ""
    out, _, rc = _run(["nmcli", "-t", "-f", "ACTIVE,SSID", "dev", "wifi"])
    if rc == 0:
        for line in out.split("\n"):
            if not line.strip():
                continue
            parts = line.split(":")
            if len(parts) >= 2 and parts[0] == "yes":
                connected_ssid = parts[1]
                break

    networks = []
    out, _, rc = _run(["nmcli", "-t", "-f", "SSID,SIGNAL,BARS,SECURITY", "dev", "wifi", "list"])
    if rc == 0 and out:
        for line in out.split("\n"):
            if not line.strip():
                continue
            parts = line.split(":")
            if len(parts) >= 3:
                ssid = parts[0]
                signal = parts[1]
                bars = parts[2]
                security = parts[3] if len(parts) > 3 else ""
                if ssid:
                    networks.append({
                        "ssid": ssid,
                        "signal": signal,
                        "bars": bars,
                        "security": security,
                    })
    return jsonify({"connected": connected_ssid, "networks": networks})


@app.route("/api/wifi/scan", methods=["POST"])
def api_wifi_scan():
    err = _check_root()
    if err:
        return jsonify(err)
    out, _, rc = _run(["nmcli", "dev", "wifi", "rescan"])
    return jsonify({"success": rc == 0, "error": out if rc != 0 else None})


@app.route("/api/wifi/connect", methods=["POST"])
def api_wifi_connect():
    err = _check_root()
    if err:
        return jsonify(err)
    ssid = request.form.get("ssid", "")
    password = request.form.get("password", "")
    if not ssid:
        return jsonify({"success": False, "error": "SSID required"}), 400
    cmd = ["nmcli", "dev", "wifi", "connect", ssid]
    if password:
        cmd.append("password")
        cmd.append(password)
    out, _, rc = _run(cmd)
    return jsonify({"success": rc == 0, "error": out if rc != 0 else None})


# ---------------------------------------------------------------------------
# API: Wired
# ---------------------------------------------------------------------------


@app.route("/api/wired/status")
def api_wired_status():
    interfaces = []
    out, _, rc = _run(["nmcli", "-t", "-f", "GENERAL.DEVICE,GENERAL.STATE,IP4.ADDRESS,IP4.GATEWAY", "device", "show"])
    if rc == 0 and out:
        for line in out.split("\n"):
            if not line.strip():
                continue
            parts = line.split(":")
            if len(parts) >= 2 and parts[1] == "connected":
                dev = parts[0]
                addr = ""
                gw = ""
                for line2 in out.split("\n"):
                    if line2.startswith(dev + ":"):
                        sub_parts = line2.split(":")
                        if len(sub_parts) >= 4:
                            addr = sub_parts[2]
                            gw = sub_parts[3] if len(sub_parts) > 3 else ""
                interfaces.append({
                    "name": dev,
                    "state": "connected",
                    "address": addr,
                    "gateway": gw,
                })
    return jsonify({"interfaces": interfaces})


# ---------------------------------------------------------------------------
# API: Users
# ---------------------------------------------------------------------------


@app.route("/api/users")
def api_users_list():
    users = []
    try:
        out, _, _ = _run(["getent", "passwd"])
        if out:
            for line in out.split("\n"):
                if not line.strip():
                    continue
                parts = line.split(":")
                if len(parts) >= 3:
                    username = parts[0]
                    uid = int(parts[2])
                    if uid >= 1000 and username != "nobody":
                        groups_out, _, _ = _run(["id", "-Gn", username])
                        groups = groups_out.split() if groups_out else []
                        users.append({
                            "username": username,
                            "groups": groups,
                        })
    except Exception:
        pass
    return jsonify({"users": users})


@app.route("/api/users", methods=["POST"])
def api_users_add():
    err = _check_root()
    if err:
        return jsonify(err)

    username = request.form.get("username", "").strip()
    fullname = request.form.get("fullname", "").strip()
    password = request.form.get("password", "")
    confirm = request.form.get("confirm", "")

    if not username or not password:
        return jsonify({"success": False, "error": "Username and password are required"}), 400

    if password != confirm:
        return jsonify({"success": False, "error": "Passwords do not match"}), 400

    username_regex = r"^[a-z_][a-z0-9_-]*$"
    if not re.match(username_regex, username):
        return jsonify({"success": False, "error": "Invalid username format"}), 400

    # Check if user already exists
    out, _, rc = _run(["id", username])
    if rc == 0:
        return jsonify({"success": False, "error": "User already exists"}), 409

    # Create user with home directory
    cmd = ["useradd", "-m", "-s", "/bin/bash"]
    if fullname:
        cmd.extend(["-c", fullname])
    cmd.append(username)
    out, err_out, rc = _run(cmd)
    if rc != 0:
        return jsonify({"success": False, "error": f"Failed to create user: {err_out}"}), 500

    # Set password via chpasswd
    import io
    try:
        process = subprocess.Popen(
            ["chpasswd"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdin_data = f"{username}:{password}\n".encode()
        stdout, stderr = process.communicate(input=stdin_data, timeout=10)
        if process.returncode != 0:
            return jsonify({"success": False, "error": f"Failed to set password: {stderr.decode()}"}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

    return jsonify({"success": True}), 201


@app.route("/api/users/<username>/permissions")
def api_users_permissions(username):
    groups = []
    out, _, rc = _run(["id", "-Gn", username])
    if rc == 0 and out:
        groups = out.split()
    return jsonify({"username": username, "groups": groups})


@app.route("/api/users/<username>/permissions", methods=["POST"])
def api_users_permissions_update(username):
    err = _check_root()
    if err:
        return jsonify(err)

    groups = request.form.getlist("groups")
    if not groups:
        return jsonify({"success": False, "error": "No groups selected"}), 400

    # Check user exists
    out, _, rc = _run(["id", username])
    if rc != 0:
        return jsonify({"success": False, "error": "User does not exist"}), 404

    # Add user to all selected groups using -aG (append)
    for group in groups:
        cmd = ["usermod", "-aG", group, username]
        _, err_out, rc = _run(cmd)
        if rc != 0:
            return jsonify({"success": False, "error": f"Failed to add {username} to {group}: {err_out}"}), 500

    return jsonify({"success": True})


# ---------------------------------------------------------------------------
# API: Kiosk
# ---------------------------------------------------------------------------


@app.route("/api/kiosk/toggle", methods=["POST"])
def api_kiosk_toggle():
    err = _check_root()
    if err:
        return jsonify(err)

    service_name = "kiosk-mode.service"
    service_path = Path("/etc/systemd/system") / service_name

    if service_path.exists():
        out, _, rc = _run(["systemctl", "disable", service_name])
        if rc != 0:
            return jsonify({"success": False, "error": f"Failed to disable: {out}"}), 500
        return jsonify({"success": True, "status": "disabled"})
    else:
        service_content = "[Unit]\nDescription=Kiosk Mode\nAfter=graphical.target\n\n[Service]\nExecStart=/usr/bin/Xorg :0 -share-vts\n\n[Install]\nWantedBy=graphical.target\n"
        service_path.write_text(service_content)
        out, _, rc = _run(["systemctl", "enable", service_name])
        if rc != 0:
            return jsonify({"success": False, "error": f"Failed to enable: {out}"}), 500
        return jsonify({"success": True, "status": "enabled"})


# ---------------------------------------------------------------------------
# API: System Info
# ---------------------------------------------------------------------------


@app.route("/api/system/info")
def api_system_info():
    cpu_info = _get_cpu_info()
    mem_info = _get_memory_info()
    disk_info = _get_disk_info()
    system_info = _get_system_info()
    return jsonify({
        "cpu": cpu_info,
        "memory": mem_info,
        "disk": disk_info,
        "system": system_info,
    })


def _get_cpu_info():
    usage = 0
    model = "Unknown"
    out, _, rc = _run(["cat", "/proc/cpuinfo"])
    if rc == 0 and out:
        for line in out.split("\n"):
            if line.startswith("model name"):
                model = line.split(":", 1)[1].strip()
                break

    # Try to read CPU usage from /proc/stat
    try:
        with open("/proc/stat") as f:
            for line in f:
                if line.startswith("cpu "):
                    parts = line.split()[1:]
                    total = sum(int(x) for x in parts)
                    idle = int(parts[3]) if len(parts) > 3 else 0
                    if total > 0:
                        usage = round((1 - idle / total) * 100, 1)
                    break
    except Exception:
        pass

    return {
        "model": model,
        "usage": usage,
    }


def _get_memory_info():
    total = 0
    used = 0
    out, _, rc = _run(["free", "-b"])
    if rc == 0 and out:
        lines = out.split("\n")
        if len(lines) >= 2:
            parts = lines[1].split()
            if len(parts) >= 3:
                total = int(parts[1])
                used = int(parts[2])
    usage = (used / total * 100) if total > 0 else 0
    return {
        "total": round(total / (1024**3), 2),
        "used": round(used / (1024**3), 2),
        "usage": round(usage, 1),
    }


def _get_disk_info():
    total = 0
    used = 0
    out, _, rc = _run(["df", "-B1", "/"])
    if rc == 0 and out:
        lines = out.split("\n")
        if len(lines) >= 2:
            parts = lines[1].split()
            if len(parts) >= 3:
                total = int(parts[1])
                used = int(parts[2])
    usage = (used / total * 100) if total > 0 else 0
    return {
        "total": round(total / (1024**3), 2),
        "used": round(used / (1024**3), 2),
        "usage": round(usage, 1),
    }


def _get_system_info():
    uptime = "Unknown"
    load = "0.00, 0.00, 0.00"
    out, _, rc = _run(["uptime"])
    if rc == 0 and out:
        load = out.split("load average:")[1].strip()
        # Parse uptime
        if "day" in out or "day " in out:
            parts = out.split(",")
            for part in parts:
                if "day" in part or "day " in part:
                    uptime = part.strip()
                    break
        elif "hour" in out or "hour " in out:
            parts = out.split(",")
            for part in parts:
                if "hour" in part or "hour " in part:
                    uptime = part.strip()
                    break
    return {
        "uptime": uptime,
        "load": load,
    }


# ---------------------------------------------------------------------------
# API: Logs
# ---------------------------------------------------------------------------


@app.route("/api/logs")
def api_logs():
    severity = request.args.get("severity", "all")
    lines_count = request.args.get("lines", "100", type=int)

    logs = []
    out, _, rc = _run(["journalctl", "-n", str(lines_count), "--no-pager", "-q"])
    if rc == 0 and out:
        for line in out.split("\n"):
            if not line.strip():
                continue
            log_entry = {
                "message": line,
                "severity": "info",
            }
            if "error" in line.lower():
                log_entry["severity"] = "error"
            elif "warning" in line.lower():
                log_entry["severity"] = "warning"
            elif "success" in line.lower() or "ok" in line.lower():
                log_entry["severity"] = "success"
            logs.append(log_entry)

    return jsonify({"logs": logs})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
