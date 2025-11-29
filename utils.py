import inspect
import re
import time
import itertools
import sys
import asyncio


async def spinner(awaitable):
    """Show a spinner while awaiting the completion of an async function"""
    if not sys.stdout.isatty():
        return await awaitable
    (t0, spinner, task) = (time.time(), itertools.cycle("🌑🌒🌓🌔🌕🌖🌗🌘"), asyncio.ensure_future(awaitable))
    try:
        while True:
            sys.stdout.write(f"\r{next(spinner)} {time.time() - t0:.1f}s")
            sys.stdout.flush()
            try:
                return await asyncio.wait_for(asyncio.shield(task), timeout=0.2)
            except asyncio.TimeoutError:
                continue
    finally:
        sys.stdout.write("\r" + " " * 30 + "\r")


async def try_repeatedly(awaitable):
    """Retry an async operation indefinitely with exponential backoff."""
    attempt = 0
    while True:
        try:
            return await awaitable
        except Exception as e:
            # TODO: parse e and print a more informative message
            attempt += 1
            delay = min(2 ** (attempt - 1), 60)  # Cap at 60 seconds
            print(f"! Operation failed: {e}")
            print(f"  Retrying in {delay}s (attempt {attempt})...")
            await asyncio.sleep(delay)


def as_described(desc):
    def decorator(func):
        func.__doc__ = desc + (func.__doc__ or "")
        return func
    return decorator


def function_to_tool(func,name=None):
    """Convert a function with a docstring to a litellm tool description."""
    doc = inspect.getdoc(func)
    if not doc: raise ValueError(f"Function {func.__name__} has no docstring")
    lines = doc.split('\n')

    description_lines = []
    for line in lines:
        if re.match(r'^(Args|Returns|Raises):\s*$', line.strip()): break
        description_lines.append(line)
    description = '\n'.join(description_lines).strip()

    args_section = _extract_section(doc, 'Args')
    if not args_section: raise ValueError(f"Function {func.__name__} has no Args section")
    param_info = _parse_args_section(args_section)
    sig = inspect.signature(func) # for working out which args are required
    properties = {}
    required = []
    
    for (param_name, param) in sig.parameters.items():
        if param_name == 'self': continue
        if param_name not in param_info: raise ValueError(f"Parameter {param_name} not documented in docstring")
        (type_str, desc) = param_info[param_name]
        properties[param_name] = _parse_type_string(type_str, desc)
        if param.default == inspect.Parameter.empty: required.append(param_name)
    
    return {
        "type": "function",
        "function": {
            "name": func.__name__ if name is None else name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }

def _extract_section(doc, section_name):
    """Extract a section from docstring (e.g., 'Args', 'Returns')."""
    pattern = rf'^{section_name}:\s*$'
    lines = doc.split('\n')
    start_idx = None
    for i, line in enumerate(lines):
        if re.match(pattern, line.strip()):
            start_idx = i + 1
            break
    if start_idx is None: return None
    end_idx = len(lines)
    for i in range(start_idx, len(lines)):
        if lines[i].strip() and not lines[i].startswith(' '):
            end_idx = i
            break
    return '\n'.join(lines[start_idx:end_idx])

def _parse_args_section(args_text):
    """Parse Args section into dict of param_name -> (type, description)."""
    result = {}
    lines = args_text.split('\n')
    current_param = None
    current_type = None
    current_desc = []
    for line in lines:
        # Match: "param_name (type): description"
        match = re.match(r'^\s+(\w+)\s*\(([^)]+)\):\s*(.*)', line)
        if match:
            if current_param:
                result[current_param] = (current_type, ' '.join(current_desc).strip())
            current_param = match.group(1)
            current_type = match.group(2).strip()
            current_desc = [match.group(3)]
        elif current_param and line.strip():
            current_desc.append(line.strip())
    if current_param:
        result[current_param] = (current_type, ' '.join(current_desc).strip())
    return result



def _parse_type_string(type_str, description):
    """Convert type string from docstring to JSON schema."""
    schema = {"description": description}
    
    # Remove optional markers and get base type
    type_str = type_str.lower().strip()
    
    # Handle enum syntax: "str, one of ['celsius', 'fahrenheit']" or similar
    enum_match = re.search(r'\[([^\]]+)\]', type_str)
    if enum_match and ('one of' in type_str or 'enum' in type_str):
        enum_values = [v.strip().strip("'\"") for v in enum_match.group(1).split(',')]
        schema["enum"] = enum_values
        if enum_values:
            schema["type"] = "string"
        return schema
    
    # Handle list[type] syntax
    list_match = re.match(r'list\[(\w+)\]', type_str)
    if list_match:
        inner_type = list_match.group(1)
        schema["type"] = "array"
        schema["items"] = {"type": _map_simple_type(inner_type)}
        return schema
    
    # Map common type strings to JSON schema types
    if 'int' in type_str:
        schema["type"] = "integer"
    elif 'float' in type_str or 'number' in type_str:
        schema["type"] = "number"
    elif 'bool' in type_str:
        schema["type"] = "boolean"
    elif 'str' in type_str or 'string' in type_str:
        schema["type"] = "string"
    elif 'list' in type_str or 'array' in type_str:
        schema["type"] = "array"
        schema["items"] = {"type": "string"}  # default to string
    elif 'dict' in type_str or 'object' in type_str:
        schema["type"] = "object"
    else:
        schema["type"] = "string"
    
    return schema

def _map_simple_type(type_str):
    """Map a simple type string to JSON schema type."""
    type_str = type_str.lower().strip()
    if type_str == 'int' or type_str == 'integer':
        return 'integer'
    elif type_str == 'float' or type_str == 'number':
        return 'number'
    elif type_str == 'bool' or type_str == 'boolean':
        return 'boolean'
    else:
        return 'string'

