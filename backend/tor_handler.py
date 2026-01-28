import os
import sys
import subprocess
import time
import uuid
import shutil
import socket
import threading
from pathlib import Path
from typing import Optional, List
from concurrent.futures import ThreadPoolExecutor

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ImportError:
    pass

try:
    from stem.control import Controller
except ImportError:
    pass


def get_exe_dir() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    else:
        return Path(__file__).parent.parent

class TorInstance:
    
    def __init__(self, socks_port: int = 9050, control_port: int = 9051, password: str = None):
        self.socks_port = socks_port
        self.control_port = control_port
        self.password = password or "MySecretPassword123"
        self.instance_id = str(uuid.uuid4())[:8]
        
        self.project_root = get_exe_dir()
        
        self.tor_exe_path = self.project_root / "tor" / "tor.exe"
        if not self.tor_exe_path.exists():
             self.tor_exe_path = self.project_root / "tor_bin" / "tor.exe"

        self.data_dir = self.project_root / "data" / f"tor_{socks_port}"
        self.process: Optional[subprocess.Popen] = None
        self.torrc_path = self.data_dir / "torrc"
        
        try:
            self.session = requests.Session()
            
            adapter = HTTPAdapter(
                pool_connections=2,
                pool_maxsize=2,
                max_retries=Retry(total=0, backoff_factor=0)  
            )
            self.session.mount('http://', adapter)
            self.session.mount('https://', adapter)
            self.session.headers.update({'Connection': 'keep-alive'})
            self.session.proxies = {
                'http': f'socks5://127.0.0.1:{self.socks_port}',
                'https': f'socks5://127.0.0.1:{self.socks_port}'
            }
        except:
            self.session = None
        
        self._ip_cache = None
        self._ip_cache_time = 0
        self._cache_ttl = 60 
        
        if sys.platform == "win32":
            self.creation_flags = subprocess.CREATE_NO_WINDOW
        else:
            self.creation_flags = 0

    def _reset_cached_state(self):
        """Klasörü tamamen silmeden Tor state/cache dosyalarını temizler."""
        try:
            if self.data_dir.exists():
                patterns = [
                    "cached-*",
                    "state",
                    "lock",
                    "router*",
                    "micro*",
                ]
                for pattern in patterns:
                    for path in self.data_dir.glob(pattern):
                        try:
                            if path.is_file():
                                path.unlink()
                            elif path.is_dir():
                                shutil.rmtree(path, ignore_errors=True)
                        except Exception:
                            pass
            else:
                self.data_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
    
    def _create_hashed_password(self) -> str:
        return "16:872860B76453A77D60CA2BB8C1A7042072093276A3D701AD9B00AC5DA7"

    def _create_data_directory(self):
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    def _create_torrc(self):
        hashed = self._create_hashed_password()
        rel_data_dir = f"data/tor_{self.socks_port}"
        
        torrc_content = f"""SocksPort {self.socks_port}
ControlPort {self.control_port}
DataDirectory {rel_data_dir}
HashedControlPassword {hashed}
"""
        try:
            with open(self.torrc_path, 'w', encoding='utf-8') as f:
                f.write(torrc_content)
        except Exception as e:
            print(f"[WARNING] Failed to write torrc: {e}")
            pass

    def start(self):
        if self.process is not None:
            return True

        self._reset_cached_state()
        self._create_data_directory()
        self._create_torrc()
        
        if not self.tor_exe_path.exists():
            return False

        try:
            self.process = subprocess.Popen(
                [str(self.tor_exe_path), "-f", str(self.torrc_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=self.creation_flags,
                cwd=str(self.project_root)  
            )
            ready = False
            for _ in range(180):
                time.sleep(1.0)
                try:
                    if self.is_circuit_ready_socks(timeout_sec=5.0):
                        ready = True
                        break
                except Exception:
                    pass
            if not ready:
                self.stop()
                return False
            self._ip_cache = None
            return True
            
        except Exception:
            self.stop()
            return False

    def stop(self):
        if self.process:
            try:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except Exception:
                    try:
                        self.process.kill()
                    except Exception:
                        pass
            except Exception:
                pass
            self.process = None
    
    def renew_ip(self):
        try:
            with Controller.from_port(port=self.control_port, timeout=2) as controller:
                controller.authenticate(password=self.password)
                controller.signal("NEWNYM")
                self._ip_cache = None
        except:
            pass

    def get_ip(self, max_retries=1, retry_delay=0):
        current_time = time.time()
        if self._ip_cache and (current_time - self._ip_cache_time) < self._cache_ttl:
            return self._ip_cache
        
        for attempt in range(max_retries):
            try:
                if self.session:
                    response = self.session.get(
                        "https://api.ipify.org?format=json", 
                        timeout=3.0,
                        allow_redirects=False 
                    )
                else:
                    proxies = {
                        'http': f'socks5://127.0.0.1:{self.socks_port}',
                        'https': f'socks5://127.0.0.1:{self.socks_port}'
                    }
                    response = requests.get(
                        "https://api.ipify.org?format=json", 
                        proxies=proxies, 
                        timeout=3.0,
                        allow_redirects=False
                    )
                
                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, dict):
                        ip = data.get('ip', '')
                        if ip and isinstance(ip, str):
                            ip = ip.strip()
                            self._ip_cache = ip
                            self._ip_cache_time = time.time()
                            return ip
            except Exception:
                pass
            
            if retry_delay > 0 and attempt < max_retries - 1:
                time.sleep(retry_delay)
        
        return "..."

    def get_country(self, ip=None):
        if not ip or ip in ("Bilinmiyor", "Hazır", "Yükleniyor...", "...", "-"):
            return "-"
        try:
            if self.session:
                old_proxies = self.session.proxies
                self.session.proxies = {}
                try:
                    response = self.session.get(
                        f"http://ip-api.com/json/{ip}", 
                        timeout=2.0,
                        allow_redirects=False
                    )
                finally:
                    self.session.proxies = old_proxies
            else:
                response = requests.get(
                    f"http://ip-api.com/json/{ip}", 
                    timeout=2.0,
                    allow_redirects=False
                )
            
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, dict):
                    country_code = data.get("countryCode", "-")
                    if country_code and isinstance(country_code, str):
                        return country_code.strip()
                return "-"
        except Exception:
            pass
        return "-"

    def is_circuit_ready_socks(self, timeout_sec: float = 5.0) -> bool:
        try:
            proxies = {
                'http': f'socks5://127.0.0.1:{self.socks_port}',
                'https': f'socks5://127.0.0.1:{self.socks_port}'
            }
            r = requests.get("https://api.ipify.org?format=json", proxies=proxies, timeout=timeout_sec)
            if r.status_code == 200:
                d = r.json()
                return isinstance(d, dict) and isinstance(d.get('ip'), str) and len(d.get('ip', '')) > 0
        except Exception:
            pass
        return False

    def is_circuit_ready(self):
        try:
            with Controller.from_port(port=self.control_port, timeout=2) as controller:
                controller.authenticate(password=self.password)
                status = controller.get_info("status/circuit-established")
                return "1" in str(status)
        except:
            return False


