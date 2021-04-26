from cryptography.fernet import Fernet
import http.server
import requests
from socket import *
import threading
import time
import base64
import json
import typing
import copy
import traceback
from peerbase.peer_utils import *
import random
import hashlib
from concurrent.futures import ThreadPoolExecutor


def process_request(data, node):
    data = json.loads(node.decode(data))
    command = data['command']
    args = data['args']
    kwargs = data['kwargs']

    try:
        resp = get_multikey(command, node.registered_commands)(
            node, args, kwargs)
        stat = 200
    except InternalKeyError:
        stat = 404
        resp = f'CMD "{command}" NOT FOUND'
    except:
        stat = 500
        resp = traceback.format_exc()
    return stat, resp


class LocalServerHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        node = self.server.node
        content_len = int(self.headers.get('content-length'))

        stat, resp = process_request(self.rfile.read(content_len), node)

        self.send_response(stat)
        self.end_headers()
        self.wfile.write(node.encode(json.dumps({
            'timestamp': time.time(),
            'response': resp
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
    def _echo(self, node, args, kwargs):
        return f'Echoed args {str(args)} and kwargs {str(kwargs)} at time [{time.ctime()}]'

    def list_methods(self, node, args, kwargs):
        return format_dict(self.registered_commands)

    def get_peers(self, node, args, kwargs):
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

    # Get dict of {peer name: (peer IP, peer port)} for all peers in local network
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
                    discovered[node_name] = (node_ip, int(node_port))
        return discovered

    def launch_discovery_loop(self):
        while self.running:
            self.peers = self.discover()

    def process_single_buffer(self, pid, buffer_data):
        stat, resp = process_request(buffer_data['data'], self)
        try:
            resp = requests.post(
                url=f'http://{buffer_data["remote"]}/send/',
                json={
                    'target': buffer_data['originator'],
                    'data': self.encode(json.dumps({
                        'status': stat,
                        'result': resp
                    })).decode('utf-8'),
                    'packet_id': pid,
                    'originator': self.name,
                    'r_type': 'response',
                    'remote_addr': buffer_data['remote']
                }
            )
        except ConnectionError:
            pass

    def remote_keepalive_loop(self, target):
        while self.running:
            try:
                resp = requests.post(f'http://{target}/ping/', json={
                    'node_name': self.name,
                    'node_network': self.network,
                    'known_servers': list(self.server_info.keys())
                })
                dat = resp.json()
                for i in dat['peers']:
                    if not i == self.name:
                        if not i in self.remote_peers.keys():
                            self.remote_peers[i] = {target}
                        else:
                            self.remote_peers[i].add(target)

                for s in dat['servers']:
                    if not s in self.server_info.keys() and len(self.server_info.keys()) < self.max_remotes:
                        self.server_info[s] = {
                            'maintain': False,
                            'active': True,
                            'peers': set(),
                            'thread': threading.Thread(target=self.remote_keepalive_loop, args=[s], name=f'{self.network}.{self.name}.remote_keepalive[{s}]', daemon=True)
                        }
                        self.server_info[s]['thread'].start()

                for b in dat['buffer'].keys():
                    if dat['buffer'][b]['type'] == 'response':
                        self.remote_buffer[b] = dat['buffer'][b]
                    else:
                        threading.Thread(target=self.process_single_buffer, args=[
                                         b, dat['buffer'][b]], name=f'{self.network}.{self.name}.process_request[{b}]', daemon=True).start()
            except requests.ConnectionError:
                self.server_info[target]['active'] = False
                if not self.server_info[target]['maintain']:
                    del self.server_info[target]
                    for k in list(self.remote_peers.keys()):
                        if target in self.remote_peers[k]:
                            self.remote_peers[k].remove(target)
                    return

            if self.server_info[target]['active']:
                time.sleep(self.keepalive_tick)
            else:
                time.sleep(30)

    def __init__(
        self,
        name,
        network,
        network_key,
        ports=[1000, 1001],
        servers=None,
        registered_commands={},
        use_local=True,
        keepalive_tick=0.25,
        max_remotes=None
    ):
        '''
        name: Name of node in network (cannot contain ".", "|", or ":")
        network: Name of network (cannot contain ".", "|", or ":")
        network_key: str encryption key to use within the network
        ports: [local server port, local UDP advertiser port]
        servers: address or list of addresses of remote middleman servers
        registered_commands: dict (may be nested to have sub/sub-sub/etc commands) of command names related to functions.
            Reserved names in top-level tree: __echo__, __list_commands__, __peers__
        use_local: boolean, make local connections/do not make local connections
        keepalive_tick: time between keepalive requests
        max_remotes: max number of remotes to connect to at one time. Must be >= len(servers), or None to remove the limit.
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
        if servers == None:
            self.features['remote'] = False
            print(
                'WARNING: No server specified. Will not be capable of forming remote connections.')
            self.remote_buffer = None
        else:
            self.features['remote'] = True
            if type(servers) == str:
                servers = [servers]
            if max_remotes != None and max_remotes < len(servers):
                raise ValueError(
                    'max_remotes cannot be less than the number of servers provided.')
            self.server_info = {s: {
                'maintain': True,
                'active': True,
                'peers': set(),
                'thread': threading.Thread(target=self.remote_keepalive_loop, args=[s], name=f'{self.network}.{self.name}.remote_keepalive[{s}]', daemon=True)
            } for s in servers}
            self.remote_buffer = {}
        self.features['local'] = bool(use_local)

        if not self.features['remote'] and not self.features['local']:
            raise ValueError(
                'Must enable either local or remote connections, or both.')

        self.max_remotes = max_remotes
        if self.max_remotes == None:
            self.max_remotes = 1e99
        self.local_server = None
        self.running = False
        self.advertising_socket = socket(AF_INET, SOCK_DGRAM)
        self.advertising_socket.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        self.advertising_socket.bind(('', 0))
        self.advertising_socket.setsockopt(SOL_SOCKET, SO_BROADCAST, 1)
        self.advertising_thread = threading.Thread(
            target=self.launch_advertising_loop, name=f'{self.network}.{self.name}.advertiser', daemon=True)
        self.peers = {}
        self.remote_peers = {}
        self.keepalive_tick = keepalive_tick
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

    def start(self):  # Start the node. This method is blocking.
        self.running = True
        if self.features['local']:
            self.local_server = LoadedThreadingHTTPServer(
                (ip(), self.ports['local_server']), LocalServerHandler, self)
            self.advertising_thread.start()
            self.discovery_thread.start()
        if self.features['remote']:
            [i['thread'].start() for i in self.server_info.values()]

        if self.features['local']:
            self.local_server.serve_forever()

    # Start the Node in a separate thread
    def start_multithreaded(self, thread_name=None, thread_group=None):
        proc = threading.Thread(
            name=thread_name, target=self.start, group=thread_group, daemon=True)
        proc.start()
        if self.features['local']:
            self.peers = self.discover()
        return proc

    def _command_one(self, command_path, args, kwargs, target, raise_errors, timeout):
        ret = None
        i = target
        if i in self.peers.keys() and self.features['local']:
            '''if raise_errors:
                raise LookupError(
                    f'Could not find target {i} in peers. Available peers: {str(len(self.peers.keys()))}')
            else:
                continue'''
            try:
                resp = requests.post(
                    url=f'http://{self.peers[i][0]}:{self.peers[i][1]}',
                    data=self.encode(json.dumps({
                        'timestamp': time.time(),
                        'command': command_path,
                        'args': args,
                        'kwargs': kwargs,
                        'initiator': f'{self.network}.{self.name}'
                    })),
                    timeout=timeout
                )
            except requests.Timeout:
                if raise_errors:
                    raise TimeoutError(
                        f'Attempt to reach peer {i} timed out after {str(timeout)} seconds.')
                else:
                    ret = None
            if resp.status_code == 200:
                ret = json.loads(self.decode(resp.text))[
                    'response']
            else:
                ret = None
                print(
                    f'Encountered error with status {str(resp.status_code)}:\n{json.loads(self.decode(resp.text))["response"]}')
        elif i in self.remote_peers.keys() and self.features['remote']:
            while len(self.remote_peers[i]) > 0 and ret == None:
                remote_target = random.choice(list(self.remote_peers[i]))
                pid = hashlib.sha256(
                    str(time.time() + random.random()).encode('utf-8')).hexdigest()
                try:
                    resp = requests.post(
                        url=f'http://{remote_target}/send/',
                        json={
                            'target': i,
                            'data': self.encode(json.dumps({
                                'timestamp': time.time(),
                                'command': command_path,
                                'args': args,
                                'kwargs': kwargs,
                                'initiator': f'{self.network}.{self.name}'
                            })).decode('utf-8'),
                            'packet_id': pid,
                            'originator': self.name,
                            'r_type': 'request',
                            'remote_addr': remote_target
                        }
                    )
                    if resp.status_code != 200:
                        raise requests.ConnectionError
                    wait_start = time.time()
                    if timeout == None:
                        _t = -1
                    else:
                        _t = timeout + 0
                    while not pid in self.remote_buffer.keys() and (wait_start + _t > time.time() or _t == -1):
                        pass
                    if pid in self.remote_buffer.keys():
                        res = json.loads(self.decode(
                            copy.deepcopy(self.remote_buffer[pid])['data']))
                        if res['status'] == 200:
                            ret = res['result']
                        else:
                            print(
                                f'Encountered error with status {str(res["status"])}:\n{res["result"]}')
                        del self.remote_buffer[pid]
                    else:
                        raise requests.ConnectionError
                except (requests.ConnectionError, requests.Timeout):
                    self.remote_peers[i].remove(remote_target)
            if ret == None:
                del self.remote_peers[i]
                if raise_errors:
                    raise TimeoutError(
                        f'Attempt to reach peer {i} remotely failed.')
                else:
                    pass
                    
        else:
            if raise_errors:
                raise LookupError(
                    f'Could not find target {i} in remote peers. Available peers: {str(len(self.remote_peers.keys()))}')
            else:
                pass
        
        return ret

    def command(self, command_path='__echo__', args=[], kwargs={}, target='*', raise_errors=False, timeout=5, max_threads=32):
        if target == '*' or target == []:
            targets = list(self.peers.keys())
            targets.extend(list(self.remote_peers.keys()))
        elif type(target) == list:
            targets = target[:]
        else:
            targets = [target]

        with ThreadPoolExecutor(max_workers=max_threads) as executor:
            returned = {i:executor.submit(self._command_one,command_path,args,kwargs,i,raise_errors,timeout) for i in targets}
        
        returned = {i:returned[i].result() for i in returned.keys()}
        if len(targets) == 1:
            return returned[list(returned.keys())[0]]
        else:
            return returned

    # Register <function> at <command_path>
    def register_command(self, command_path, function):
        try:
            translated_path = '"]["'.join([i for i in command_path.split('.')])
            exec(f'self.registered_commands["{translated_path}"] = function', globals(), {
                 'self': self, 'function': function})
        except KeyError:
            raise KeyError(
                f'Unable to register {command_path} as the path to it does not exist.')

    # Register dict of <commands>. If <top> != None, will use <top> as the starting point.
    def register_commands(self, commands, top=None):
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
                    exec(f'self.registered_commands["{translated_path}"][i] = cmd', globals(), {
                         'self': self, 'i': i, 'cmd': cmd})
                except KeyError:
                    raise KeyError(
                        f'Unable to register commands to {top} as the path to it does not exist.')

    # Utility function to list methods of target(s). Similar args as with command()
    def get_commands(self, target='*', raise_errors=False, timeout=4):
        return self.command(command_path='__list_commands__', target=target, raise_errors=raise_errors, timeout=timeout)
