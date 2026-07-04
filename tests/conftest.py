import os
import json
import subprocess
import urllib.request
from unittest.mock import MagicMock
import pytest

@pytest.fixture(autouse=True)
def mock_external_calls(monkeypatch):
    """
    Globally mocks subprocess.run and urllib.request.urlopen for tests to prevent
    real ROCm/Fireworks calls in offline test environments.
    """
    original_run = subprocess.run

    def custom_run(args, **kwargs):
        if isinstance(args, list) and len(args) > 0:
            cmd = args[0]
            if cmd == "hipify-clang":
                src = args[1]
                dest = args[3]
                try:
                    with open(src, "r", encoding="utf-8") as f:
                        content = f.read()
                    
                    if "HIPFORGE_MOCK_COMPILE_ERROR" in content:
                        mock_res = MagicMock()
                        mock_res.returncode = 1
                        mock_res.stdout = ""
                        mock_res.stderr = "error: hipify-clang mock failure triggered"
                        return mock_res
                    
                    translated = (
                        content
                        .replace("cuda", "hip")
                        .replace("Cuda", "Hip")
                        .replace("CUDA", "HIP")
                        .replace("cuda_runtime.h", "hip/hip_runtime.h")
                    )
                    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
                    with open(dest, "w", encoding="utf-8") as f:
                        f.write(translated)
                    
                    mock_res = MagicMock()
                    mock_res.returncode = 0
                    mock_res.stdout = "Translated successfully"
                    mock_res.stderr = ""
                    return mock_res
                except Exception as e:
                    mock_res = MagicMock()
                    mock_res.returncode = 1
                    mock_res.stdout = ""
                    mock_res.stderr = str(e)
                    return mock_res
                    
            elif cmd == "hipcc":
                src = args[1]
                dest = args[3]
                try:
                    with open(src, "r", encoding="utf-8") as f:
                        content = f.read()
                    
                    if "HIPFORGE_MOCK_COMPILE_ERROR" in content:
                        mock_res = MagicMock()
                        mock_res.returncode = 1
                        mock_res.stdout = ""
                        mock_res.stderr = (
                            f"{os.path.basename(src)}:42:8: error: no matching function for call to 'hipMemcpyAsync' [E0308]\n"
                            f"{os.path.basename(src)}:67:12: error: use of undeclared identifier 'hipStreamNonBlocking' [E0020]\n"
                        )
                        return mock_res
                    
                    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
                    with open(dest, "w", encoding="utf-8") as f:
                        f.write("/* HIPForge compiled mock binary */\n")
                    
                    mock_res = MagicMock()
                    mock_res.returncode = 0
                    mock_res.stdout = "Compiled successfully"
                    mock_res.stderr = ""
                    return mock_res
                except Exception as e:
                    mock_res = MagicMock()
                    mock_res.returncode = 1
                    mock_res.stdout = ""
                    mock_res.stderr = str(e)
                    return mock_res

        return original_run(args, **kwargs)

    monkeypatch.setattr(subprocess, "run", custom_run)

    def custom_urlopen(request, timeout=None):
        req_url = request.full_url if hasattr(request, "full_url") else str(request)
        if "api.fireworks.ai" in req_url:
            req_data = ""
            if request.data:
                if isinstance(request.data, bytes):
                    req_data = request.data.decode("utf-8")
                else:
                    req_data = str(request.data)
            
            req_data_lower = req_data.lower()
            
            # Formulate mock JSON responses representing different agents
            if "identify the root cause" in req_data_lower or "analysis" in req_data_lower:
                body = {
                    "summary": "Compilation failed due to unsupported CUDA memory copy API.",
                    "root_cause": "cudaMemcpyAsync is not fully equivalent to hipMemcpyAsync in this context.",
                    "affected_files": ["kernel.hip"],
                    "affected_lines": [42, 67],
                    "confidence": 0.92,
                    "repair_plan": [
                        "Replace hipMemcpyAsync with hipMemcpyWithStream.",
                    ]
                }
                payload_content = json.dumps(body)
            elif "modify source code to patch" in req_data_lower:
                body = {
                    "summary": "Applied targeted fix.",
                    "modified_files": ["kernel.hip"],
                    "changes": [
                        {
                            "file": "kernel.hip",
                            "reason": "Replace unsupported hipMemcpyAsync",
                            "lines": [42],
                        }
                    ]
                }
                payload_content = json.dumps(body)
                # Wrap in markdown fence to make it realistic for patch agent
                payload_content = "Here is the patched code:\n```hip\n" + payload_content + "\n```"
            elif "documentation and research" in req_data_lower or "research" in req_data_lower:
                body = {
                    "findings": ["Found stream sync issue in ROCm docs."],
                    "recommended_actions": ["Use hipMemcpyWithStream."]
                }
                payload_content = json.dumps(body)
            else:
                body = {"result": "Default mock response"}
                payload_content = json.dumps(body)

            response_data = {
                "id": "mock-completion-1234",
                "object": "chat.completion",
                "model": "test-model",
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": payload_content},
                    "finish_reason": "stop",
                }],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
            }

            class FakeResponse:
                def read(self):
                    return json.dumps(response_data).encode("utf-8")
                def __enter__(self): return self
                def __exit__(self, *args): pass

            return FakeResponse()

        raise RuntimeError(f"Unexpected external request: {req_url}")

    monkeypatch.setattr(urllib.request, "urlopen", custom_urlopen)