class TorPoolManager:
    
    def __init__(self, count: int = 1, base_socks_port: int = 9050, base_control_port: int = 9051):
        self.count = count
        self.base_socks_port = base_socks_port
        self.base_control_port = base_control_port
        self.instances: List[TorInstance] = []
        self.current_index = 0
    
    def start_pool(self):
        try:
            os.system("taskkill /F /IM tor.exe >nul 2>&1")
            time.sleep(0.5)
        except Exception:
            pass


        launched_instances = []
        futures = []
        with ThreadPoolExecutor(max_workers=min(self.count, 15)) as executor:
            for i in range(self.count):
                socks = self.base_socks_port + (i*2)
                control = self.base_control_port + (i*2)
                instance = TorInstance(socks_port=socks, control_port=control)
                launched_instances.append(instance)
                futures.append(executor.submit(instance.start))
            for inst, fut in zip(launched_instances, futures):
                try:
                    if fut.result():
                        self.instances.append(inst)
                except Exception:
                    pass
        
        max_wait = 30  
        start_time = time.time()
        while (time.time() - start_time) < max_wait:
            try:
                all_ready = all(inst.is_circuit_ready() for inst in self.instances)
                if all_ready:
                    break
            except:
                pass
            time.sleep(0.5)

        if not self.instances:
            raise RuntimeError("Tor instanceları başlatılamadı (tor.exe veya data izinlerini kontrol et)")

    def stop_pool(self):
        for instance in self.instances:
            instance.stop()
        self.instances.clear()

        try:
            os.system("taskkill /F /IM tor.exe >nul 2>&1")
        except Exception:
            pass

    def get_proxy_port(self) -> int:
        if self.instances:
            instance = self.instances[self.current_index]
            return instance.socks_port
        return 0

    def get_current_instance(self):
        if self.instances:
            return self.instances[self.current_index]
        return None

    def switch_to_next_instance(self):
        if not self.instances:
            return None
        
        if len(self.instances) == 1:
            current_instance = self.instances[0]
            
            def renew_single_ip():
                try:
                    current_instance.renew_ip()
                    
                    for attempt in range(5):
                        time.sleep(1)
                        if current_instance.is_circuit_ready():
                            break
                    
                    current_instance.get_ip(max_retries=2, retry_delay=0)
                except:
                    pass
            
            threading.Thread(target=renew_single_ip, daemon=True).start()
            return current_instance
        
        self.current_index = (self.current_index + 1) % len(self.instances)
        new_instance = self.instances[self.current_index]
        
        old_index = (self.current_index - 1) % len(self.instances)
        old_instance = self.instances[old_index]
        
        def prewarm_old_instance():
            try:
                old_instance.renew_ip()
                
                for attempt in range(5):
                    time.sleep(1)
                    if old_instance.is_circuit_ready():
                        break
                
                old_instance.get_ip(max_retries=2, retry_delay=0)
                
            except:
                pass
        
        threading.Thread(target=prewarm_old_instance, daemon=True).start()
        
        return new_instance