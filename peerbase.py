from cryptography.fernet import Fernet
import http.server
import requests
from socket import *
import socket as _socket
import threading
import time
import base64
import json
import typing


def key_generate():
    return Fernet.generate_key()

def ip():
    return gethostbyname(gethostname())

class LocalServerHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        node = self.server.node
        content_len = int(self.headers.get('content-length'))

        data = json.loads(node.decode(self.rfile.read(content_len)))

        print(data)

        self.send_response(200)
        self.end_headers()
        self.wfile.write(node.encode(json.dumps({
            'timestamp':time.time(),
            'received':data
        })))
        self.wfile.write(b'\n')

class LoadedThreadingHTTPServer(http.server.ThreadingHTTPServer):
    def __init__(self, server_address: typing.Tuple[str, int], RequestHandlerClass: typing.Callable[..., LocalServerHandler], node):
        super().__init__(server_address, RequestHandlerClass)
        self.node = node

class Node:
    def launch_advertising_loop(self):
        while self.running:
            data = f'{self.network}.{self.name}|{ip()}:{self.ports["local_server"]}'.encode(
                'utf-8')
            self.advertising_socket.sendto(
                data, ('<broadcast>', self.ports['local_advertiser']))
            time.sleep(1)
        self.advertising_socket.close()

    def discover(self, timeout=1.5):
        s = socket(AF_INET, SOCK_DGRAM)  # create UDP socket
        s.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        s.bind(('', self.ports['local_advertiser']))
        ct = time.time()
        discovered = {}
        while time.time() < ct+timeout:
            data, addr = s.recvfrom(1024)
            data = data.decode('utf-8')
            if data.startswith(self.network+'.'):
                try:
                    identifier, ip_addr = data.split('|')
                except ValueError:
                    continue
                try:
                    node_network, node_name = identifier.split('.')
                except ValueError:
                    continue
                try:
                    node_ip, node_port = ip_addr.split(':')
                except ValueError:
                    continue
                if node_name != self.name:
                    discovered[node_name] = (node_ip,int(node_port))
        return discovered

    def launch_discovery_loop(self):
        while self.running:
            self.peers = self.discover()

    def __init__(self, name, network, network_key, ports=[1000, 1001, 1002, 1003], server=None):
        if '.' in name or '|' in name or ':' in name:
            raise ValueError(
                f'Node name {name} contains reserved characters (".","|", or ":").')
        if '.' in network or '|' in network or ':' in network:
            raise ValueError(
                f'Network name {network} contains reserved characters (".","|", or ":").')
        if len(ports) != 4:
            raise ValueError('The list of ports to use must contain 4 values.')
        self.network = network
        self.name = name
        self.crypt = Fernet(network_key.encode('utf-8'))
        self.ports = {
            'local_server': ports[0],
            'local_transmitter': ports[1],
            'local_advertiser': ports[2],
            'remote_transciever': ports[3]
        }
        self.features = {}
        if server == None:
            self.features['remote'] = False
            print(
                'WARNING: No server specified. Will not be capable of forming remote connections.')
        else:
            self.features['remote'] = True
            self.server_info = server
        self.local_server = None
        self.running = False
        self.advertising_socket = socket(AF_INET, SOCK_DGRAM)
        self.advertising_socket.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        self.advertising_socket.bind(('', 0))
        self.advertising_socket.setsockopt(SOL_SOCKET, SO_BROADCAST, 1)
        self.advertising_thread = threading.Thread(
            target=self.launch_advertising_loop, name=f'{self.network}.{self.name}.advertiser')
        self.peers = {}
        self.discovery_thread = threading.Thread(
            target=self.launch_discovery_loop, name=f'{self.network}.{self.name}.discoverer')

    def decode(self, data):  # Recieves encrypted data in base64, returns string of data
        if type(data) == bytes:
            data = data.decode('utf-8')
        decoded_b64 = base64.urlsafe_b64decode(data.encode('utf-8'))
        return self.crypt.decrypt(decoded_b64).decode('utf-8')

    def encode(self, data):  # Recieves raw string data, returns base64-encoded encrypted data
        encrypted = self.crypt.encrypt(data.encode('utf-8'))
        return base64.urlsafe_b64encode(encrypted)

    def start(self):
        self.running = True
        self.local_server = LoadedThreadingHTTPServer((ip(),self.ports['local_server']),LocalServerHandler,self)
        self.advertising_thread.start()
        self.discovery_thread.start()

        self.local_server.serve_forever()

    def start_multithreaded(self, thread_name=None, thread_group=None):
        proc = threading.Thread(
            name=thread_name, target=self.start, group=thread_group)
        proc.start()
        self.discover()
        return proc
    
    def send(self,data,target='*',raise_errors=False,timeout=4,mime_type='text/plain'): # send <data> to <target>, returning the response. <target> accepts "*" for all, a list of target names, or a single target name
        if target == '*' or target == []:
            targets = list(self.peers.keys())
        elif type(target) == list:
            targets = target[:]
        else:
            targets = [target]
        
        returned = {}

        for i in targets:
            if not i in self.peers.keys():
                if raise_errors:
                    raise LookupError(f'Could not find target {i} in peers. Available peers: {str(len(self.peers.keys()))}')
                else:
                    continue
            try:
                resp = requests.post(
                    url=f'http://{self.peers[i][0]}:{self.peers[i][1]}',
                    data=self.encode(json.dumps({
                        'timestamp':time.time(),
                        'mime_type':mime_type,
                        'data':data,
                        'initiator':f'{self.network}.{self.name}'
                    })),
                    timeout=timeout
                )
            except requests.Timeout:
                if raise_errors:
                    raise TimeoutError(f'Attempt to reach peer {i} timed out after {str(timeout)} seconds.')
                else:
                    returned[i] = None
            returned[i] = json.loads(self.decode(resp.text))
        if len(targets) == 1:
            return returned[list(returned.keys())[0]]
        else:
            return returned
