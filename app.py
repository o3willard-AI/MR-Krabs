"""
MR-Krabs Kiosk Admin Panel
Flask web app for Ubuntu touchscreen system administration.

Run: pip install flask && python app.py
Access: http://<ip>:5000

Service:
    sudo cp kiosk-admin.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable --now kiosk-admin.service
"""

import json
import os
import pwd
import re
import shlex
import subprocess
import sys
import time
from datetime import datetime, timedelta
from ipaddress import ip_address, ip_network
from pathlib import Path
from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

app = Flask(__name__)
app.secret_key = os.urandom(32)

# ─── helpers ────────────────────────────────────────────────────────────────

def run(cmd, timeout=30):
    """Run a subprocess command (list form, no shell=True)."""
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout
    )
    return result


def validate_ip(ip_str):
    """Return True if valid IPv4 address."""
    try:
        ip_address(ip_str)
        return True
    except (ValueError, TypeError):
        return False


def validate_netmask(mask_str):
    """Return True if valid netmask like /24."""
    if not re.match(r"^/\d{1,2}$", mask_str):
        return False
    prefix = int(mask_str[1:])
    if prefix < 0 or prefix > 32:
        return False
    return True


def get_interfaces():
    """Get network interfaces using nmcli."""
    r = run(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device", "status"])
    interfaces = []
    for line in r.stdout.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split(":")
        if len(parts) >= 3:
            interfaces.append({
                "name": parts[0],
                "type": parts[1],
                "state": parts[2],
            })
    return interfaces


def get_connection_info(device_name):
    """Get connection details for a device."""
    r = run(["nmcli", "-t", "-f", "GENERAL.STATE,IP4.GATEWAY,IP4.DNS,IP4.ADDRESS",
             "connection", "show", device_name])
    info = {"state": "", "gateway": "", "dns": "", "address": ""}
    if r.returncode == 0 and r.stdout.strip():
        for line in r.stdout.strip().split("\n"):
            parts = line.split(":")
            if len(parts) >= 2:
                field, value = parts[0], parts[1]
                if field == "GENERAL.STATE":
                    info["state"] = value
                elif field == "IP4.GATEWAY":
                    info["gateway"] = value
                elif field == "IP4.DNS":
                    info["dns"] = value
                elif field == "IP4.ADDRESS":
                    info["address"] = value
    return info


def get_groups():
    """Get all system groups."""
    r = run(["getent", "group"])
    groups = []
    for line in r.stdout.strip().split("\n"):
        if line.strip():
            groups.append(line.strip().split(":")[0])
    return sorted(groups)


def get_user_groups(username):
    """Get groups a user belongs to."""
    r = run(["groups", username])
    if r.returncode != 0:
        return []
    # Output: "username : group1 group2 ..."
    parts = r.stdout.strip().split(":", 1)
    if len(parts) >= 2:
        return parts[1].strip().split()
    return []


def get_system_info():
    """Get CPU, memory, disk usage, uptime, load average."""
    info = {"cpu": "N/A", "memory": "N/A", "disk": "N/A",
            "uptime": "N/A", "load": "N/A",
            "cpu_percent": 0, "mem_percent": 0, "disk_percent": 0}

    # CPU usage via top
    r = run(["top", "-bn1"], timeout=5)
    if r.returncode == 0:
        for line in r.stdout.split("\n"):
            if "Cpu(s)" in line or "CPU" in line.upper():
                match = re.search(r"(\d+\.?\d*)\s*id", line)
                if match:
                    idle = float(match.group(1))
                    info["cpu_percent"] = round(100 - idle, 1)
                    info["cpu"] = f"{info['cpu_percent']}%"
                break

    # Memory from /proc/meminfo
    try:
        mem = {}
        with open("/proc/meminfo", "r") as f:
            for line in f:
                parts = line.split(":")
                if len(parts) >= 2:
                    key = parts[0].strip()
                    val = parts[1].strip().split()[0]
                    mem[key] = int(val)
        total = mem.get("MemTotal", 0)
        available = mem.get("MemAvailable", 0)
        used = total - available
        if total > 0:
            info["mem_percent"] = round((used / total) * 100, 1)
            info["memory"] = f"{info['mem_percent']}% ({used // 1024}MB / {total // 1024}MB)"
    except (IOError, OSError, KeyError):
        pass

    # Disk usage for /
    r = run(["df", "-B1", "/"])
    if r.returncode == 0:
        lines = r.stdout.strip().split("\n")
        if len(lines) >= 2:
            parts = lines[1].split()
            if len(parts) >= 5:
                total_disk = int(parts[1])
                used_disk = int(parts[2])
                if total_disk > 0:
                    info["disk_percent"] = round((used_disk / total_disk) * 100, 1)
                    info["disk"] = f"{info['disk_percent']}% ({used_disk // (1024**3)}GB / {total_disk // (1024**3)}GB)"

    # Uptime
    r = run(["uptime", "-p"])
    if r.returncode == 0:
        info["uptime"] = r.stdout.strip()

    # Load average
    try:
        with open("/proc/loadavg", "r") as f:
            load_parts = f.read().split()
            info["load"] = f"{load_parts[0]} / {load_parts[1]} / {load_parts[2]}"
    except (IOError, OSError, IndexError):
        pass

    return info


def get_user_info(username):
    """Get user details from /etc/passwd."""
    try:
        pw = pwd.getpwnam(username)
        return {
            "username": pw.pw_name,
            "uid": pw.pw_uid,
            "home": pw.pw_dir,
            "shell": pw.pw_shell,
            "gid": pw.pw_gid,
        }
    except KeyError:
        return None


def get_all_users():
    """Get all non-system users (uid >= 1000)."""
    users = []
    r = run(["getent", "passwd"])
    if r.returncode == 0:
        for line in r.stdout.strip().split("\n"):
            parts = line.split(":")
            if len(parts) >= 7:
                username = parts[0]
                uid = int(parts[2])
                home = parts[5]
                if uid >= 1000 and username not in ("nobody", "sync", "shutdown", "halt"):
                    users.append({"username": username, "home": home})
    return sorted(users, key=lambda u: u["username"])


# ─── page routes ────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/network")
def network():
    return render_template("network.html")


@app.route("/wifi")
def wifi():
    return render_template("wifi.html")


@app.route("/wired")
def wired():
    return render_template("wired.html")


@app.route("/users")
def users():
    return render_template("users.html")


@app.route("/users/add", methods=["GET", "POST"])
def users_add():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        fullname = request.form.get("fullname", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")

        # Validation
        if not username:
            flash("Username is required.", "error")
        elif not re.match(r"^[a-z_][a-z0-9_-]*$", username):
            flash("Username must start with a lowercase letter or underscore, "
                  "and contain only lowercase letters, numbers, hyphens, underscores.",
                  "error")
        elif len(username) < 3 or len(username) > 32:
            flash("Username must be between 3 and 32 characters.", "error")
        elif not fullname:
            flash("Full name is required.", "error")
        elif len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
        elif password != confirm:
            flash("Passwords do not match.", "error")
        else:
            # Create user
            r = run(["useradd", "-m", "-s", "/bin/bash",
                     "-c", shlex.quote(fullname), shlex.quote(username)])
            if r.returncode != 0:
                flash(f"Failed to create user: {r.stderr.strip()}", "error")
            else:
                # Set password via chpasswd
                pw_data = f"{username}:{password}".encode()
                r = run(["chpasswd"])
                if r.returncode != 0:
                    flash(f"Failed to set password: {r.stderr.strip()}", "error")
                else:
                    flash(f"User '{username}' created successfully.", "success")
                    return redirect(url_for("users"))
    return render_template("users_add.html")


@app.route("/users/<username>/permissions", methods=["GET", "POST"])
def user_permissions(username):
    if request.method == "POST":
        groups = request.form.getlist("groups")
        # Get current groups
        current = get_user_groups(username)
        all_groups = get_groups()

        # Remove from groups not selected
        for g in current:
            if g not in groups:
                run(["usermod", "-aG", f"!{g}", username])

        # Add to new groups
        for g in groups:
            if g not in current:
                run(["usermod", "-aG", shlex.quote(g), username])

        flash(f"Permissions updated for {username}.", "success")
        return redirect(url_for("users"))

    user_info = get_user_info(username)
    if not user_info:
        flash(f"User '{username}' not found.", "error")
        return redirect(url_for("users"))

    all_groups = get_groups()
    user_groups = get_user_groups(username)
    return render_template(
        "user_permissions.html",
        user_info=user_info,
        all_groups=all_groups,
        user_groups=user_groups,
    )


@app.route("/kiosk")
def kiosk():
    return render_template("kiosk.html")


@app.route("/system_info")
def system_info():
    return render_template("system_info.html")


@app.route("/logs")
def logs():
    return render_template("logs.html")


# ─── API routes ─────────────────────────────────────────────────────────────

@app.route("/api/network/status")
def api_network_status():
    interfaces = get_interfaces()
    for iface in interfaces:
        if iface["type"] == "ethernet" and iface["state"] == "connected":
            info = get_connection_info(iface["name"])
            iface.update(info)
            break
    return jsonify({"interfaces": interfaces})


@app.route("/api/wifi/scan", methods=["POST"])
def api_wifi_scan():
    run(["nmcli", "device", "wifi", "rescan"])
    time.sleep(2)
    r = run(["nmcli", "-t", "-f",
             "SSID,SECURITY,ACTIVE,SIGNAL,DEVICE",
             "wifi", "list"])
    networks = []
    for line in r.stdout.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split(":")
        if len(parts) >= 5:
            networks.append({
                "ssid": parts[0],
                "security": parts[1],
                "active": parts[2] == "yes",
                "signal": int(parts[3]) if parts[3].isdigit() else 0,
                "device": parts[4],
            })
    return jsonify({"networks": networks})


@app.route("/api/wifi/connect", methods=["POST"])
def api_wifi_connect():
    ssid = request.form.get("ssid", "").strip()
    password = request.form.get("password", "").strip()
    if not ssid:
        flash("SSID is required.", "error")
        return redirect(url_for("wifi"))

    # Check if already connected
    r = run(["nmcli", "-t", "-f", "SSID,STATE", "wifi", "status"])
    for line in r.stdout.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split(":")
        if len(parts) >= 2 and parts[0] == ssid and parts[1] == "connected":
            flash(f"Already connected to '{ssid}'.", "success")
            return redirect(url_for("wifi"))

    # Connect
    if password:
        r = run(["nmcli", "device", "wifi", "connect",
                 shlex.quote(ssid), "password", password])
    else:
        r = run(["nmcli", "device", "wifi", "connect",
                 shlex.quote(ssid)])

    if r.returncode == 0:
        flash(f"Connected to '{ssid}'.", "success")
    else:
        flash(f"Connection failed: {r.stderr.strip()}", "error")
    return redirect(url_for("wifi"))


@app.route("/api/wired/configure", methods=["POST"])
def api_wired_configure():
    interface = request.form.get("interface", "").strip()
    mode = request.form.get("mode", "dhcp")
    if not interface:
        flash("No interface selected.", "error")
        return redirect(url_for("wired"))

    if mode == "dhcp":
        r = run(["nmcli", "connection", "delete", shlex.quote(interface)])
        r = run(["nmcli", "connection", "add",
                 "type", "ethernet",
                 "con-name", shlex.quote(interface),
                 "ifname", shlex.quote(interface),
                 "autoconnect", "yes",
                 "ipv4.method", "auto"])
    else:
        ip_addr = request.form.get("ip", "").strip()
        netmask = request.form.get("netmask", "").strip()
        gateway = request.form.get("gateway", "").strip()

        if not validate_ip(ip_addr):
            flash("Invalid IP address.", "error")
            return redirect(url_for("wired"))
        if not validate_netmask(netmask):
            flash("Invalid netmask. Use /24, /16, or /8.", "error")
            return redirect(url_for("wired"))

        # Convert netmask prefix to dotted notation
        prefix = int(netmask[1:])
        mask_int = (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF
        dotted_mask = ".".join(str((mask_int >> i) & 0xFF) for i in (24, 16, 8, 0))

        r = run(["nmcli", "connection", "delete", shlex.quote(interface)])
        r = run(["nmcli", "connection", "add",
                 "type", "ethernet",
                 "con-name", shlex.quote(interface),
                 "ifname", shlex.quote(interface),
                 "autoconnect", "yes",
                 "ipv4.method", "manual",
                 "ipv4.address", f"{ip_addr}{netmask}",
                 "ipv4.gateway", gateway if gateway else "",
                 "ipv4.dns", "8.8.8.8,8.8.4.4"])

    if r.returncode == 0:
        flash(f"Wired connection configured on {interface}.", "success")
    else:
        flash(f"Configuration failed: {r.stderr.strip()}", "error")
    return redirect(url_for("wired"))


@app.route("/api/kiosk/toggle", methods=["POST"])
def api_kiosk_toggle():
    action = request.form.get("action", "")
    if action not in ("enable", "disable"):
        flash("Invalid action.", "error")
        return redirect(url_for("kiosk"))

    service_name = "kiosk-admin"
    if action == "enable":
        r = run(["systemctl", "enable", "--now", service_name])
        if r.returncode == 0:
            flash("Kiosk mode enabled.", "success")
        else:
            flash(f"Failed to enable kiosk mode: {r.stderr.strip()}", "error")
    else:
        r = run(["systemctl", "disable", "--now", service_name])
        if r.returncode == 0:
            flash("Kiosk mode disabled.", "success")
        else:
            flash(f"Failed to disable kiosk mode: {r.stderr.strip()}", "error")
    return redirect(url_for("kiosk"))


@app.route("/api/dashboard")
def api_dashboard():
    """Aggregated dashboard status."""
    data = {
        "network": {"status": "unknown"},
        "wifi": {"status": "unknown"},
        "users_count": 0,
        "kiosk_enabled": False,
        "system": get_system_info(),
    }

    # Network status
    r = run(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device", "status"])
    for line in r.stdout.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split(":")
        if len(parts) >= 3:
            if parts[1] == "ethernet" and parts[2] == "connected":
                data["network"]["status"] = "connected"
            elif parts[1] == "wifi" and parts[2] == "connected":
                data["network"]["status"] = "connected"
                data["wifi"]["status"] = "connected"

    # User count
    users = get_all_users()
    data["users_count"] = len(users)

    # Kiosk status
    r = run(["systemctl", "is-active", "kiosk-admin"])
    if r.returncode == 0:
        data["kiosk_enabled"] = True

    return jsonify(data)


@app.route("/api/logs/fetch", methods=["POST"])
def api_logs_fetch():
    log_file = request.form.get("log_file", "syslog")
    lines_count = request.form.get("lines", "100")
    try:
        lines_count = int(lines_count)
    except (ValueError, TypeError):
        lines_count = 100

    log_path = f"/var/log/{log_file}"
    if not log_file.replace(".", "").replace("_", "").isalnum():
        flash("Invalid log file name.", "error")
        return jsonify({"error": "Invalid log file name"}), 400

    r = run(["tail", "-n", str(lines_count), log_path])
    if r.returncode != 0:
        return jsonify({"error": r.stderr.strip()}), 403

    entries = []
    for line in r.stdout.strip().split("\n"):
        if not line.strip():
            continue
        entry = {"line": line, "severity": "info"}
        upper = line.upper()
        if "ERROR" in upper or "FAIL" in upper:
            entry["severity"] = "error"
        elif "WARN" in upper:
            entry["severity"] = "warning"
        elif "CRIT" in upper or "EMERG" in upper:
            entry["severity"] = "critical"
        entries.append(entry)

    return jsonify({"entries": entries})


# ─── main ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
