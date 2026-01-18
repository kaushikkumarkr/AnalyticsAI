from dataclasses import dataclass
from functools import wraps
from textwrap import dedent
from typing import Any, Callable, Optional

import click


def require_workspace():
    def require_workspace_inner(f: Callable[..., None]):
        @wraps(f)
        @click.pass_context
        def new_func(ctx: click.Context, *args: Any, **kwargs: Any):
            if ctx.obj.is_workspace_valid:
                return ctx.invoke(f, *args, **kwargs)
            else:
                click.echo(
                    "The current directory is not a valid Task Weaver project directory. "
                    "There needs to be a `taskweaver_config.json` in the root of the project directory. "
                    "Please change the working directory to a valid project directory or initialize a new one. "
                    "Refer to --help for more information.",
                )
                ctx.exit(1)

        return new_func

    return require_workspace_inner


@dataclass
class CliContext:
    workspace: Optional[str]
    workspace_param: Optional[str]
    is_workspace_valid: bool
    is_workspace_empty: bool


def center_cli_str(text: str, width: Optional[int] = None):
    import shutil

    width = width or shutil.get_terminal_size().columns
    lines = text.split("\n")
    max_line_len = max(len(line) for line in lines)
    return "\n".join((line + " " * (max_line_len - len(line))).center(width) for line in lines)


def get_ascii_banner(center: bool = True) -> str:
    text = dedent(
        r"""
        =================================================================
             _                _       _   _             _    ___ 
            / \   _ __   __ _| |_   _| |_(_) ___ ___   / \  |_ _|
           / _ \ | '_ \ / _` | | | | | __| |/ __/ __| / _ \  | | 
          / ___ \| | | | (_| | | |_| | |_| | (__\__ \/ ___ \ | | 
         /_/   \_\_| |_|\__,_|_|\__, |\__|_|\___|___/_/   \_\___|
                                |___/                            
        =================================================================
        """,
    ).strip()
    if center:
        return center_cli_str(text)
    else:
        return text
