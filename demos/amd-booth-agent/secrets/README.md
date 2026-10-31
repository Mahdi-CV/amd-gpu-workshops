# Runtime secrets

Create these files on the deployment host with mode `0600`:

```text
fireworks_api_key
```

Never commit the key. The Fireworks credential is mounted only into the
Semantic Router container. OpenClaw and the booth web application do not
receive it.
