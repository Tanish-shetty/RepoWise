# Architecture

RepoWise uses a React/Vite client, a FastAPI service, PostgreSQL, an in-process code index, and dedicated Docker runner images. Repository services remain framework-independent; API routes coordinate them and persist run envelopes. The debugging workflow is an explicit state machine whose complete state and history are reportable.

Data flows from ingestion to bounded discovery, profiling, syntax-aware chunking, indexing, retrieval, deterministic analysis, hypothesis formation, test proposal, optional isolated execution, verification, and reporting. Failures are returned as controlled API errors and do not terminate the service.

