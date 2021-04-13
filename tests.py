import json
from peerbase import Node
import time, json

key = 'hVE3FNXnE_JnmmzGVuBOi4vc1XhIRina9tdS_IZZ8Tk='

node1 = Node('node1','peerbase/tests',key)
node2 = Node('node2','peerbase/tests',key,ports=[1004,1001,1002,1003])

node1.start_multithreaded(thread_name='peerbase/tests.node1.main')
node2.start_multithreaded(thread_name='peerbase/tests.node2.main')

while True:
    print(node1.peers, node2.peers)
    print(node1.send('Hello World'))
    time.sleep(2)