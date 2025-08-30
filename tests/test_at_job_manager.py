import subprocess


class FakeRedis:
    def __init__(self):
        # storage maps keys to dicts
        self.storage = {}

    def hmset(self, key, mapping):
        # mimic redis-py hmset behavior (store mapping)
        self.storage[key] = mapping.copy()

    def hgetall(self, key):
        return self.storage.get(key, {})

    def scan_iter(self, match=None):
        # simple implementation: return keys that start with the prefix in match
        prefix = match.replace("*", "") if match else ""
        for k in list(self.storage.keys()):
            if k.startswith(prefix):
                yield k

    def hset(self, key, field, value):
        cur = self.storage.get(key, {})
        cur[field] = value
        self.storage[key] = cur

    def exists(self, key):
        return 1 if key in self.storage else 0


class FakeClient:
    def __init__(self, redis):
        self.redis = redis

    def is_connected(self):
        return True


def fake_subprocess_run_at(args, input=None, capture_output=None, text=None, check=None):
    # Simulate `at` command output that contains "job <id> at <time>"
    class Result:
        def __init__(self):
            self.returncode = 0
            # typical at output includes 'job <id> at <date>' in stdout
            self.stdout = "job 123 at Tue Sep 02 12:00:00 2025"
            self.stderr = ""

    return Result()


def fake_subprocess_run_at_failure(args, input=None, capture_output=None, text=None, check=None):
    class Result:
        def __init__(self):
            self.returncode = 1
            self.stdout = ""
            self.stderr = "at: you must specify a time"

    return Result()


def test_schedule_links_at_job_id_to_session(monkeypatch):
    # Arrange: create fake redis with a session entry
    fake_redis = FakeRedis()
    session_key = "desto:session:session-1"
    fake_redis.storage[session_key] = {"session_name": "my-session"}
    client = FakeClient(fake_redis)

    # Patch subprocess.run so we don't call the system `at`
    monkeypatch.setattr(subprocess, "run", fake_subprocess_run_at)

    # Import here so monkeypatch applies before module usage
    from desto.redis.at_job_manager import AtJobManager

    atm = AtJobManager(redis_client=client)

    # Act: schedule a job for the session name that exists in fake redis
    job_id = atm.schedule(command="echo hello", time_spec="12:00 2025-09-02", session_name="my-session", script_path=["/tmp/script.sh"], arguments="")

    # Assert: job_id returned and atjob stored in redis
    assert job_id == "123"
    atjob_key = f"desto:atjob:{job_id}"
    assert atjob_key in fake_redis.storage
    # Assert session was updated with at_job_id
    assert fake_redis.storage[session_key].get("at_job_id") == "123"


def test_schedule_with_no_matching_session_still_stores_atjob(monkeypatch):
    fake_redis = FakeRedis()
    # create a session with a different name
    session_key = "desto:session:other-session"
    fake_redis.storage[session_key] = {"session_name": "other-session"}
    client = FakeClient(fake_redis)

    monkeypatch.setattr(subprocess, "run", fake_subprocess_run_at)
    from desto.redis.at_job_manager import AtJobManager

    atm = AtJobManager(redis_client=client)
    job_id = atm.schedule(command="echo hi", time_spec="12:00 2025-09-02", session_name="nonexistent-session", script_path=["/tmp/s"], arguments="")

    assert job_id == "123"
    # atjob stored
    assert f"desto:atjob:{job_id}" in fake_redis.storage
    # no session key was updated
    for k, v in fake_redis.storage.items():
        if k.startswith("desto:session:"):
            assert v.get("at_job_id") is None


def test_schedule_fails_when_at_fails(monkeypatch):
    fake_redis = FakeRedis()
    session_key = "desto:session:session-1"
    fake_redis.storage[session_key] = {"session_name": "my-session"}
    client = FakeClient(fake_redis)

    monkeypatch.setattr(subprocess, "run", fake_subprocess_run_at_failure)
    from desto.redis.at_job_manager import AtJobManager

    atm = AtJobManager(redis_client=client)
    job_id = atm.schedule(command="", time_spec="", session_name="my-session")

    assert job_id is None
    # no atjob stored and session not updated
    assert all(not k.startswith("desto:atjob:") for k in fake_redis.storage.keys())
    assert fake_redis.storage[session_key].get("at_job_id") is None


def test_direct_lookup_used_when_get_session_key_available(monkeypatch):
    fake_redis = FakeRedis()
    session_key = "desto:session:my-session"
    fake_redis.storage[session_key] = {"session_name": "my-session"}

    class ClientWithGetKey(FakeClient):
        def get_session_key(self, session_name: str):
            # Return the direct key we created above
            return session_key

    client = ClientWithGetKey(fake_redis)

    monkeypatch.setattr(subprocess, "run", fake_subprocess_run_at)
    from desto.redis.at_job_manager import AtJobManager

    atm = AtJobManager(redis_client=client)
    job_id = atm.schedule(command="echo hi", time_spec="12:00 2025-09-02", session_name="my-session", script_path=["/tmp/s"], arguments="")

    assert job_id == "123"
    # Verify the direct key was updated
    assert fake_redis.storage[session_key].get("at_job_id") == "123"
