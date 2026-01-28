## MK Proxy Generator and Rotator

Desktop application built with **PyQt5** that manages a pool of **Tor** instances and exposes them via a local HTTP proxy. It can automatically rotate IPs or let you trigger rotation manually, making it useful for privacy, testing, scraping, and load-distribution scenarios.

---

### Overview

- **Tor pool management**: Starts and manages multiple Tor instances via `TorPoolManager`.
- **Local HTTP proxy**: Exposes the Tor pool through a hybrid proxy server on `127.0.0.1:<port>`.
- **Automatic IP rotation**: Optional timer-based rotation between instances.
- **Manual IP change**: One-click/manual IP switching from the UI or `GET /rotate`.
- **Real-time instance table**: Shows instance ID, backend port, current IP, country, and status.
- **Dark terminal-style UI**: Modern dark theme with a live log console.

Project structure (simplified):

- `main.py` – PyQt5 GUI, configuration management, and high-level control.
- `backend/tor_handler.py` – Tor process management, IP/country lookup, and pool orchestration.
- `backend/proxy_server.py` – Hybrid HTTP proxy that forwards traffic through the Tor pool.

---

### Requirements

- **Python**: 3.8+
- **Tor**:
  - Recommended: use the bundled archive `tor-expert-bundle-windows-x86_64-15.0.4.tar.gz` included in this project.
- **Python packages** (see `requirements.txt`):
  - `PyQt5`
  - `requests`
  - `urllib3`
  - `stem`

Install dependencies:

```bash
pip install -r requirements.txt
```

---

### Installation & Run

1. **Extract Tor Expert Bundle (Windows)**

   In the project root (where `main.py` lives), you should see:

   - `tor-expert-bundle-windows-x86_64-15.0.4.tar.gz`

   Extract this archive so that `tor.exe` ends up under one of the following folders:

   - `tor/tor.exe`  
   **or**
   - `tor_bin/tor.exe`

   The application will automatically look for `tor.exe` in those locations.

2. **Install Python dependencies**

   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application**

   ```bash
   python main.py
   ```

   The main window titled **"MK Proxy Generator and Rotator"** will open.

---

### UI Guide

- **Settings**
  - `Pool Size`: Number of Tor instances to start.
  - `Proxy Port`: Local HTTP proxy port (default: `8080`).
  - `Auto Rotate Time (sec)`: Interval in seconds for automatic IP rotation (`0` = Off/Manual).

- **Control**
  - `Start`: Starts Tor instances and the local proxy.
  - `Stop`: Stops the proxy and all Tor instances.
  - `Change IP (Manual)`: Manually trigger IP renewal / instance switch.

- **Connection Info**
  - Shows the proxy address and example browser/API configuration, including the `GET /rotate` endpoint.

- **Instance List**
  - Displays instance ID, backend port, current IP, country, and status:
    - `🟢 Ready` – instance is usable and has a resolved IP.
    - `🟡 Connecting` – instance is still warming up.
    - `🔴 Error` – failed to resolve IP for this instance.

- **Log Terminal**
  - Shows timestamped log messages from the Tor pool and proxy server (startup, IP changes, errors, etc.).

---

### Proxy Usage

**Browser configuration**

- HTTP proxy host: `127.0.0.1`
- HTTP proxy port: `<proxy_port>` (default `8080`)

**Programmatic / API usage**

- Send HTTP traffic through:

  ```text
  http://127.0.0.1:<proxy_port>
  ```

- To trigger rotation (or fast switch) programmatically:

  ```text
  GET http://127.0.0.1:<proxy_port>/rotate
  ```

Depending on the pool size:

- Pool size `1`: behaves like “renew IP” on a single Tor instance.
- Pool size `>1`: rotates between instances and pre-warms the one that was just rotated out.

---

### Configuration Persistence

Basic configuration (`pool_size`, `proxy_port`, `auto_rotate_time`) is stored in `config.json` in the project root. If the file does not exist, the application uses built-in defaults and saves the configuration when you change settings or close the app.

---

### Development Notes

- The project is structured to be bundled as an executable (e.g. with `PyInstaller`) by embedding defaults and looking up paths relative to the executable.
- Network calls for IP and country lookup use:
  - `https://api.ipify.org?format=json` for public IP discovery.
  - `http://ip-api.com/json/<ip>` for country code lookup.
- The Tor pool is started in parallel using `ThreadPoolExecutor` and validated for circuit readiness.

---

Disclaimer: This tool is for educational and testing purposes only. The author is not responsible for any misuse or violation of any third-party terms of service.
