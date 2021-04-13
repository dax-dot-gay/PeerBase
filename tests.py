import json
from peerbase import Node
import time, json

key = 'hVE3FNXnE_JnmmzGVuBOi4vc1XhIRina9tdS_IZZ8Tk='

node1 = Node('node1','peerbase/tests',key)
node2 = Node('node2','peerbase/tests',key,ports=[1002,1001])
node3 = Node('node3','peerbase/tests',key,ports=[1003,1001])

node1.start_multithreaded(thread_name='peerbase/tests.node1.main')
node2.start_multithreaded(thread_name='peerbase/tests.node2.main')
node3.start_multithreaded(thread_name='peerbase/tests.node2.main')

node2.register_commands({
    'user_defined':{
        'echo':node2._echo,
        'sublevel':{}
    }
})
node2.register_command('user_defined.sublevel.echo',node2._echo)

time.sleep(2)

print(node1.peers, node2.peers, node3.peers)
print('__echo__:                   ', node1.command(args=['test'], kwargs={'test':1}, target='*'))
print('user_defined.echo:          ', node1.command(command_path='user_defined.echo',args=['test'], kwargs={'test':1}, target='node2'))
print('user_defined.sublevel.echo: ', node1.command(command_path='user_defined.sublevel.echo',args=['test'], kwargs={'test':1}, target='node2'))
print('Formatted command list:     ', node1.command(command_path='__list_commands__', target='*'))
print('Done.')