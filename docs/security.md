# Security

RepoWise validates public GitHub URLs, bounds repository and file size, ignores dependency/build/secret patterns, resolves every tool path under the repository root, and exposes no arbitrary command tool. Test execution accepts only named runners and uses Docker with no network, read-only source, a non-root image user, CPU/memory/PID constraints, a timeout, and bounded output. Logs exclude configured credentials. For production, run sandbox jobs on separate hosts and avoid exposing a Docker socket to the API container.

