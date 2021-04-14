from socket import *
from cryptography.fernet import Fernet
import copy

def key_generate():
    return Fernet.generate_key()

def ip():
    return gethostbyname(gethostname())

class InternalKeyError(KeyError):
    pass

def get_multikey(path, obj, sep='.'):
    cur = obj.copy()
    past = ['object']
    for i in path.split(sep):
        try:
            if type(cur) == list:
                try:
                    _i = int(i)
                except ValueError:
                    raise InternalKeyError(f'Attempted to get string index "{i}" of list at path {".".join(past)}')
            else:
                _i = copy.copy(i)
            cur = cur[i]
            past.append(i)
        except KeyError:
            raise InternalKeyError(f'Key {i} not found at path {".".join(past)}')
    return cur