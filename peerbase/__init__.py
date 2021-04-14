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
import copy
import traceback
from .relay import Relay
from .peer_utils import *

class LocalServerHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        node = self.server.node
        content_len = int(self.headers.get('content-length'))

        data = json.loads(node.decode(self.rfile.read(content_len)))

        command = data['command']
        args = data['args']
        kwargs = data['kwargs']

        try:
            resp = get_multikey(command,node.registered_commands)(self, args, kwargs)
            stat = 200
        except InternalKeyError:
            stat = 404
            resp = f'CMD "{command}" NOT FOUND'
        except:
            stat = 500
            resp = traceback.format_exc()

        self.send_response(stat)
        self.end_headers()
        self.wfile.write(node.encode(json.dumps({
            'timestamp':time.time(),
            'response':resp
        })))
        self.wfile.write(b'\n')
    def log_message(self, format, *args):
        pass

class LoadedThreadingHTTPServer(http.server.ThreadingHTTPServer):
    def __init__(self, server_address: typing.Tuple[str, int], RequestHandlerClass: typing.Callable[..., LocalServerHandler], node):
        super().__init__(server_address, RequestHandlerClass)
        self.node = node

def format_dict(dct, sep='.', start=''):
    dct = dct.copy()
    to_ret = []
    for i in dct.keys():
        if type(dct[i]) == dict:
            to_ret.extend(format_dict(dct[i], sep=sep, start=f'{start}{i}.'))
        else:
            to_ret.append(start+i)
    return to_ret

class Node:
    # Default commands
    def _echo(self, request, args, kwargs):
        return f'Echoed args {str(args)} and kwargs {str(kwargs)} at time [{time.ctime()}]'
    
    def list_methods(self, request, args, kwargs):
        return format_dict(self.registered_commands)
    
    def get_peers(self, request, args, kwargs):
        return self.peers

    # Threaded Loops
    def launch_advertising_loop(self):
        while self.running:
            data = f'{self.network}.{self.name}|{ip()}:{self.ports["local_server"]}'.encode(
                'utf-8')
            self.advertising_socket.sendto(
                data, ('<broadcast>', self.ports['local_advertiser']))
            time.sleep(1)
        self.advertising_socket.close()

    def discover(self, timeout=1.5): # Get dict of {peer name: (peer IP, peer port)} for all peers in local network
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

    def __init__(self, name, network, network_key, ports=[1000, 1001], server=None, registered_commands={}):
        '''
        name: Name of node in network (cannot contain ".", "|", or ":")
        network: Name of network (cannot contain ".", "|", or ":")
        network_key: str encryption key to use within the network
        ports: [local server port, local UDP advertiser port]
        server: address or list of addresses of remote middleman servers
        registered_commands: dict (may be nested to have sub/sub-sub/etc commands) of command names related to functions.
            Reserved names in top-level tree: __echo__, __list_commands__, __peers__
        '''

        if '.' in name or '|' in name or ':' in name:
            raise ValueError(
                f'Node name {name} contains reserved characters (".","|", or ":").')
        if '.' in network or '|' in network or ':' in network:
            raise ValueError(
                f'Network name {network} contains reserved characters (".","|", or ":").')
        if len(ports) != 2:
            raise ValueError('The list of ports to use must contain 2 values.')
        self.network = network
        self.name = name
        self.crypt = Fernet(network_key.encode('utf-8'))
        self.ports = {
            'local_server': ports[0],
            'local_advertiser': ports[1]
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
            target=self.launch_advertising_loop, name=f'{self.network}.{self.name}.advertiser', daemon=True)
        self.peers = {}
        self.discovery_thread = threading.Thread(
            target=self.launch_discovery_loop, name=f'{self.network}.{self.name}.discoverer', daemon=True)
        
        self.registered_commands = registered_commands.copy()
        self.registered_commands['__echo__'] = self._echo
        self.registered_commands['__list_commands__'] = self.list_methods
        self.registered_commands['__peers__'] = self.get_peers

    def decode(self, data):  # Recieves encrypted data in base64, returns string of data
        if type(data) == bytes:
            data = data.decode('utf-8')
        decoded_b64 = base64.urlsafe_b64decode(data.encode('utf-8'))
        return self.crypt.decrypt(decoded_b64).decode('utf-8')

    def encode(self, data):  # Recieves raw string data, returns base64-encoded encrypted data
        encrypted = self.crypt.encrypt(data.encode('utf-8'))
        return base64.urlsafe_b64encode(encrypted)

    def start(self): # Start the node. This method is blocking.
        self.running = True
        self.local_server = LoadedThreadingHTTPServer((ip(),self.ports['local_server']),LocalServerHandler,self)
        self.advertising_thread.start()
        self.discovery_thread.start()

        self.local_server.serve_forever()

    def start_multithreaded(self, thread_name=None, thread_group=None): # Start the Node in a separate thread
        proc = threading.Thread(
            name=thread_name, target=self.start, group=thread_group, daemon=True)
        proc.start()
        self.peers = self.discover()
        return proc
    
    def command(self,command_path='__echo__',args=[],kwargs={},target='*',raise_errors=False,timeout=4): # send <data> to <target>, returning the response. <target> accepts "*" for all, a list of target names, or a single target name
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
                        'command':command_path,
                        'args':args,
                        'kwargs':kwargs,
                        'initiator':f'{self.network}.{self.name}'
                    })),
                    timeout=timeout
                )
            except requests.Timeout:
                if raise_errors:
                    raise TimeoutError(f'Attempt to reach peer {i} timed out after {str(timeout)} seconds.')
                else:
                    returned[i] = None
            if resp.status_code == 200:
                returned[i] = json.loads(self.decode(resp.text))['response']
            else:
                returned[i] = None
                print(f'Encountered error with status {str(resp.status_code)}:\n{json.loads(self.decode(resp.text))["response"]}')
        if len(targets) == 1:
            return returned[list(returned.keys())[0]]
        else:
            return returned
    
    def register_command(self, command_path, function): # Register <function> at <command_path>
        try:
            translated_path = '"]["'.join([i for i in command_path.split('.')])
            exec(f'self.registered_commands["{translated_path}"] = function', globals(), {'self':self, 'function':function})
        except KeyError:
            raise KeyError(f'Unable to register {command_path} as the path to it does not exist.')
    
    def register_commands(self, commands, top=None): # Register dict of <commands>. If <top> != None, will use <top> as the starting point.
        if top == None:
            for i in commands.keys():
                if type(commands[i]) == dict:
                    cmd = commands[i].copy()
                else:
                    cmd = copy.copy(commands[i])
                self.registered_commands[i] = cmd
        else:
            for i in commands.keys():
                if type(commands[i]) == dict:
                    cmd = commands[i].copy()
                else:
                    cmd = copy.copy(commands[i])
                try:
                    translated_path = '"]["'.join([i for i in top.split('.')])
                    exec(f'self.registered_commands["{translated_path}"][i] = cmd', globals(), {'self':self, 'i':i, 'cmd':cmd})
                except KeyError:
                    raise KeyError(f'Unable to register commands to {top} as the path to it does not exist.')
    
    def get_commands(self, target='*', raise_errors=False, timeout=4): # Utility function to list methods of target(s). Similar args as with command()
        return self.command(command_path='__list_commands__', target=target, raise_errors=raise_errors, timeout=timeout)
