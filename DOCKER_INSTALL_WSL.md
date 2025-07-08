# Installing Docker on WSL2

## Option 1: Docker Desktop (Recommended)

1. **Install Docker Desktop for Windows**:
   - Download from: https://www.docker.com/products/docker-desktop/
   - Install Docker Desktop on your Windows host
   - During installation, make sure "Use WSL 2 based engine" is enabled

2. **Enable WSL integration**:
   - Open Docker Desktop
   - Go to Settings → Resources → WSL Integration
   - Enable integration with your WSL2 distro
   - Click "Apply & Restart"

3. **Test Docker in WSL**:
   ```bash
   docker --version
   docker run hello-world
   ```

## Option 2: Docker Engine in WSL2 (Manual)

If you prefer to install Docker directly in WSL2:

1. **Update your WSL2 system**:
   ```bash
   sudo apt update && sudo apt upgrade -y
   ```

2. **Install Docker Engine**:
   ```bash
   # Add Docker's official GPG key
   sudo apt update
   sudo apt install ca-certificates curl gnupg lsb-release
   sudo mkdir -m 0755 -p /etc/apt/keyrings
   curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

   # Add the repository
   echo \
     "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
     $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

   # Install Docker Engine
   sudo apt update
   sudo apt install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
   ```

3. **Start Docker service**:
   ```bash
   sudo service docker start
   ```

4. **Add your user to docker group**:
   ```bash
   sudo usermod -aG docker $USER
   ```

5. **Log out and back in** for group changes to take effect.

## Option 3: Quick Test with Docker Desktop

The easiest way is to use Docker Desktop:

1. Install Docker Desktop for Windows
2. Enable WSL2 integration
3. Test with: `docker run hello-world`

## Verify Installation

Once Docker is installed, test it:

```bash
# Check Docker version
docker --version

# Check Docker Compose
docker-compose --version

# Test Docker
docker run hello-world

# Test with desto
cd /path/to/desto
make docker-build
```

## Troubleshooting

If you get permission errors:
```bash
sudo usermod -aG docker $USER
# Then log out and back in
```

If Docker daemon isn't running:
```bash
# For Docker Desktop: Start Docker Desktop app
# For Docker Engine: sudo service docker start
```

## About uv and Docker

**No, you cannot install Docker with uv.** Docker is a containerization platform that requires system-level installation. `uv` is a Python package manager and cannot install system applications like Docker.

However, you can use `uv` inside Docker containers (which we're doing in our Dockerfile) to manage Python dependencies efficiently.
