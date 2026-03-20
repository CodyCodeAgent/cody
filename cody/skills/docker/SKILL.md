---
name: docker
description: Docker containerization, Dockerfile best practices, and docker-compose workflows.
---

# Docker Skill

## When to use
- Building Docker images
- Writing or reviewing Dockerfiles
- Setting up docker-compose configurations
- Debugging container issues

## Best practices
- Use multi-stage builds to reduce image size
- Pin base image versions (avoid `latest`)
- Use `.dockerignore` to exclude unnecessary files
- Run as non-root user in production
- Use COPY instead of ADD when possible
- Order instructions from least to most frequently changing

## Common commands
```bash
# Build image
docker build -t myapp .

# Run container
docker run -p 8080:8080 myapp

# Docker compose
docker compose up -d
docker compose logs -f
```
