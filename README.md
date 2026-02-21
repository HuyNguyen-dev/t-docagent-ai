# DIMS-AI

**Document Intelligence Multi-Agent System**

DIMS-AI is an autonomous document processing system that leverages a coordinated team of specialized AI agents to handle the complete document lifecycle—from initial configuration through extraction to end-to-end business processing.

## 🎯 Overview

Document Intelligence delivers intelligent document processing capabilities through multiple specialized agents, each mastering a critical phase of the document workflow:

- **Document Type Management**: Configure and manage different document types
- **Document Format Processing**: Handle various document formats and structures  
- **Intelligence Agents**: AI-powered document analysis and extraction
- **Schema Discovery**: Automatically discover document schemas from annotated samples
- **Mapping Generation**: Generate and recommend field mappings for document processing

## 🏗️ Architecture

The system is built as a FastAPI-based microservice with the following key components:

- **Multi-Agent System**: Specialized agents for different document processing tasks
- **LangChain Integration**: Advanced language model capabilities for document understanding
- **MongoDB**: Document and metadata storage
- **Redis**: Pub/Sub, streaming and background coordination
- **MinIO**: Object storage for document files
- **Docker**: Containerized deployment

## 🚀 Quick Start

### Prerequisites

- **Python**: 3.12+
- **MongoDB**: 4.4+
- **Redis**: 6+
- **MinIO**: (for file storage)
- **UV**: Python package manager (`pip install uv`)

### Installation

1. **Clone the repository:**

   ```bash
   git clone https://gitlab.tma.com.vn/agentic-document-intelligent/dims-ai.git
   cd dims-ai
   ```

2. **Install dependencies:**

   ```bash
   uv sync
   ```

3. **Set up environment variables:**
   There are two ways to configure environment variables—choose one:

   - Option A: Export environment variables directly in your shell (recommended for rapid development)

     ```bash
     export MONGODB_DSN="mongodb://localhost:27017"
     export MONGODB_DATABASE_NAME="agentic-document-intelligence"
     export MINIO_ENDPOINT="localhost:9000"
     export MINIO_ACCESS_KEY="your_access_key"
     export MINIO_SECRET_KEY="your_secret_key"
     export REDIS_HOST="localhost"
     export REDIS_PORT=6379
     export REDIS_DB=0
      # Optional: configure LLM providers
     export OPENAI_API_KEY="your_openai_key"
     export GOOGLE_API_KEY="your_google_key"
      # Optional: Azure OpenAI
     export AZURE_OPENAI_API_KEY="your_azure_key"
     export AZURE_OPENAI_ENDPOINT="https://your-endpoint.openai.azure.com/"
     export AZURE_OPENAI_GPT4O_DEPLOYMENT_NAME="gpt-4o"
     ```

   - Option B: Use a `.env` file
     1. Set `APP_HOME` to the project root so the system can auto-load the `.env` file per `src/config.py`

     ```bash
      export APP_HOME="$(pwd)"   # when you are at the repository root
     ```

     1. Create a `.env` file at the repository root and fill in the following variables:

     ```bash
     # Database
     MONGODB_DSN=mongodb://localhost:27017
     MONGODB_DATABASE_NAME=agentic-document-intelligence

     # Redis
     REDIS_HOST=localhost
     REDIS_PORT=6379
     REDIS_DB=0

     # LLM Providers (at least one)
     OPENAI_API_KEY=your_openai_key
     GOOGLE_API_KEY=your_google_key

     # Azure OpenAI (optional)
     AZURE_OPENAI_API_KEY=your_azure_key
     AZURE_OPENAI_ENDPOINT=https://your-endpoint.openai.azure.com/
     AZURE_OPENAI_GPT4O_DEPLOYMENT_NAME=gpt-4o

     # Storage
     MINIO_ENDPOINT=localhost:9000
     MINIO_ACCESS_KEY=your_access_key
     MINIO_SECRET_KEY=your_secret_key

     # Server (optional)
     HOST=0.0.0.0
     PORT=8888
     LOG_LEVEL=INFO
     UVICORN_WORKERS=1
     ```

