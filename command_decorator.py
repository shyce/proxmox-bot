import inspect
import functools
import logging
from proxmox import get_proxmox_api, resolve_vm_identifier
from session_config import SessionConfig

def command(description: str):
    """
    `command` decorator: Facilitates the development of command interfaces in Proxmox environments by
    automatically managing command parameters, streamlining error handling, and optimizing command
    categorization based on function signatures.

    Features:
    1. **Command Grouping**: Extracts command groups from function names for logical organization.
    2. **API & Node Name Injection**: Dynamically injects Proxmox API objects and node names into functions,
    driven by session configuration and signature introspection, eliminating manual parameter specification.
    3. **Parameter Inference**: Leverages signature introspection to infer command parameters, including
    conditional handling of `node_name` and VM ID resolution, tailored to session context.
    4. **Adaptive Execution Logic**: Implements logic branches based on session node configuration, optimizing
    command syntax and execution pathways.
    5. **Syntax Optimization**: Automatically adjusts command parameter requirements and documentation based
    on session settings, minimizing user input complexity.
    6. **Error Handling & Feedback**: Integrates error detection and user feedback mechanisms, enhancing
    troubleshooting and user interaction.
    7. **Dynamic Argument Checks**: Performs runtime argument validation, ensuring command integrity and providing
    informative feedback on missing inputs.

    Usage is centered around enhancing function definitions within Proxmox-based command utilities, streamlining
    the creation and maintenance of a coherent, user-friendly command layer.
    """
    def decorator(func):
        func.__description__ = description
        func_name_parts = func.__name__.split('_', 1)
        func.__group__ = func_name_parts[0] if len(func_name_parts) > 1 else 'default'
        func.__command__ = func_name_parts[-1]
        func.__params__ = inspect.signature(func).parameters

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            proxmox_api = get_proxmox_api()
            if proxmox_api is None:
                logging.error("Failed to connect to Proxmox API.")
                return "🔴 Failed to connect to Proxmox API."

            session_node = SessionConfig.get_node()
            func_params = inspect.signature(func).parameters
            call_args = [proxmox_api]

            node_name_in_args = 'node_name' in func_params and 'node_name' in kwargs
            if 'node_name' in func_params and not node_name_in_args:
                if session_node:
                    call_args.append(session_node)
                elif args:
                    call_args.append(args[0])
                    args = args[1:]

            if 'vm_id' in func_params and args:
                node_name = call_args[1] if len(call_args) > 1 else None
                vm_id = args[0] if not node_name_in_args else kwargs.get('vm_id')

                if vm_id is not None:
                    resolved_vm_id = resolve_vm_identifier(node_name, vm_id)
                    if resolved_vm_id is None:
                        return f"🔴 Could not resolve VM identifier: {vm_id}"

                    if node_name_in_args:
                        kwargs['vm_id'] = resolved_vm_id
                    else:
                        args = (resolved_vm_id,) + args[1:]

            try:
                bound_args = inspect.signature(func).bind(*call_args, *args, **kwargs)
                bound_args.apply_defaults()
                return func(*bound_args.args, **bound_args.kwargs)
            except TypeError as e:
                return f"🔴 TypeError in {func.__name__}: {str(e)}."
            except Exception as e:
                return f"🔴 Error processing your request in {func.__name__}: {str(e)}"

        return wrapper
    return decorator