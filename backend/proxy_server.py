import socket
import threading
import struct
import socketserver
import time
from typing import Optional, Tuple
from backend.tor_handler import TorPoolManager
from datetime import datetime
import asyncio
from concurrent.futures import ThreadPoolExecutor

class HybridProxyHandler(socketserver.BaseRequestHandler):
    
    def setup(self):
        self.pool_manager = self.server.pool_manager
        self.log_callback = self.server.log_callback
        self.timeout = 30  
        self.request.settimeout(self.timeout)
    
    def log(self, message, color="#ffffff"):
        if self.log_callback:
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.log_callback(f'<span style="color: {color};">[{timestamp}] {message}</span>')

    def detect_protocol(self, first_byte: int) -> str:
        if first_byte == 0x04:
            return "SOCKS4"
        elif first_byte == 0x05:
            return "SOCKS5"
        elif first_byte in (0x47, 0x48, 0x50, 0x43, 0x4F, 0x50): 
            return "HTTP"
        else:
            return "UNKNOWN"

    def relay_data(self, client_socket, remote_socket):
        def forward(source, destination):
            try:
                while True:
                    data = source.recv(8192)  
                    if not data:
                        break
                    destination.sendall(data)
            except:
                pass
            finally:
                try:
                    destination.shutdown(socket.SHUT_RDWR)
                    destination.close()
                except:
                    pass

        t1 = threading.Thread(target=forward, args=(client_socket, remote_socket), daemon=True)
        t2 = threading.Thread(target=forward, args=(remote_socket, client_socket), daemon=True)
        
        t1.start()
        t2.start()
        
        t1.join(timeout=30)  
        t2.join(timeout=30)

    def connect_to_tor(self, target_host, target_port):
        """Tor SOCKS portuna baglanir - OPTİMİZE."""
        tor_port = self.pool_manager.get_proxy_port()
        if not tor_port:
            return None

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(5) 
            s.connect(('127.0.0.1', tor_port))
            
            s.sendall(b'\x05\x01\x00')
            resp = s.recv(2)
            if not resp or resp[1] != 0x00:
                s.close()
                return None
            
            host_bytes = target_host.encode()
            req = struct.pack('>BB', 0x05, 0x01) + b'\x00' + \
                  b'\x03' + struct.pack('>B', len(host_bytes)) + host_bytes + \
                  struct.pack('>H', target_port)
            
            s.sendall(req)
            
            resp = s.recv(10)
            if not resp or resp[1] != 0x00:
                s.close()
                return None
            
            return s
        except Exception:
            return None

    def handle_http(self, data):
        first_line = data.split(b'\r\n')[0].decode('utf-8', errors='ignore')
        
        if "GET /rotate" in first_line:
            try:
                instance = self.pool_manager.get_current_instance()
                if not instance:
                    self.request.sendall(b"HTTP/1.1 500 Internal Server Error\r\n\r\nNo active instance")
                    return
                
                old_ip = instance.get_ip(max_retries=1, retry_delay=0)
                if old_ip == "...":
                    old_ip = "Hazırlanıyor"
                
                pool_size = len(self.pool_manager.instances)
                
                new_instance = self.pool_manager.switch_to_next_instance()
                
                new_ip = new_instance.get_ip(max_retries=1, retry_delay=0)
                if new_ip == "...":
                    new_ip = "Connecting..."
                
                elapsed_time = 0.1
                if pool_size == 1:
                    response_body = f"IP Renewal Started\nOld IP: {old_ip}\nPort: {new_instance.socks_port}\nNew IP: {new_ip}\nTime: {elapsed_time:.1f}s"
                else:
                    response_body = f"IP Rotation Started\nOld IP: {old_ip}\nNew Port: {new_instance.socks_port}\nNew IP: {new_ip}\nTime: {elapsed_time:.1f}s"
                response = f"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: {len(response_body)}\r\n\r\n{response_body}"
                self.request.sendall(response.encode())
                
            except Exception as e:
                error_response = f"HTTP/1.1 500 Internal Server Error\r\n\r\nError: {str(e)}"
                self.request.sendall(error_response.encode())
            return

        host = ""
        port = 80
        
        parts = first_line.split(' ')
        if len(parts) < 2:
            return
            
        method = parts[0]
        url = parts[1]
        
        if method == 'CONNECT':
            try:
                host, port_str = url.split(':')
                port = int(port_str)
            except:
                return
                
            tor_sock = self.connect_to_tor(host, port)
            if tor_sock:
                self.request.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                self.relay_data(self.request, tor_sock)
            else:
                self.request.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
                
        else:
            if 'http://' in url:
                try:
                    from urllib.parse import urlparse
                    u = urlparse(url)
                    host = u.hostname
                    port = u.port or 80
                except:
                    pass
            
            if not host:
                for line in data.split(b'\r\n'):
                    if line.lower().startswith(b'host:'):
                        host = line.split(b':', 1)[1].strip().decode()
                        if ':' in host:
                            host, port = host.split(':')
                            port = int(port)
                        break
            
            if host:
                tor_sock = self.connect_to_tor(host, port)
                if tor_sock:
                    tor_sock.sendall(data) # Istegi aynen ilet
                    self.relay_data(self.request, tor_sock)
                else:
                    self.request.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")

    def handle(self):
        try:
            header = self.request.recv(4096, socket.MSG_PEEK)
            if not header:
                return
            
            protocol = self.detect_protocol(header[0])
            
            if protocol == "HTTP":
                data = self.request.recv(65536)
                self.handle_http(data)
                
            elif protocol == "SOCKS5":
                pass 
                
        except Exception:
            pass
        finally:
            try:
                self.request.close()
            except:
                pass

class HybridProxyServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True
    
    def __init__(self, pool_manager: TorPoolManager, host: str = '0.0.0.0', port: int = 8080, log_callback=None):
        self.pool_manager = pool_manager
        self.log_callback = log_callback
        super().__init__((host, port), HybridProxyHandler)
        self.running = False
    
    def serve_forever(self):
        self.running = True
        try:
            super().serve_forever()
        except:
            pass
        finally:
            self.running = False

    def stop(self):
        self.shutdown()
        self.server_close()