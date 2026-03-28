"""Agent Skills SDK — in-process execution and LLM-framework adapters.

Recommended imports::

    # Direct execution (no server needed)
    from sdk.embedded import execute, execute_capability
    from sdk.embedded import list_capabilities, list_skills

    # Native LLM provider tools
    from sdk.embedded import as_anthropic_tools, execute_anthropic_tool_call
    from sdk.embedded import as_openai_tools,    execute_openai_tool_call
    from sdk.embedded import as_gemini_tools,    execute_gemini_tool_call

    # Framework adapters
    from sdk.embedded import as_langchain_tools, as_crewai_tools
    from sdk.embedded import as_autogen_tools, as_semantic_kernel_functions
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("agent-skills")
except PackageNotFoundError:
    __version__ = "0.1.0+dev"

# Re-export public API so users can write:
#   from sdk import execute, as_openai_tools, ...
from sdk.embedded import (  # noqa: F401
    as_anthropic_tools,
    as_autogen_tools,
    as_crewai_tools,
    as_gemini_tools,
    as_langchain_tools,
    as_openai_tools,
    as_semantic_kernel_functions,
    execute,
    execute_anthropic_tool_call,
    execute_capability,
    execute_gemini_tool_call,
    execute_openai_tool_call,
    list_capabilities,
    list_skills,
)
