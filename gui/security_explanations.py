"""Human-readable explanations for security findings.

Each finding type maps to a dict with:
- what: What this means in plain language
- risk: What an attacker could do
- fix: Copy-paste fix command or file change
"""

from __future__ import annotations

import re

EXPLANATIONS: dict[tuple[str, str], dict[str, str]] = {
    ("docker", "privileged"): {
        "what": "Container runs with full system privileges — same as root on the host machine.",
        "risk": "If an attacker compromises this container, they gain complete control over your server. They can read all files, install malware, access other containers.",
        "fix": "Remove 'privileged: true' from docker-compose.yml.\nIf you need specific permissions, use cap_add instead:\n\n  cap_add:\n    - NET_ADMIN  # only what you actually need",
    },
    ("docker", "docker.sock"): {
        "what": "Docker control socket is mounted inside the container. This gives the container full control over Docker itself.",
        "risk": "An attacker inside this container can create new containers, read secrets from other containers, or escape to the host entirely.",
        "fix": "Remove the docker.sock volume mount from docker-compose.yml:\n\n  # DELETE this line:\n  - /var/run/docker.sock:/var/run/docker.sock\n\nIf you need Docker access, use a Docker proxy with limited permissions.",
    },
    ("docker", "host network"): {
        "what": "Container shares the host's network directly instead of having its own isolated network.",
        "risk": "The container can see all network traffic on the host, access services on localhost, and bypass network isolation between containers.",
        "fix": "Remove 'network_mode: host' from docker-compose.yml.\nUse port mapping instead:\n\n  ports:\n    - '8080:8080'",
    },
    ("docker", "root"): {
        "what": "Container runs as admin (root). If hacked, attacker gets full access inside the container.",
        "risk": "Combined with other vulnerabilities, root access makes container escape much easier. The attacker can modify any file inside the container.",
        "fix": "Add a USER line to your Dockerfile:\n\n  RUN adduser --disabled-password appuser\n  USER appuser\n\nOr in docker-compose.yml:\n\n  user: '1000:1000'",
    },
    ("docker", "latest"): {
        "what": "Container uses the :latest tag instead of a specific version. You don't know exactly which version is running.",
        "risk": "A compromised or buggy update could be pulled automatically. Builds are not reproducible — works on my machine, breaks on yours.",
        "fix": "Pin to a specific version in your Dockerfile or docker-compose.yml:\n\n  # Instead of: image: postgres:latest\n  image: postgres:16.2-alpine",
    },
    ("config", "env_in_git"): {
        "what": "A .env file with secrets (passwords, API keys) is committed to git. Anyone with repo access can see them.",
        "risk": "If the repo is public or gets leaked, all your secrets are exposed. Passwords, API keys, database credentials — everything.",
        "fix": "1. Add .env to .gitignore:\n   echo '.env*' >> .gitignore\n\n2. Remove from git history:\n   git rm --cached .env\n   git commit -m 'remove .env from tracking'\n\n3. Rotate ALL secrets that were in the file — they're already compromised.",
    },
    ("config", "permissions"): {
        "what": "A sensitive file (with passwords, keys, or certificates) has too broad permissions. Other users on the system can read it.",
        "risk": "Any user on the server can read this file and steal credentials or certificates.",
        "fix": "Restrict permissions to owner only:\n\n  chmod 600 <filename>\n\nThis makes the file readable only by its owner.",
    },
    ("network", "exposed"): {
        "what": "This service listens on all network interfaces (0.0.0.0) instead of just localhost. It's accessible from outside your machine.",
        "risk": "Anyone on your network (or the internet if port-forwarded) can connect to this service. Databases, Redis, debug servers should never be exposed.",
        "fix": "Bind to localhost only. In docker-compose.yml:\n\n  ports:\n    # Instead of: '5432:5432'\n    - '127.0.0.1:5432:5432'\n\nOr in app config, change host from 0.0.0.0 to 127.0.0.1",
    },
    ("deps", "vulnerability"): {
        "what": "A dependency has a known security vulnerability (CVE). An attacker knows exactly how to exploit it.",
        "risk": "Depending on the vulnerability, an attacker could execute code on your server, steal data, or crash your application.",
        "fix": "Update the vulnerable package:\n\n  pip install --upgrade <package-name>\n\nOr pin a fixed version in requirements.txt.",
    },
}

_PATTERNS: list[tuple[re.Pattern, tuple[str, str]]] = [
    (re.compile(r"privileged mode", re.I), ("docker", "privileged")),
    (re.compile(r"docker\.sock", re.I), ("docker", "docker.sock")),
    (re.compile(r"host network", re.I), ("docker", "host network")),
    (re.compile(r"runs as root|no USER set", re.I), ("docker", "root")),
    (re.compile(r":latest tag|:latest\b", re.I), ("docker", "latest")),
    (re.compile(r"\.env.*committed|\.env.*git", re.I), ("config", "env_in_git")),
    (re.compile(r"[Bb]road permissions", re.I), ("config", "permissions")),
    (re.compile(r"exposed on 0\.0\.0\.0|0\.0\.0\.0", re.I), ("network", "exposed")),
    (re.compile(r"CVE-|vulnerability|vuln", re.I), ("deps", "vulnerability")),
]

_GENERIC = {
    "what": "A potential security issue was detected in your environment.",
    "risk": "This could expose your system to attacks. Review the details and take action.",
    "fix": "Review the finding description and consult security documentation for your specific setup.",
}

_HUMAN_DESCRIPTIONS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(.+): runs in privileged mode"), r"\1: full admin access — if hacked, attacker owns the server"),
    (re.compile(r"(.+): docker\.sock mounted inside container"), r"\1: Docker control exposed — attacker can control ALL containers"),
    (re.compile(r"(.+): uses host network mode"), r"\1: shares host network — can see all traffic"),
    (re.compile(r"(.+): runs as root \(no USER set\)"), r"\1: runs as admin — if hacked, attacker gets full access"),
    (re.compile(r"(.+): uses :latest tag \((.+)\)"), r"\1: no version pinned (\2) — updates can break things"),
    (re.compile(r"\.env file committed in git: (.+)"), r"Secrets leaked in git: \1 — passwords visible to anyone with access"),
    (re.compile(r"Broad permissions \((.+)\) on sensitive file: (.+)"), r"File \2 readable by everyone (perms: \1) — should be owner-only"),
    (re.compile(r"Port (\d+) \((.+)\) exposed on 0\.0\.0\.0"), r"Port \1 (\2) open to the world — should be localhost only"),
]


def get_explanation(finding_type: str, description: str) -> dict[str, str]:
    for pattern, key in _PATTERNS:
        if pattern.search(description):
            return EXPLANATIONS.get(key, _GENERIC)
    for key, exp in EXPLANATIONS.items():
        if key[0] == finding_type:
            return exp
    return _GENERIC


def get_human_description(finding_type: str, description: str) -> str:
    for pattern, replacement in _HUMAN_DESCRIPTIONS:
        result = pattern.sub(replacement, description)
        if result != description:
            return result
    return description
