import typing
from starlette.status import HTTP_404_NOT_FOUND
import uvicorn
from fastapi import status, FastAPI, Request, Response
try:
    from peerbase.peer_utils import *
except ImportError:
    from peer_utils import *
from threading import Thread
import base64
import argparse
import json
from pydantic import BaseModel
import os
import logging
import time
import requests

logging.basicConfig(format='%(levelname)s:%(message)s',level=0)

app = FastAPI()

class Relay:
    def __init__(self, port, clear_time=1.5, save_to=None, peers={}, altservers=[]):
        logging.info(f'Instantiating relay on port {str(port)}.')
        self.port = port
        self.peers = peers
        self.altservers = set(altservers)
        self.save_location = save_to
        self.clear_time = clear_time

        self.save_state()

    @classmethod
    def from_config(cls, path):  # Load new instance from config
        logging.info(f'Loading new relay from config file {path}.')
        with open(path, 'r') as f:
            conf = json.load(f)
        return cls(conf['port'], save_to=conf['save_location'], clear_time=conf['clear_time'])

    @classmethod
    def from_state(cls, path, config=None):  # Load saved instance from JSON file
        logging.info(f'Loading saved relay from state file {path}.')
        if os.path.exists(path):
            with open(path, 'r') as f:
                conf = json.load(f)
            return cls(conf['port'], save_to=conf['save_location'], peers=conf['peers'], altservers=conf['altservers'], clear_time=conf['clear_time'])
        elif config:
            logging.warning(f'No state file found at {path}. Loading new instance from config file {config}')
            return cls.from_config(config)
        else:
            raise OSError('State file not found and no initial configuration file has been provided.')

    def save_state(self):
        if self.save_location:
            with open(self.save_location, 'w') as f:
                state = {
                    'port': self.port,
                    'save_location': self.save_location,
                    'peers': self.peers,
                    'altservers': list(self.altservers),
                    'clear_time': self.clear_time
                }
                json.dump(state, f)

    def decode(self, data):  # Recieves encrypted data in base64, returns string of data
        if type(data) == bytes:
            data = data.decode('utf-8')
        decoded_b64 = base64.urlsafe_b64decode(data.encode('utf-8'))
        return self.crypt.decrypt(decoded_b64).decode('utf-8')

    def encode(self, data):  # Recieves raw string data, returns base64-encoded encrypted data
        encrypted = self.crypt.encrypt(data.encode('utf-8'))
        return base64.urlsafe_b64encode(encrypted)


parser = argparse.ArgumentParser(
    description='Start PeerBase Relay server.')
parser.add_argument(
    '--state', help='Path to json file of saved state. If not specified, will default to config, then passed args.', default=None)
parser.add_argument(
    '--config', help='Path to config file. If not specified, will default to using alternate arguments', default=None)
parser.add_argument(
    '--port', help='Port to run relay server on.', default=0, type=int)
parser.add_argument(
    '--saveloc', help='Location to save the server state to. Defaults to None, in which case no states will be saved.', default=None)
parser.add_argument(
    '--timeout', help='Seconds to wait for another keepalive request before removing an active peer.', default=0.5, type=float)

args = parser.parse_args()

if args.state:
    relay = Relay.from_state(args.state, config=args.config)
elif args.config:
    relay = Relay.from_config(args.config)
elif args.port > 0:
    relay = Relay(args.port,
                    save_to=args.saveloc, clear_time=args.timeout)
else:
    raise ValueError(
        'Please include --state, --config, or [--port, --network, and optionally --saveloc]')

# Define endpoints
class PingRequestModel(BaseModel):
    node_name: str
    node_network: str
    known_servers: list

@app.get('/')
async def root():
    return {'time':time.ctime()}

@app.post('/ping')
async def ping(model: PingRequestModel, request: Request, response: Response):
    global relay
    if not model.node_network in relay.peers.keys():
        relay.peers[model.node_network] = {}
    if model.node_name in relay.peers[model.node_network].keys():
        relay.peers[model.node_network][model.node_name]['timeout'] = time.time()
    else:
        relay.peers[model.node_network][model.node_name] = {
            'timeout':time.time(),
            'buffer':{}
        }
    for s in model.known_servers:
        if not s in relay.altservers:
            relay.altservers.add(s)
    buf = relay.peers[model.node_network][model.node_name]['buffer'].copy()
    relay.peers[model.node_network][model.node_name]['buffer'] = {}
    return {
        'peers': list(relay.peers[model.node_network].keys()),
        'servers': list(relay.altservers),
        'buffer': buf
    }

class SendDataRequestModel(BaseModel):
    target: str
    data: str
    packet_id: str
    originator: str
    r_type: str
    remote_addr: str

@app.post('/send')
async def send(model: SendDataRequestModel, request: Request, response: Response):
    global relay
    serv = None
    for i in relay.peers.keys():
        if model.originator in relay.peers[i].keys():
            serv = i
            break
    if serv == None:
        response.status_code = status.HTTP_404_NOT_FOUND
        return {'detail':f'originator {model.originator} is not in any known servers.'}
    if not model.target in relay.peers[serv].keys():
        response.status_code = status.HTTP_404_NOT_FOUND
        return {'detail':f'target {model.target} not found in peers.'}
    relay.peers[serv][model.target]['buffer'][model.packet_id] = {
        'originator': model.originator,
        'data': model.data,
        'type': model.r_type,
        'remote': model.remote_addr
    }
    return {'pid': model.packet_id}

def check_peers_loop():
    global relay
    while True:
        for s in list(relay.peers.keys()):
            for i in list(relay.peers[s].keys()):
                if relay.peers[s][i]['timeout'] + relay.clear_time < time.time():
                    del relay.peers[s][i]
            if len(relay.peers[s].keys()) == 0:
                del relay.peers[s]
        time.sleep(relay.clear_time)

def check_altservers_loop():
    global relay
    while True:
        for s in list(relay.altservers):
            try:
                requests.get(s)
            except requests.ConnectionError:
                relay.altservers.remove(s)
        time.sleep(30)

def save_state_loop():
    global relay
    while True:
        relay.save_state()
        time.sleep(5)

check_peers_thread = Thread(target=check_peers_loop, name='peerbase.relay.check_peers', daemon=True)
check_altservers_thread = Thread(target=check_altservers_loop, name='peerbase.relay.check_altservers', daemon=True)
save_state_thread = Thread(target=save_state_loop, name='peerbase.relay.save_state', daemon=True)

if __name__ == '__main__':
    print([i.path for i in app.routes])
    logging.info(f'Starting relay server on http://{ip()}:{str(relay.port)}')
    check_peers_thread.start()
    check_altservers_thread.start()
    save_state_thread.start()
    uvicorn.run('relay:app', host=ip(), port=relay.port, access_log=False)