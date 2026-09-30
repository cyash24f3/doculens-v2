# Third-party notices

The original DocuLens application, fictional policy corpus, authored benchmark and PDF fixture are MIT licensed. The fictional policies and question labels were AI-authored; they are not actual commercial policy or independently human-reviewed ground truth.

`data/public/python-venv.txt` and `python-zipfile.txt` reproduce CPython v3.12.7 documentation from the Python Software Foundation's repository. Their original URLs and SHA-256 hashes are in `data/source_manifest.json`. The upstream [Python license](data/public/PYTHON-LICENSE.txt) applies to this content; the DocuLens MIT license does not replace it.

The pinned `sentence-transformers/all-MiniLM-L6-v2` and `cross-encoder/ms-marco-MiniLM-L6-v2` model cards identify Apache-2.0 licensing. They are downloaded at runtime and not redistributed in Git. [Encoder model card](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2), [cross-encoder model card](https://huggingface.co/cross-encoder/ms-marco-MiniLM-L6-v2).

Qwen2.5 7B is an optional, separately downloaded local Ollama model, not part of the application source distribution. Preserve upstream notices if distributing model files. No model files, Ollama binaries, Python interpreter, Docker layers or third-party dependency source are committed here; their own licenses continue to apply. `uv.lock` records the tested packages, with CPU Torch wheels on Linux. Only two small public documentation files and the accompanying license are vendored.
