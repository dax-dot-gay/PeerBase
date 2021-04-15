import json
import peerbase
import time, json

key = 'hVE3FNXnE_JnmmzGVuBOi4vc1XhIRina9tdS_IZZ8Tk='

def _echo(request, args, kwargs):
    return f'Echoed args {str(args)} and kwargs {str(kwargs)} at time [{time.ctime()}]'

node1 = peerbase.Node('node1','peerbase/tests',key)
node2 = peerbase.Node('node2','peerbase/tests',key,ports=[1002,1001],servers=[f'{peerbase.ip()}:2000'])
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

print(node1.peers, node2.peers, node3.peers)
print('__echo__:                   ', node1.command(args=['test'], kwargs={'test':1}, target='*'))
print('user_defined.echo:          ', node1.command(command_path='user_defined.echo',args=['test'], kwargs={'test':1}, target='node2'))
print('user_defined.sublevel.echo: ', node1.command(command_path='user_defined.sublevel.echo',args=['test'], kwargs={'test':1}, target='node2'))
print('Formatted command list:     ', node1.get_commands())

while True:
    #print(node2.peers, node2.remote_peers)
    if 'node3' in node2.remote_peers.keys():
        print(node2.command(target='node3'))