import asyncio

class MockRedis:
    def __init__(self):
        self.lists = {}
        self.db = self.lists
        self.pubsub_channels = {}

    async def ping(self):
        return True

    async def delete(self, *keys):
        for key in keys:
            self.lists.pop(key, None)

    async def keys(self, pattern):
        import fnmatch
        return [k for k in self.lists.keys() if fnmatch.fnmatch(k, pattern)]

    async def lpush(self, key, value):
        if key not in self.lists:
            self.lists[key] = []
        self.lists[key].insert(0, value)
        return len(self.lists[key])

    async def rpush(self, key, value) -> int:
        if key not in self.lists:
            self.lists[key] = []
        if not isinstance(self.lists[key], list):
            self.lists[key] = [self.lists[key]]
        self.lists[key].append(value)
        return len(self.lists[key])

    async def brpop(self, key, timeout=0):
        if key not in self.lists or not self.lists[key]:
            if timeout > 0:
                await asyncio.sleep(min(timeout, 0.1))
            if key not in self.lists or not self.lists[key]:
                return None
        val = self.lists[key].pop()
        return (key, val)

    async def lrange(self, key, start, end):
        if key not in self.lists:
            return []
        if end == -1:
            return self.lists[key][start:]
        return self.lists[key][start:end+1]

    async def lrem(self, key, count, value):
        if key not in self.lists:
            return 0
        original_len = len(self.lists[key])
        self.lists[key] = [v for v in self.lists[key] if v != value]
        return original_len - len(self.lists[key])

    async def get(self, key: str):
        val = self.lists.get(key)
        if isinstance(val, list):
            return None
        return val

    async def set(self, key: str, value: str):
        self.lists[key] = value
        return True

    async def hset(self, key: str, *args, **kwargs):
        if key not in self.lists:
            self.lists[key] = {}
        if not isinstance(self.lists[key], dict):
            self.lists[key] = {}
        mapping = kwargs.pop("mapping", None)
        if mapping is not None:
            self.lists[key].update(mapping)
            return len(mapping)
        if args:
            if len(args) == 2:
                self.lists[key][args[0]] = args[1]
                return 1
            if len(args) == 1 and isinstance(args[0], dict):
                self.lists[key].update(args[0])
                return len(args[0])
        if kwargs:
            self.lists[key].update(kwargs)
            return len(kwargs)
        return 0

    async def hgetall(self, key: str):
        val = self.lists.get(key)
        if isinstance(val, dict):
            return val
        return {}

    async def hget(self, key: str, field: str):
        val = self.lists.get(key)
        if isinstance(val, dict):
            return val.get(field)
        return None


    async def llen(self, key: str) -> int:
        val = self.lists.get(key)
        if isinstance(val, list):
            return len(val)
        return 0

    async def publish(self, channel, message):
        if channel in self.pubsub_channels:
            count = 0
            for queue in self.pubsub_channels[channel]:
                await queue.put({"type": "message", "channel": channel, "data": message})
                count += 1
            return count
        return 0

    def pubsub(self):
        return MockPubSub(self)

class MockPubSub:
    def __init__(self, client):
        self.client = client
        self.channels = []
        self.queue = asyncio.Queue()

    async def subscribe(self, channel):
        self.channels.append(channel)
        if channel not in self.client.pubsub_channels:
            self.client.pubsub_channels[channel] = []
        self.client.pubsub_channels[channel].append(self.queue)

    async def get_message(self, ignore_subscribe_messages=False, timeout=0):
        try:
            if timeout > 0:
                return await asyncio.wait_for(self.queue.get(), timeout=timeout)
            return self.queue.get_nowait()
        except (asyncio.QueueEmpty, asyncio.TimeoutError):
            return None

    async def unsubscribe(self, channel=None):
        pass

    async def aclose(self):
        pass

