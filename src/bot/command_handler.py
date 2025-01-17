import inspect
import logging
from typing import Callable, Dict, List

from .commands import *
from .transformers import commands_to_markdown


class CommandHandler:
    """
    A class to manage commands and their execution.
    """

    _instance = None

    def __new__(cls, *args, **kwargs):
        """
        Override __new__ method to implement singleton pattern.
        """
        if not cls._instance:
            cls._instance = super().__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        """
        Initialize the CommandHandler.
        """
        if not hasattr(self, "initialized"):
            self.initialized = True
            self.command_functions = {}
            self.commands = []
            self.register_commands()
            self.generate_commands()

    def register_commands(self) -> None:
        for name, obj in globals().items():
            if inspect.isfunction(obj) and hasattr(obj, "__command__"):
                command_name = getattr(obj, "__command__")
                command_group = getattr(
                    obj, "__group__", "default"
                )  # Assume 'default' group if not specified
                logging.debug(f"Registering command: {
                             command_group} {command_name}")
                self.register_command(command_group, command_name, obj)

    def generate_commands(self) -> None:
        """
        Generate commands array based on registered command functions.
        """
        self.commands.clear()
        logging.debug("Generating commands...")
        for group, commands in self.command_functions.items():
            for command_name, command_func in commands.items():
                try:
                    signature = inspect.signature(command_func)
                    params = [
                        p for p in signature.parameters.values() if p.name != "proxmox"
                    ]  # Exclude 'proxmox' parameter
                    # Exclude 'default' group name from the command format
                    command_format = (
                        f"{command_name} {
                            ' '.join([f'<{param.name}>' for param in params])}"
                        if group == "default"
                        else f"{group} {command_name} {' '.join([f'<{param.name}>' for param in params])}"
                    )
                    description = getattr(command_func, "__description__", "No description available.")
                    self.commands.append(
                        {"command": command_format, "description": description}
                    )
                    logging.debug(f"Registered command: {command_format}")
                except Exception as e:
                    logging.error(
                        f"Error generating command for {
                            group} {command_name}: {e}"
                    )
        logging.debug("Commands generated successfully.")

    def register_command(
        self, command_group: str, command_name: str, func: Callable
    ) -> None:
        """
        Register a command function within a specific command group.

        Args:
            command_group (str): The name of the command group.
            command_name (str): The name of the command.
            func (Callable): The command function to register.
        """
        # Ensure that the command group is set to 'default' if not explicitly specified
        if not command_group:
            command_group = "default"

        # Check if the command group already exists, if not, create it
        if command_group not in self.command_functions:
            self.command_functions[command_group] = {}

        # Register the command within its group
        self.command_functions[command_group][command_name] = func
        logging.debug(
            f"Command '{command_name}' registered under group '{
                command_group}'"
        )

    def generate_help_message(self, command_group=None):
        all_groups_info = []
        for group, commands in self.command_functions.items():
            if command_group and group != command_group:
                continue
            
            group_commands_info = []
            for cmd, cmd_func in commands.items():
                func_params = inspect.signature(cmd_func).parameters
                param_names = [param for param in func_params if param not in ['proxmox', 'node_name']]
                
                if 'node_name' in func_params and not SessionConfig.get_node():
                    param_names.insert(0, 'node_name')  # Add 'node_name' if session node is not set
                
                command_format = f"{cmd} {' '.join([f'<{param}>' for param in param_names])}".strip()
                if group != 'default':
                    command_format = f"{group} {command_format}"
                    
                description = getattr(cmd_func, "__description__", "No description available.")
                group_commands_info.append({"command": command_format, "description": description})
            
            if group_commands_info:
                all_groups_info.append(commands_to_markdown(group_commands_info))

        return "\n".join(all_groups_info) if all_groups_info else "No commands found for this group."


    def parse_command(self, parts):
        """
        Parses the command string to identify the command group, command, and arguments.

        Args:
            parts (list): The message split into parts [command_group, command, args...]

        Returns:
            tuple: A tuple containing (command_group, command, args)
        """
        logging.debug(f"Starting to parse command with parts: {parts}")
        # Initialize default command group
        command_group = "default"

        # Check if the first part is explicitly specifying a command group
        if parts[0] in self.command_functions and len(parts) > 1:
            command_group = parts[0].lower()
            command = parts[1]
            args = parts[2:]
            logging.debug(
                f"Command group specified. Group: {
                    command_group}, Command: {command}, Args: {args}"
            )
        elif parts[0] in self.command_functions["default"]:
            # First part is a command in the default group
            command = parts[0]
            args = parts[1:]
            logging.debug(f"Default command group. Command: {
                         command}, Args: {args}")
        else:
            # Handle case where command might not follow expected structure
            command = parts[0]
            args = parts[1:]
            logging.warning(
                f"Command may not follow expected structure. Interpreted Command: {
                    command}, Args: {args}"
            )

        return command_group, command, args

    def respond(self, message: str) -> str:
        logging.debug(f"Received message: {message}")
        parts = message.strip().split()

        if not parts:
            logging.warning("No command parts found after splitting message.")
            return "Please provide a command. Type 'help' for a list of commands."

        if parts[0].lower() == "help":
            logging.debug("Generating help message.")
            if len(parts) > 1:
                command_group = parts[1].lower()
                return self.generate_help_message(command_group)
            else:
                return self.generate_help_message()

        command_group, command, user_args = self.parse_command(parts)
        logging.debug(
            f"Parsed command: Command Group - {command_group}, Command - {
                command}, User Args - {user_args}"
        )

        if (
            command_group in self.command_functions
            and command in self.command_functions[command_group]
        ):
            command_function = self.command_functions[command_group][command]
            logging.debug(f"Found command function: {command_function}")

            try:
                logging.debug(
                    f"Final arguments for command function: User Args - {
                        user_args}"
                )
                result = command_function(*user_args)
                logging.debug(
                    f"Command function executed successfully. Result: {result}"
                )
                return result
            except TypeError as e:
                logging.error(f"TypeError when calling {
                              command}: {e}", exc_info=True)
                return "Incorrect command usage. Please check the command format and try again."
            except Exception as e:
                logging.error(
                    f"An error occurred while executing {
                        command_group} {command}: {str(e)}",
                    exc_info=True,
                )
                return f"An error occurred: {str(e)}"
        else:
            logging.warning(
                f"Unknown command or command group: Command Group - {
                    command_group}, Command - {command}"
            )
            return (
                "Unknown command or command group. Type 'help' for a list of commands."
            )


handler = CommandHandler()
