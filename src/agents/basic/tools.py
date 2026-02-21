from langchain_core.tools import tool


@tool("get_weather")
def get_weather(city: str) -> str:
    """Get weather for a given city."""
    return f"It's always sunny in {city}!"


@tool("add")
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


@tool("multiply")
def multiply(a: int, b: int) -> int:
    """Multiply two numbers."""
    return a * b
