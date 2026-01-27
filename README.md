# Cody

🤖 Your AI coding companion - A Claude Code-like CLI tool with RPC support, dynamic skills, and MCP integration

## Features

- **AI-Powered** - Built on Pydantic AI with support for multiple models (Claude, GPT, Gemini)
- **Dual Mode** - CLI for direct use, RPC Server for integration
- **Dynamic Skills** - Extensible skill system, AI reads documentation to learn
- **MCP Support** - Connect to Model Context Protocol servers
- **Sub-Agents** - Spawn specialized agents for complex tasks
- **Secure** - Built-in command filtering and path validation

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/cody.git
cd cody

# Install dependencies
pip install -e .

# Set up API key
export ANTHROPIC_API_KEY='your-key-here'
```

### CLI Usage

```bash
# Initialize in a project
cody init

# Run a task
cody run "create a FastAPI hello world app"

# List available skills
cody skills list

# Show skill documentation
cody skills show git
```

### RPC Server

```bash
# Start the server
cody-server --port 8000

# Call via API
curl -X POST http://localhost:8000/run \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "create hello.py"}'
```

## Documentation

- [Features](docs/FEATURES.md) - Complete feature list and roadmap
- [Architecture](docs/ARCHITECTURE.md) - System architecture and design
- [API](docs/API.md) - RPC API documentation

## Configuration

Create `.cody/config.json` in your project:

```json
{
  "model": "anthropic:claude-sonnet-4-0",
  "skills": {
    "enabled": ["git", "github", "docker"]
  }
}
```

## Skills

Skills are documented tools that AI can learn to use:

```
.cody/skills/          # Project skills
├── github/
│   └── SKILL.md
└── custom-tool/
    └── SKILL.md
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Format code
black cody/
ruff check cody/
```

## License

MIT

## Contributing

Contributions welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) first.

## Credits

Built with:
- [Pydantic AI](https://ai.pydantic.dev/) - AI agent framework
- [FastAPI](https://fastapi.tiangolo.com/) - RPC server
- [Click](https://click.palletsprojects.com/) - CLI framework
- [Rich](https://rich.readthedocs.io/) - Terminal formatting
