# LLM Helpers

This directory contains helper modules for working with Large Language Models (LLMs) in the DIMS-AI project.

## Files

- `custom_google.py` - Custom Google Generative AI implementation
- `chat.py` - Chat functionality helpers
- `vision.py` - Vision-related LLM helpers
- `config.py` - Configuration utilities for LLM models

## CustomGoogleGenerativeAI Class

The `CustomGoogleGenerativeAI` class in `custom_google.py` is a custom implementation of Google's Generative AI chat model that extends LangChain's `BaseChatModel`.

### Purpose

This custom implementation was created to overcome SSL certificate issues in certain environments by using REST transport with SSL verification disabled (`verify=False`). The standard Google GenAI client may fail in environments with strict SSL configurations or custom certificates.

### Key Features

- **SSL Bypass**: Uses `HttpOptions` with `verify=False` for both sync and async operations
- **LangChain Compatibility**: Fully compatible with LangChain's chat model interface
- **Tool Binding Support**: Implements `bind_tools()` method for tool calling compatibility
- **Structured Output**: Supports structured data output via `with_structured_output()`
- **Streaming Support**: Provides both sync and async streaming capabilities

### Usage

```python
from src.helpers.llm.custom_google import CustomGoogleGenerativeAI

# Initialize the model
model = CustomGoogleGenerativeAI(
    model="gemini-1.5-pro",
    google_api_key="your-api-key",
    temperature=0.7
)

# Use with LangChain
response = model.invoke("Hello, how are you?")
```

### Important Notes

- **Tool Calling**: While the class implements `bind_tools()` for API compatibility, actual tool calling functionality is not implemented with the underlying Google GenAI client. The method filters out tool-related parameters to prevent errors.
- **SSL Configuration**: This implementation bypasses SSL verification, which may have security implications in production environments.
- **Parameter Filtering**: The class filters out unsupported parameters like `tools`, `functions`, `safety_settings`, etc., to maintain compatibility with LangChain's interface.

### Supported Models

The tool choice functionality is supported for:
- `gemini-1.5-pro`
- `gemini-1.5-flash` 
- `gemini-2.0` series models

### Configuration

The class supports standard Google GenAI configuration options:
- `temperature` - Controls randomness in responses
- `top_p` - Nucleus sampling parameter
- `top_k` - Top-k sampling parameter
- `max_output_tokens` - Maximum tokens in response
- `stop_sequences` - Stop sequences for generation

### Error Handling

The implementation includes robust error handling for:
- SSL certificate issues
- Unsupported parameter filtering
- Tool conversion and binding
- Message format conversion between LangChain and Google GenAI formats 