4. **Required Environment Variables:**

   ```bash
   # Database
   MONGODB_DSN=mongodb://localhost:27017
   MONGODB_DATABASE_NAME=agentic-document-intelligence
   
   # LLM Providers (configure at least one)
   OPENAI_API_KEY=your_openai_key
   GOOGLE_API_KEY=your_google_key
   
   # Azure OpenAI (optional)
   AZURE_OPENAI_API_KEY=your_azure_key
   AZURE_OPENAI_ENDPOINT=https://your-endpoint.openai.azure.com/
   AZURE_OPENAI_GPT4O_DEPLOYMENT_NAME=gpt-4o
   
   # Storage
   MINIO_ENDPOINT=localhost:9000
   MINIO_ACCESS_KEY=your_access_key
   MINIO_SECRET_KEY=your_secret_key
   ```

5. **Start the application:**

   ```bash
   python src/app.py
   ```

The API will run at `http://localhost:8888` (default per `src/config.py`) with interactive docs at `http://localhost:8888/docs`.

## 🐳 Docker Deployment

`Dockerfile`/`docker-compose.yaml` are not provided in this repository yet. This section will be updated once official Docker configurations are added.

## 📚 API Endpoints

### Core Endpoints (default prefix: `/api/v1`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/ping` | GET | Health check |
| `/api/v1/document-type` | GET/POST/PUT/DELETE | Manage document types |
| `/api/v1/document-format` | GET/POST/PUT/DELETE | Manage document formats |
| `/api/v1/document-intelligence/discover-annotations` | POST | Discover schema from annotated images (multipart/form-data) |
| `/api/v1/document-intelligence/discover-mapping` | POST | Suggest field/table mappings (multipart/form-data) |
| `/api/v1/llm/list-models?llm_provider=...` | GET | List models by provider |
| `/api/v1/llm/complete?model_name=...` | POST | Synchronous completion |
| `/api/v1/llm/complete/astream?model_name=...` | POST | Streaming completion (NDJSON) |
| `/api/v1/sample-agent/ainvoke?model_name=...` | POST | Sample workflow agent (synchronous) |
| `/api/v1/sample-agent/astream?model_name=...` | POST | Sample workflow agent (streaming) |
| `/api/v1/conversation` | POST/PUT/DELETE | Manage conversations |
| `/api/v1/conversational-agent/{conv_id}/chat` | POST | Chat with conversational agent (streaming) |
| `/api/v1/conversational-agent/{conv_id}/stream` | GET | Stream events via SSE |
| `/api/v1/worker-agent/{conv_id}/chat` | POST | Chat with worker agent (streaming) |
| `/api/v1/work-item/{dwi_id}` | GET | Query work item and download source file |
| `/api/v1/action-package/...` | GET/POST/PUT/DELETE | Manage action packages |

### Document Intelligence Features

- **Schema Discovery**: Upload annotated document samples to automatically discover document schemas
- **Field Mapping**: Generate intelligent mappings between document fields and target formats
- **Multi-format Support**: Process various document types and formats
- **Agent Workflows**: Leverage specialized agents for complex document processing tasks

#### API Examples

- Discover Annotations

  ```bash
  curl -X POST "http://localhost:8888/api/v1/document-intelligence/discover-annotations" \
    -H "accept: application/json" \
    -H "Content-Type: multipart/form-data" \
    -F "dt_id=YOUR_DOCUMENT_TYPE_ID" \
    -F "zip_file=@/path/to/images.zip;type=application/zip" \
    -F 'annotation_config={
      "field": {"color_name": "Red", "hex_code": "#FF0000"},
      "tables": [
        {"color_name": "Blue", "hex_code": "#0000FF", "table_name": "Items"}
      ]
    }'
  ```

- Discover Mapping

  ```bash
  curl -X POST "http://localhost:8888/api/v1/document-intelligence/discover-mapping" \
    -H "accept: application/json" \
    -H "Content-Type: multipart/form-data" \
    -F "dt_id=YOUR_DOCUMENT_TYPE_ID" \
    -F "df_id=YOUR_DOCUMENT_FORMAT_ID" \
    -F "zip_file=@/path/to/images.zip;type=application/zip" \
    -F "annotation_config=Please map total, date, and vendor name"
  ```

