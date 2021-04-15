# PeerBase
High-level p2p protocol allowing both local and remote p2p connections via UDP advertising and a TURN-like middleman server (or multiple)

## Features
- High-level abstraction of remote/local node commands
- Discovery of alternate relay servers via reporting from other nodes
- Fernet encryption of sent data
- Log-free relay servers
- Ability to connect to fallback relay servers
- E2EE on remote and local commands (encryption keys not sent to relay servers)
- RPC functionality
- Command paths

## Installation
Run `python -m pip install --upgrade peerbase`.

## Documentation (Basics)
The following documentation is laid out in the order in which functions should generally be called.

### Main Class: `Node()`
```
Node(name: str, network: str, network_key: str, ports: list=[1000,1001], servers: (str, list, None)=None, registered_commands: dict={}, use_local: bool=True, keepalive_tick: float=0.25, max_remotes: (int, None)=None)
```

- `name` - Name of node in network. Should not be repeated in a network, as this may cause inconsistent results. A check for this will be implemented in a future update. Cannot contain any of the following reserved characters: `.|:`
- `network` - Name of the virtual network or P2P channel to connect to. Cannot contain any of the following reserved characters: `.|:`
- `network_key` - Encryption key of the virtual network. Can use `peerbase.key_generate()` or similar to generate this key.
- `ports` - Ports to use for this node. In order, they are `[local node port (cannot be repeated), advertiser port (can be repeated across nodes)]`. This defaults to `[1000,1001]`
- `servers` - Relay servers to connect to. Can be `None` to disable remote connections, a single `ip:port` address, or a list of `ip:port` addresses. Defaults to `None`.
- `registered_commands` - A dictionary of pre-registered commands. Reference the **Registering Commands** section for more information. Defaults to `{}`.
- `use_local` - Boolean value of whether to make local connections or not. `Node()` will raise `ValueError` if both local and remote connections are disabled. Defaults to `True`.
- `keepalive_tick` - Seconds to wait between sending keepalive requests to relay servers. Defaults to 0.25 seconds.
- `max_remotes` - Maximum amount of relay servers to connect to. Must be greater than or equal to the length of `servers`. If `None`, no limit will be imposed. Defaults to `None`.

#### Registering Commands
Commands can (and should) be registered in Node instances to allow RPC functionality. When `Node()` is instantiated, three commands will be pre-registered in addition to those in `registered_commands`:
- `__echo__` - Will echo the args and kwargs back at the sender.
- `__list_commands__` - Will return a list of reciever commands.
- `__peers__` - Returns a list of the peers of the recieving Node.

`Node().register_command(command_path, function)` - Registers a single `function` at `command_path`. `function` should reference a python function that accepts three arguments:
  - `node` - The Node instance
  - `args` - A list of positional arguments
  - `kwargs` - A dictionary of keyword arguments

The function should return a JSON-encodeable value. The `command_path` argument should be the command name. If the command exists as a subcommand, separate path elements with periods like so: `path.to.function`.

`Node().register_commands(commands, top=None)` - Registers a dictionary of commands and subcommands at `top`. `top` should be a path to a command root, using the same path syntax as in `command_path` in `Node().register_command()`. The dictionary should follow the following syntax, which should also be used in the `registered_commands` argument of `Node()`:

```json
{
  "path":{
    "to":{
        "function":function(node, args, kwargs)
      },
      "function":function(node, args, kwargs)
    },
    "function":function(node, args, kwargs)
  }
```
Any number of paths and functions can be specified in this function.

#### Starting the Node
The `Node()` instance can be started with either of the following functions. Nodes must be started before they can be used.
- `Node().start()` - Starts the Node. This is blocking.
- `Node().start_multithreaded(thread_name=None, thread_group=None)` - Starts the instance in a separate thread with name `thread_name` in group `thread_group`.

#### Commanding Alternate Nodes
`Node().command(command_path='__echo__', args=[], kwargs={}, target='*', raise_errors=False, timeout=5, max_threads=32)` - Sends a command to a target or group of targets
- `command_path` - Path to command on target Node(s) in `path.to.command` format. Defaults to `__echo__`.
- `args` - Positional arguments to be sent to the target(s)
- `kwargs` - Keyword arguments to be sent to the target(s)
- `target` - Target or targets to send the command to. Can be a single Node name, a list of names, or `"*"` to send the command to all nodes in a network. The latter is not suggested for larger networks.
- `raise_errors` - Whether to raise errors on failure to connect to a Node.
- `timeout` - How long to wait before timing out an attempt to connect to a Node.
- `max_threads` - The maximum number of threads to open at any one time while processing commands.

This function will return either a single value (if only one target was specified) or a dictionary of `{node name: return value, ...}` if multiple were specified.

`Node().get_commands(target='*', raise_errors=False, timeout=4)` - Returns the commands of a node or number of nodes. Arguments identical to those in `Node().command()`.

### Relay Servers
A Relay server is a port-forwarded server that acts as a relay/middleman between individual Nodes on different LANs. The following section outlines how to start one of these servers in the simplest manner.

**Steps:**
- Open a terminal in the peerbase directory.
- Run the following command: `python relay.py --port <port to run server on> --network <name of network>`

Assuming all required libraries are installed, this will start the relay server.