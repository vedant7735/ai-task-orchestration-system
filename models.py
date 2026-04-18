import os
import sys
import psutil
import contextlib
import threading
from llama_cpp import Llama

# ──────────────────────────────────────────────────────────
# BACKEND CONFIGURATION
# Change these two lines to switch between Groq and local
# ──────────────────────────────────────────────────────────
WORKER_BACKEND    = "groq"   # "groq" | "local"
ASSEMBLER_BACKEND = "groq"   # "groq" | "local"

GROQ_WORKER_MODEL    = "llama-3.3-70b-versatile"
GROQ_ASSEMBLER_MODEL = "llama-3.3-70b-versatile"

LOCAL_WORKER_MODEL    = "phi3"
LOCAL_ASSEMBLER_MODEL = "phi3"

# ──────────────────────────────────────────────────────────
# THREAD-SAFE LOG SUPPRESSION
# ──────────────────────────────────────────────────────────
_suppress_lock = threading.Lock()

@contextlib.contextmanager
def suppress_llama_output():
    with _suppress_lock:
        devnull = None
        try:
            devnull    = open(os.devnull, 'w')
            sys.stdout = devnull
            sys.stderr = devnull
            yield
        finally:
            sys.stdout = sys.__stdout__
            sys.stderr = sys.__stderr__
            if devnull is not None:
                try:
                    devnull.close()
                except Exception:
                    pass


def _print(*args, **kwargs):
    try:
        print(*args, file=sys.__stdout__, **kwargs)
    except Exception:
        pass


def print_ram():
    try:
        ram = psutil.virtual_memory()
        _print(f"[RAM] Used: {ram.used // (1024**3)} GB | Available: {ram.available // (1024**3)} GB")
    except Exception:
        pass


# ──────────────────────────────────────────────────────────
# MODEL MANAGER (local models only)
# ──────────────────────────────────────────────────────────
class ModelManager:
    def __init__(self):
        self.models = {}
        self._lock  = threading.Lock()

    def load(self, name: str, path: str, n_ctx: int = 2048) -> Llama:
        with self._lock:
            if name in self.models and self.models[name] is not None:
                return self.models[name]

            _print(f"[MODEL] Loading {name}...")
            print_ram()

            with suppress_llama_output():
                self.models[name] = Llama(
                    model_path=path,
                    n_ctx=n_ctx,
                    n_threads=6,
                    n_gpu_layers=0,
                    verbose=False,
                )

            _print(f"[MODEL] {name} loaded")
            print_ram()
            return self.models[name]

    def unload(self, name: str) -> None:
        with self._lock:
            if name in self.models:
                self.models[name] = None
                del self.models[name]
                _print(f"[MODEL] Unloaded {name}")
                print_ram()

    def unload_all(self) -> None:
        with self._lock:
            for name in list(self.models.keys()):
                self.models[name] = None
            self.models.clear()
        _print("[MODEL] Clearing all models")
        print_ram()


manager = ModelManager()

# ──────────────────────────────────────────────────────────
# MODEL PATHS
# ──────────────────────────────────────────────────────────
MODEL_PATHS = {
    "phi3":     "C:/Local_AI_Models/Phi-3-mini-4k-instruct-q4.gguf",
    "deepseek": "C:/Local_AI_Models/deepseek-coder-6.7b-instruct.Q4_K_M.gguf",
}

# ──────────────────────────────────────────────────────────
# GROQ CLIENT
# ──────────────────────────────────────────────────────────
def _get_groq_client():
    try:
        from groq import Groq
    except ImportError:
        raise ImportError("Run: pip install groq")

    api_key = os.environ.get("GROQ_API_KEY", "").strip()

    if not api_key:
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("GROQ_API_KEY="):
                        api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break

    if not api_key:
        raise ValueError("GROQ_API_KEY not set in environment or .env file")

    return Groq(api_key=api_key)


# ──────────────────────────────────────────────────────────
# UNIFIED MODEL BACKEND
# ──────────────────────────────────────────────────────────
class ModelBackend:
    """
    Unified interface for Groq and local backends.
    Call backend.complete(system, user) — same API for both.
    """

    def __init__(self, backend_type: str, model_name: str, fallback_model_name: str | None = None):
        self.backend_type = backend_type
        self.model_name   = model_name
        self.fallback_model_name = fallback_model_name
        self._groq_client = None
        self._local_model = None

    def complete(
        self,
        system:      str,
        user:        str,
        temperature: float = 0.3,
        max_tokens:  int   = 1000,
    ) -> str:
        if self.backend_type == "groq":
            return self._groq_complete(system, user, temperature, max_tokens)
        else:
            return self._local_complete(system, user, temperature, max_tokens)

    def unload(self):
        """Cleanup. No-op for Groq."""
        if self.backend_type == "local":
            manager.unload_all()
        self._local_model = None

    def _groq_complete(self, system, user, temperature, max_tokens) -> str:
        if self._groq_client is None:
            self._groq_client = _get_groq_client()

        _print(f"[BACKEND] Groq ({self.model_name})...")
        try:
            response = self._groq_client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as e:
            if not self.fallback_model_name:
                raise

            fallback_path = MODEL_PATHS.get(self.fallback_model_name)
            if not fallback_path or not os.path.exists(fallback_path):
                raise

            _print(f"[BACKEND] Groq failed: {e}")
            _print(f"[BACKEND] Falling back to local model: {self.fallback_model_name}")

            self.backend_type = "local"
            self.model_name = self.fallback_model_name
            self._groq_client = None
            return self._local_complete(system, user, temperature, max_tokens)

        output = response.choices[0].message.content.strip()

        if hasattr(response, "usage") and response.usage:
            u = response.usage
            _print(f"[BACKEND] Groq — in: {u.prompt_tokens} / out: {u.completion_tokens} tok")

        return output

    def _local_complete(self, system, user, temperature, max_tokens) -> str:
        if self._local_model is None:
            path = MODEL_PATHS.get(self.model_name)
            if not path:
                raise ValueError(f"Unknown local model: {self.model_name}")
            self._local_model = manager.load(self.model_name, path, n_ctx=2048)

        _print(f"[BACKEND] Local ({self.model_name})...")

        with suppress_llama_output():
            response = self._local_model.create_chat_completion(
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )

        return response["choices"][0]["message"]["content"].strip()


# ──────────────────────────────────────────────────────────
# PUBLIC GETTERS
# ──────────────────────────────────────────────────────────
def get_worker_backend() -> ModelBackend:
    if WORKER_BACKEND == "groq":
        return ModelBackend("groq", GROQ_WORKER_MODEL, fallback_model_name=LOCAL_WORKER_MODEL)
    return ModelBackend("local", LOCAL_WORKER_MODEL)


def get_assembler_backend() -> ModelBackend:
    if ASSEMBLER_BACKEND == "groq":
        return ModelBackend("groq", GROQ_ASSEMBLER_MODEL, fallback_model_name=LOCAL_ASSEMBLER_MODEL)
    return ModelBackend("local", LOCAL_ASSEMBLER_MODEL)


# Legacy getters — kept so old imports don't break
def get_worker_model():
    return manager.load(LOCAL_WORKER_MODEL, MODEL_PATHS[LOCAL_WORKER_MODEL], n_ctx=2048)

def get_assembler_model():
    return manager.load(LOCAL_ASSEMBLER_MODEL, MODEL_PATHS[LOCAL_ASSEMBLER_MODEL], n_ctx=2048)
