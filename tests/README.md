Use the `docker-compose.test.yml` override to speed tests by shortening healthcheck intervals:

- To run tests using the override, start compose with:

```bash
# from repo root
docker compose -f docker-compose.yml -f tests/docker-compose.test.yml up -d
pytest ...
```

- Or pass the override when bringing services up in `docker_compose` fixture if you want it applied automatically.