- LLM List Models

  ```bash
  curl "http://localhost:8888/api/v1/llm/list-models?llm_provider=OPENAI"
  ```

- LLM Complete

  ```bash
  curl -X POST "http://localhost:8888/api/v1/llm/complete?model_name=gpt-4o-mini" \
    -H "Content-Type: application/json" \
  -d '{"prompt": "Write a short welcome message in English"}'
  ```

## 🧠 AI Agents

The system includes several specialized agents:

- **Training Agent**: Handles document type learning and model training
- **Extraction Agent**: Specialized in data extraction from documents  
- **Basic Agent**: Handles fundamental document processing tasks

## 🛠️ Development

### Project Structure

```
src/
├── agents/           # AI agent implementations
├── handlers/         # Business logic handlers
├── models/          # Data models and schemas
├── routers/         # FastAPI route definitions
├── schemas/         # Pydantic schemas
├── settings/        # Configuration files
├── static/          # Static web assets
├── utils/           # Utility functions
├── app.py           # Main application entry point
├── config.py        # Configuration management
└── initializer.py   # Application initialization
```

### Code Quality

The project uses several tools for code quality:

- **Ruff**: Fast Python linter and formatter
- **Pylint**: Additional code analysis (installed via the `lint` optional group)
- **Type hints**: Full type annotation support
- **Pydantic**: Data validation and settings management

### Running Tests

```bash
# Install linting packages
uv sync --group lint

# Ruff
uv run ruff check .
uv run ruff format .

# Pylint
uv run pylint src/
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Merge Request

### Development Guidelines

- Follow the existing code style and formatting
- Add type hints to all functions
- Write descriptive commit messages
- Update documentation for new features
- Ensure all tests pass before submitting

## 📋 Requirements

### System Requirements

- Python 3.12+
- MongoDB 4.4+
- MinIO (or S3-compatible storage)
- Memory: 4GB+ recommended
- CPU: 2+ cores recommended

### Python Dependencies

Key dependencies include:

- **FastAPI**: Modern web framework
- **LangChain**: LLM integration and workflows
- **LangGraph**: Multi-agent orchestration
- **Beanie**: Async MongoDB ODM
- **Pydantic**: Data validation
- **Redis**: Pub/Sub and checkpoint (langgraph-checkpoint-mongodb is also supported)
- **MinIO**: Object storage client
- **Uvicorn**: ASGI server

See `pyproject.toml` for the complete list of dependencies.

## 📖 Documentation

- **API Documentation**: `/docs`
- **OpenAPI Schema**: `/openapi.json`
- **Configuration**: see `src/settings/default_config.yaml` and `src/config.py`

## 👥 Authors

- **Danh Nguyen** - <ntdanh@tma.com.vn>
- **Than Vo** - <vmthan@tma.com.vn>
- **Trieu Nguyen** - <nvtrieu@tma.com.vn>

## 📄 License

This project is proprietary software developed by TMA Solutions.

## 🔧 Troubleshooting

### Common Issues

1. **MongoDB Connection Issues**
   - Verify MongoDB is running and accessible
   - Check MONGODB_DSN environment variable

2. **MinIO Storage Issues**
   - Ensure MinIO server is running
   - Verify MINIO_ENDPOINT and credentials

3. **LLM API Issues**
   - Check API keys are correctly configured
   - Verify API quota and rate limits

4. **Docker Issues**
   - Ensure Docker daemon is running
   - Check port 8888 is not in use

### Getting Help

- Check the application logs for detailed error messages
- Review the API documentation at `/docs`
- Contact the development team for support

## 🗺️ Roadmap

- [ ] Enhanced multi-agent coordination
- [ ] Support for additional document formats
- [ ] Advanced schema learning capabilities
- [ ] Performance optimizations
- [ ] Extended API functionality
- [ ] Comprehensive testing suite
