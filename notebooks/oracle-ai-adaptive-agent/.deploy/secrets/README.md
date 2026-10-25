# Runtime secrets

The image contains no endpoint key or Jupyter token. Docker Compose mounts
three host files read-only at `/run/secrets`; only the root entrypoint and its
root-owned proxy can read them. Jupyter and participant terminals run as the
unprivileged `workshop` user.

Create the secret directory on the deployment host:

```bash
sudo install -d -m 0700 -o root -g root /etc/openclaw-vsr-workshop
```

Write the endpoint keys without putting them on a command line:

```bash
sudo sh -c 'umask 077; cat > /etc/openclaw-vsr-workshop/auto_api_key'
# Type or paste the auto-endpoint key, then press Ctrl+D.

sudo sh -c 'umask 077; cat > /etc/openclaw-vsr-workshop/glm_api_key'
# Type or paste the direct-GLM key, then press Ctrl+D.
```

If both endpoints use the same credential:

```bash
sudo install -m 0600 -o root -g root \
  /etc/openclaw-vsr-workshop/auto_api_key \
  /etc/openclaw-vsr-workshop/glm_api_key
```

Generate a separate Jupyter token:

```bash
openssl rand -hex 32 \
  | sudo tee /etc/openclaw-vsr-workshop/jupyter_token >/dev/null
sudo chown root:root /etc/openclaw-vsr-workshop/jupyter_token
sudo chmod 0600 /etc/openclaw-vsr-workshop/jupyter_token
```

Enforce and inspect metadata without printing values:

```bash
sudo chown root:root /etc/openclaw-vsr-workshop/{auto_api_key,glm_api_key,jupyter_token}
sudo chmod 0600 /etc/openclaw-vsr-workshop/{auto_api_key,glm_api_key,jupyter_token}
sudo stat -c '%A %U:%G %n' /etc/openclaw-vsr-workshop/*
```

Never place real secret files in the repository, notebook, Compose environment,
image build arguments, OpenClaw state, logs, or test artifacts. To rotate a
secret, replace its host file atomically and recreate the container:

```bash
docker compose --env-file /etc/openclaw-vsr-workshop/workshop.env \
  up -d --force-recreate
```
