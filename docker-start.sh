#!/bin/bash

# Quick start script for desto Docker setup

set -e

echo "🚀 Starting desto Docker setup..."

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed or not in PATH"
    echo "Please install Docker first: https://docs.docker.com/get-docker/"
    exit 1
fi

# Check if Docker Compose is available
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is not installed or not in PATH"
    echo "Please install Docker Compose: https://docs.docker.com/compose/install/"
    exit 1
fi

# Create directories for scripts and logs
echo "📁 Creating directories..."
mkdir -p docker-scripts docker-logs

# Copy example scripts
echo "📋 Copying example scripts..."
if [ -d "docker-examples" ]; then
    cp docker-examples/* docker-scripts/ 2>/dev/null || true
    chmod +x docker-scripts/*.sh 2>/dev/null || true
    echo "✅ Example scripts copied to docker-scripts/"
else
    echo "⚠️  docker-examples directory not found, creating empty scripts directory"
fi

# Build Docker image
echo "🏗️  Building Docker image..."
docker build -t desto:latest .

# Start services
echo "🚀 Starting desto services..."
docker-compose up -d

# Wait for services to be ready
echo "⏳ Waiting for services to start..."
sleep 5

# Check if services are running
if docker-compose ps | grep -q "Up"; then
    echo "✅ Desto is running!"
    echo ""
    echo "🌐 Access the dashboard at: http://localhost:8088"
    echo ""
    echo "📖 Available commands:"
    echo "  docker-compose logs -f desto    # View logs"
    echo "  docker-compose down             # Stop services"
    echo "  docker-compose restart desto    # Restart services"
    echo ""
    echo "📁 Your scripts directory: $(pwd)/docker-scripts"
    echo "📁 Your logs directory: $(pwd)/docker-logs"
else
    echo "❌ Failed to start services"
    echo "Check the logs with: docker-compose logs desto"
    exit 1
fi
