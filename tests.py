import json
import peerbase
import time, json

key = 'hVE3FNXnE_JnmmzGVuBOi4vc1XhIRina9tdS_IZZ8Tk='

def _echo(request, args, kwargs):
    return f'Echoed args {str(args)} and kwargs {str(kwargs)} at time [{time.ctime()}]'

node1 = peerbase.Node('node1','peerbase/tests',key)
node2 = peerbase.Node('node2','peerbase/tests',key,ports=[1002,1001],servers=[f'{peerbase.ip()}:2000',f'{peerbase.ip()}:2001'])
node3 = peerbase.Node('node3','peerbase/tests',key,ports=[1003,1001],servers=[f'{peerbase.ip()}:2000'],use_local=False)

node1.start_multithreaded(thread_name='peerbase/tests.node1.main')
node2.start_multithreaded(thread_name='peerbase/tests.node2.main')
node3.start_multithreaded(thread_name='peerbase/tests.node3.main')

node2.register_commands({
    'user_defined':{
        'echo':_echo,
        'sublevel':{}
    }
})
node2.register_command('user_defined.sublevel.echo',_echo)

while True:
    #print(node2.peers, node2.remote_peers)
    if 'node3' in node2.remote_peers.keys():
        print(node2.get_commands())
        print(node2.server_info.keys(), node3.server_info.keys())
    time.sleep(2)