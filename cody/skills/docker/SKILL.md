# Docker Operations

Manage containers, images, and Docker Compose services using the Docker CLI.

## Prerequisites

- Docker must be installed: `docker --version`
- Docker daemon must be running: `docker info`

## Container Operations

### List containers
```bash
docker ps              # Running containers
docker ps -a           # All containers (including stopped)
```

### Run a container
```bash
docker run -d --name myapp -p 8080:80 nginx
docker run -it --rm ubuntu bash
docker run -d -v $(pwd):/app -w /app node:18 npm start
```

### Stop/start/restart
```bash
docker stop myapp
docker start myapp
docker restart myapp
```

### Remove containers
```bash
docker rm myapp
docker rm -f myapp       # Force remove (even running)
```

### View logs
```bash
docker logs myapp
docker logs -f myapp     # Follow logs
docker logs --tail 100 myapp
```

### Execute command in container
```bash
docker exec -it myapp bash
docker exec myapp ls /app
```

## Image Operations

### List images
```bash
docker images
```

### Build an image
```bash
docker build -t myapp:latest .
docker build -t myapp:v1.0 -f Dockerfile.prod .
```

### Pull/push images
```bash
docker pull nginx:latest
docker push myregistry/myapp:latest
```

### Remove images
```bash
docker rmi myapp:latest
docker image prune       # Remove unused images
```

## Docker Compose

### Start services
```bash
docker compose up -d
docker compose up -d --build    # Rebuild images
```

### Stop services
```bash
docker compose down
docker compose down -v          # Also remove volumes
```

### View logs
```bash
docker compose logs
docker compose logs -f web
```

### Scale services
```bash
docker compose up -d --scale web=3
```

### Execute commands
```bash
docker compose exec web bash
docker compose run --rm web npm test
```

## Dockerfile Best Practices

When creating Dockerfiles:
```dockerfile
# Use specific version tags
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy dependency files first (leverage cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Use non-root user
RUN useradd -m appuser
USER appuser

# Expose port
EXPOSE 8000

# Use exec form for CMD
CMD ["python", "app.py"]
```

## Network & Volume

### Networks
```bash
docker network ls
docker network create mynet
docker run -d --network mynet --name web nginx
```

### Volumes
```bash
docker volume ls
docker volume create mydata
docker run -d -v mydata:/data myapp
```

## Cleanup

```bash
docker system prune             # Remove unused data
docker system prune -a --volumes  # Full cleanup
```

## Notes

- Always use specific image tags in production (not `latest`)
- Use `.dockerignore` to exclude files from build context
- Use multi-stage builds to reduce image size
- Check container health: `docker inspect --format='{{.State.Health}}' myapp`
