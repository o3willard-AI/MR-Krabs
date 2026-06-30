# MR-Krabs Kiosk Admin Panel

A comprehensive Ubuntu touchscreen system administration panel built with Flask.

## Features

- **Dashboard**: System overview with status cards
- **Network**: View and manage network interfaces
- **WiFi**: Scan and connect to WiFi networks
- **Wired**: Configure ethernet connections (DHCP/Static)
- **Users**: Manage user accounts and permissions
- **Kiosk Mode**: Toggle kiosk browser service
- **System Info**: CPU, memory, disk, and process information
- **Logs**: View system logs (syslog, auth.log, kern.log)

## Requirements

- Ubuntu 20.04+
- Python 3.8+
- Flask 3.0+
- NetworkManager (nmcli)
- Systemd

## Installation

```bash
pip install -r requirements.txt
```

## Running

```bash
python app.py
```

The admin panel will be available at `http://localhost:5000`.

## Testing

```bash
python test_smoke.py
```

## Architecture

- **Single Flask app** (`app.py`): All routes and API endpoints
- **Templates** (`templates/`): HTML templates using Jinja2
- **Static files** (`static/`): CSS and JavaScript
- **No external dependencies**: Uses Python stdlib only

## Security Notes

- All subprocess calls use list-form with `shlex.quote()` for user inputs
- `usermod` uses `-aG` (append groups) not `-G` (replace groups)
- `systemctl` uses `enable`/`disable`, NOT `toggle`/`start`/`stop`
- WiFi passwords handled securely via `nmcli` connection import
- No `shell=True` in subprocess calls

## Service Integration

The app is designed to run under an orchestrator that handles privileges. See `app.py` for the systemd service unit file comment.

## License

MIT
