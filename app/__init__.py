import os

# adding tiktoken cache path within repo to be able to run in offline environment.
os.environ["TIKTOKEN_CACHE_DIR"] = "tiktoken_cache"

