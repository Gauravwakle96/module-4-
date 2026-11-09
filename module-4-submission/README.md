# Module 4 submission files

Source: https://github.com/Gauravwakle96/module-4-

The Docker configuration is at the repository root: `Dockerfile`, `.dockerignore`, and `compose.yaml`. See `MODULE_4.md` for commands and the architecture diagram.

Upload **one image**, `02-module4-summary.png`, to LinkedIn using `post.txt`. It combines an actual screenshot of the running Docker website with verified container details. `01-docker-website.png` is the original browser capture.

Checks completed locally on 9 November 2026:

- Docker build and Compose startup passed. App and PostgreSQL are healthy.
- All **28 tests passed** on Windows and inside a Linux test container.
- Ruff lint, formatting, mypy, and Dockerfile build checks passed.
- Feedback remained saved after both Compose containers were replaced with new IDs, using the named PostgreSQL volume.
- Pausing the database produced HTTP 503 responses; unpausing it restored health and access to the saved feedback.
- The app runs as UID/GID 10001 with a read-only root filesystem and dropped capabilities. The database port is not published.
- The runtime contains no `.env`, test suite, pytest, pip, or setuptools.
- Trivy found **zero fixable HIGH/CRITICAL vulnerabilities** in the final app image using the scan options shown below. This is not a claim of zero vulnerabilities at every severity or in every dependency.
- Browser submit/reload passed with no JavaScript errors, no horizontal overflow, and no axe WCAG A/AA findings at 1280, 768, and 390 px widths.

Evidence: `docker-checks.json`, `compose-status.txt`, `app-logs.txt`, `image-scan.json`, and `browser-checks.json`. The image scan file contains the scan scope, image ID, targets, and findings, with incidental image metadata omitted.

```powershell
docker run --rm --mount type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock aquasec/trivy:0.76.2 image --scanners vuln --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 module4-feedback-board:1.0
```

The cloud website remains the existing Module 3 deployment. Module 4 is verified locally in Docker Desktop's Linux engine; CI/CD and cloud container deployment are later work.
