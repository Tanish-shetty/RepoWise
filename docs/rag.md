# Repository RAG

Python source is split with the standard AST at functions, async functions, and classes. JavaScript and TypeScript use symbol boundaries when recognizable, with module fallback. Chunks retain repository ID, file, language, symbol, start/end lines, type, imports, and content. Retrieval combines sparse token similarity, identifier normalization, query expansion, and symbol/path bonuses. Results support repository, language, and path filters and a hard result limit. `CodeIndex` is the adapter seam for Chroma or FAISS.

