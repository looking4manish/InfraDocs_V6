"""Generic service recognition — identify well-known software from a port, a docker
image, or a process name. Image/process beat port (more specific). Returns
(label, kind, is_web_ui) or None. No host-specific assumptions.
"""

from typing import Optional, Tuple

Recognition = Tuple[str, str, bool]

KNOWN_PORTS = {
    80: ("HTTP", "web", True), 443: ("HTTPS", "web", True), 8080: ("HTTP-alt", "web", True),
    8000: ("web app", "web", True), 8081: ("web app", "web", True), 3000: ("web app", "web", True),
    5000: ("web app", "web", True), 8443: ("HTTPS-alt", "web", True), 5173: ("Vite dev server", "web", True),
    9090: ("Prometheus / Cockpit", "monitoring", True), 9100: ("node-exporter", "monitoring", True),
    3001: ("Grafana", "monitoring", True), 9091: ("Pushgateway", "monitoring", True),
    5601: ("Kibana", "monitoring", True), 9093: ("Alertmanager", "monitoring", True),
    27017: ("MongoDB", "database", False), 27018: ("MongoDB", "database", False),
    27028: ("MongoDB (mongot)", "database", False),
    5432: ("PostgreSQL", "database", False), 3306: ("MySQL", "database", False),
    6379: ("Redis", "cache", False), 9200: ("Elasticsearch", "database", True),
    6333: ("Qdrant", "database", True), 6334: ("Qdrant gRPC", "database", False),
    8086: ("InfluxDB", "database", True), 2019: ("Caddy admin API", "infra", False),
    11434: ("Ollama (LLM)", "app", True),
}

# substring -> recognition. Order matters (first match wins).
IMAGE_HINTS = [
    ("grafana", ("Grafana", "monitoring", True)),
    ("prom/prometheus", ("Prometheus", "monitoring", True)),
    ("alertmanager", ("Alertmanager", "monitoring", True)),
    ("exporter", ("Prometheus exporter", "monitoring", False)),
    ("node-exporter", ("node-exporter", "monitoring", True)),
    ("qdrant", ("Qdrant (vector DB)", "database", True)),
    ("weaviate", ("Weaviate (vector DB)", "database", True)),
    ("chroma", ("Chroma (vector DB)", "database", True)),
    ("postgres", ("PostgreSQL", "database", False)),
    ("mariadb", ("MariaDB", "database", False)),
    ("mysql", ("MySQL", "database", False)),
    ("mongo", ("MongoDB", "database", False)),
    ("redis", ("Redis", "cache", False)),
    ("elasticsearch", ("Elasticsearch", "database", True)),
    ("opensearch", ("OpenSearch", "database", True)),
    ("rabbitmq", ("RabbitMQ", "queue", True)),
    ("kafka", ("Kafka", "queue", False)),
    ("nats", ("NATS", "queue", False)),
    ("minio", ("MinIO (object store)", "database", True)),
    ("traefik", ("Traefik", "proxy", True)),
    ("nginx", ("nginx", "proxy", False)),
    ("caddy", ("Caddy", "proxy", False)),
    ("cloudflare", ("Cloudflare Tunnel", "proxy", False)),
    ("openwebui", ("Open WebUI", "web", True)),
    ("open-webui", ("Open WebUI", "web", True)),
    ("ollama", ("Ollama (LLM)", "app", True)),
    ("vault", ("Vault (secrets)", "infra", True)),
    ("keycloak", ("Keycloak (auth)", "web", True)),
    ("authelia", ("Authelia (auth)", "web", False)),
    ("portainer", ("Portainer", "web", True)),
    ("n8n", ("n8n (automation)", "web", True)),
]

PROCESS_HINTS = [
    ("mongod", ("MongoDB", "database", False)),
    ("mongot", ("MongoDB Atlas Search", "database", False)),
    ("postgres", ("PostgreSQL", "database", False)),
    ("mysqld", ("MySQL", "database", False)),
    ("redis-server", ("Redis", "cache", False)),
    ("prometheus", ("Prometheus", "monitoring", True)),
    ("grafana", ("Grafana", "monitoring", True)),
    ("cockpit", ("Cockpit", "web", True)),
    ("pmproxy", ("Performance Co-Pilot (web)", "monitoring", True)),
    ("pmcd", ("Performance Co-Pilot", "monitoring", False)),
    ("uvicorn", ("Python web app (uvicorn)", "web", True)),
    ("gunicorn", ("Python web app (gunicorn)", "web", True)),
    ("hypercorn", ("Python web app", "web", True)),
    ("node", ("Node.js app", "web", True)),
    ("nginx", ("nginx", "proxy", False)),
    ("caddy", ("Caddy", "proxy", False)),
    ("tailscaled", ("Tailscale", "infra", False)),
    ("netbird", ("NetBird VPN", "infra", False)),
    ("cloudflared", ("Cloudflare Tunnel", "proxy", False)),
    ("ollama", ("Ollama (LLM)", "app", True)),
]


def recognize(port: Optional[int] = None, image: Optional[str] = None,
              process: Optional[str] = None) -> Optional[Recognition]:
    if image:
        il = image.lower()
        for hint, val in IMAGE_HINTS:
            if hint in il:
                return val
    if process:
        pl = process.lower()
        for hint, val in PROCESS_HINTS:
            if hint in pl:
                return val
    if port in KNOWN_PORTS:
        return KNOWN_PORTS[port]
    return None
