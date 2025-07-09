# Docker Examples

This directory contains example scripts to demonstrate **desto** Docker functionality.

## Scripts

### `demo-script.sh`
Basic bash script that demonstrates:
- Environment variable access
- Container information
- Simple processing workflow

### `demo-script.py`
Python script that shows:
- Python environment in container
- System information access
- Multi-step processing

### `long-running-demo.sh`
Long-running script (30 seconds) that demonstrates:
- Session management
- Live log viewing
- Process monitoring

## Usage

1. **Setup Docker environment:**
   ```bash
   # From repository root
   make docker-setup-examples
   ```

2. **Start desto with Docker:**
   ```bash
   docker build -t desto:latest .
   docker run -d -p 8809:8809 \
     -v $PWD/desto_scripts:/app/scripts \
     -v $PWD/desto_logs:/app/logs \
     --name desto-dashboard \
     desto:latest
   ```

3. **Access the dashboard:**
   Open http://localhost:8809 in your browser

4. **Run example scripts:**
   - Select any of the demo scripts from the dashboard
   - Name your tmux session
   - Click "Launch" to run the script
   - View logs in real-time

## Testing

Run the Docker integration tests:
```bash
make docker-test
```

## Customization

Copy these scripts to your own scripts directory and modify them as needed:
```bash
cp desto_scripts/* /path/to/your/scripts/
```
